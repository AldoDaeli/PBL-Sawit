"""Keamanan: hash password, sesi berbasis JWT, RBAC, pembatas percobaan login, dan pembatas laju per IP.

Sesi = JWT (HS256) yang membawa `jti`; `jti` (di-hash) juga dicatat di tabel `sesi`. Tanda tangan JWT ditolak lebih dulu bila palsu/kedaluwarsa
(murah), lalu tabel `sesi` dicek agar logout, nonaktifkan akun, dan reset password bisa mencabut token seketika. Peran pengguna selalu
dibaca dari database, bukan dari isi token."""
import hashlib, logging, os, secrets, threading, time
from collections import deque
from functools import wraps

import jwt
from flask import request
from werkzeug.security import generate_password_hash, check_password_hash

from .config import cfg, AKAR
from .db import get_db, konteks
from .errors import ApiError

log = logging.getLogger('sawitku')
ALGORITMA, PENERBIT = 'HS256', 'sawitku'


def now_ms(): return int(time.time() * 1000)

def hash_pw(pw): return generate_password_hash(pw)              # scrypt + salt acak
def cek_pw(hash_, pw): return check_password_hash(hash_, pw)
DUMMY_HASH = generate_password_hash('dummy-password-untuk-menyamakan-waktu')

def _th(jti): return hashlib.sha256(jti.encode()).hexdigest()


# ---------------- JWT ----------------
def rahasia_jwt():
    """JWT_SECRET dari .env. Bila kosong: dibuat sekali lalu disimpan di .jwt_secret (dibagi semua worker, tetap sama setelah restart)."""
    if cfg['JWT_SECRET']: return cfg['JWT_SECRET']
    jalur = os.path.join(AKAR, '.jwt_secret')
    for _ in range(2):
        try:
            with open(jalur, encoding='ascii') as f: s = f.read().strip()
            if len(s) >= 32: cfg['JWT_SECRET'] = s; return s
        except OSError: pass
        try:
            fd = os.open(jalur, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='ascii') as f: f.write(secrets.token_urlsafe(48))
        except FileExistsError: time.sleep(0.05)           # worker lain sedang membuatnya
        except OSError: break
    log.warning('JWT_SECRET kosong dan .jwt_secret tidak bisa ditulis: memakai kunci acak sementara (sesi hilang saat restart). Isi JWT_SECRET di .env.')
    cfg['JWT_SECRET'] = secrets.token_urlsafe(48)
    return cfg['JWT_SECRET']


def _jwt(jti, user_id, peran, mulai_ms, exp_ms):
    return jwt.encode({'iss': PENERBIT, 'sub': str(user_id), 'jti': jti, 'role': peran, 'iat': mulai_ms // 1000, 'exp': exp_ms // 1000},
                      rahasia_jwt(), algorithm=ALGORITMA)


def _bearer(request):
    h = request.headers.get('authorization', '')
    return h[7:].strip() if h.lower().startswith('bearer ') else None


def _klaim(token, cek_exp=True):
    """Isi token bila tanda tangan sah (dan belum kedaluwarsa), selain itu None. Algoritma dikunci: 'none' dan HS384 ditolak."""
    if not token or len(token) > 1500: return None
    try:
        return jwt.decode(token, rahasia_jwt(), algorithms=[ALGORITMA], issuer=PENERBIT,
                          options={'require': ['exp', 'sub', 'jti', 'iss'], 'verify_exp': cek_exp})
    except jwt.PyJWTError:
        return None


def buat_sesi(db, user_id, peran):
    """Sesi baru: catat jti di database, kembalikan JWT-nya."""
    jti, now = secrets.token_urlsafe(16), now_ms()
    exp = now + cfg['SESI_MENIT'] * 60000
    db.run('INSERT INTO sesi (token_hash, user_id, kedaluwarsa) VALUES (%s,%s,%s)', (_th(jti), user_id, exp))
    return _jwt(jti, user_id, peran, now, exp)


def hapus_sesi(db, request):
    k = _klaim(_bearer(request), cek_exp=False)
    if k: db.run('DELETE FROM sesi WHERE token_hash=%s', (_th(k['jti']),))


def user_sekarang(db, request):
    """Pengguna dari JWT Bearer, atau None. Masa berlaku diperpanjang (sliding) saat sisanya kurang dari separuh:
    token baru dikirim lewat header X-Token-Baru dan frontend menggantinya."""
    k = _klaim(_bearer(request))
    if not k: return None
    s = db.one('SELECT s.kedaluwarsa, u.* FROM sesi s JOIN pengguna u ON u.id=s.user_id WHERE s.token_hash=%s', (_th(k['jti']),))
    if not s or str(s['id']) != k['sub']: return None
    now = now_ms()
    if s['kedaluwarsa'] < now or not s['aktif']:
        db.run('DELETE FROM sesi WHERE token_hash=%s', (_th(k['jti']),)); db.commit(); return None
    masa = cfg['SESI_MENIT'] * 60000
    if s['kedaluwarsa'] - now < masa // 2:      # tanpa tulis+commit DB di setiap request
        exp = now + masa
        db.run('UPDATE sesi SET kedaluwarsa=%s WHERE token_hash=%s', (exp, _th(k['jti'])))
        konteks().token_baru = _jwt(k['jti'], s['id'], s['peran'], now, exp)
    s.pop('kedaluwarsa')
    return s


def wajib(peran=None):
    """Dekorator RBAC untuk route Flask. peran=None -> cukup login; 'customer' / 'admin' -> harus sesuai.
    Baris pengguna diteruskan sebagai ARGUMEN POSISI PERTAMA fungsi route: `@wajib('admin') def x(u, pid): ...`."""
    def dekorator(fn):
        @wraps(fn)
        def bungkus(*a, **k):
            u = user_sekarang(get_db(), request)
            if not u: raise ApiError('Silakan masuk terlebih dahulu.', 401)
            if peran and u['peran'] != peran:
                raise ApiError('Fitur ini khusus akun customer.' if peran == 'customer' else 'Akses ditolak.', 403)
            if u['peran'] == 'admin' and request.method != 'GET':      # jejak audit aksi admin
                log.info('AUDIT admin=%s %s %s ip=%s', u['id'], request.method, request.path, ip_klien())
            return fn(u, *a, **k)
        bungkus.peran = peran or 'login'                                # dibaca halaman dokumentasi /api/docs
        return bungkus
    return dekorator


# ---- Pembatas percobaan login ----
def sisa_blokir(db, k):
    r = db.one('SELECT blokir_hingga FROM gagal_login WHERE kunci=%s', (k,))
    return -(-(r['blokir_hingga'] - now_ms()) // 60000) if r and r['blokir_hingga'] > now_ms() else 0

def catat_gagal(db, k, maks=None):
    maks = maks or cfg['MAKS_GAGAL']
    r = db.one('SELECT n FROM gagal_login WHERE kunci=%s FOR UPDATE', (k,))
    n, blokir = (r['n'] if r else 0) + 1, 0
    if n >= maks: blokir, n = now_ms() + cfg['BLOKIR_MENIT'] * 60000, 0
    if r: db.run('UPDATE gagal_login SET n=%s, blokir_hingga=%s WHERE kunci=%s', (n, blokir, k))
    else: db.run('INSERT INTO gagal_login (kunci, n, blokir_hingga) VALUES (%s,%s,%s)', (k, n, blokir))

def reset_gagal(db, k): db.run('DELETE FROM gagal_login WHERE kunci=%s', (k,))


# ---- Pembatas laju per IP untuk endpoint publik (daftar, kontak) ----
# Disimpan di memori proses (jendela geser). Dengan N worker batas efektifnya N kali lipat; tetap cukup untuk menahan spam sederhana.
# Untuk batas global yang ketat, tambahkan limit_req di Nginx.
_LAJU, _LAJU_LOCK = {}, threading.Lock()

def ip_klien(): return konteks().ip[:60]

def reset_laju():
    with _LAJU_LOCK: _LAJU.clear()

def batasi_laju(nama, maks, detik, siapa=None):
    """siapa=None -> per IP; isi (mis. id pengguna) untuk membatasi per akun."""
    now, kunci = time.monotonic(), (nama, siapa or ip_klien())
    with _LAJU_LOCK:
        if len(_LAJU) > 10_000:       # cegah memori membengkak: buang catatan yang sudah di luar jendela
            for k in [k for k, d in _LAJU.items() if not d or now - d[-1] > detik]: del _LAJU[k]
        d = _LAJU.setdefault(kunci, deque())
        while d and now - d[0] > detik: d.popleft()
        if len(d) >= maks: raise ApiError('Terlalu banyak permintaan. Coba lagi beberapa menit lagi.', 429)
        d.append(now)
