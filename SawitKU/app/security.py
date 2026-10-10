import hashlib, secrets, threading, time
from collections import deque
from functools import wraps
from flask import request, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from .db import get_db
from .errors import ApiError

def now_ms(): return int(time.time() * 1000)

def hash_pw(pw): return generate_password_hash(pw)              # scrypt + salt acak
def cek_pw(hash_, pw): return check_password_hash(hash_, pw)
DUMMY_HASH = generate_password_hash('dummy-password-untuk-menyamakan-waktu')

def _th(token): return hashlib.sha256(token.encode()).hexdigest()

def buat_sesi(db, user_id):
    token = secrets.token_urlsafe(32)
    db.run('INSERT INTO sesi (token_hash, user_id, kedaluwarsa) VALUES (%s,%s,%s)',
           (_th(token), user_id, now_ms() + current_app.config['SESI_MENIT'] * 60000))
    return token

def _token():
    h = request.headers.get('Authorization', '')
    return h[7:].strip() if h.lower().startswith('bearer ') else None

def hapus_sesi(db, token):
    db.run('DELETE FROM sesi WHERE token_hash=%s', (_th(token),))

def user_sekarang(db):
    """Pengguna dari token Bearer, atau None. Sesi diperpanjang setiap ada aktivitas (sliding)."""
    t = _token()
    if not t or len(t) > 100: return None
    s = db.one('SELECT s.kedaluwarsa, u.* FROM sesi s JOIN pengguna u ON u.id=s.user_id WHERE s.token_hash=%s', (_th(t),))
    now = now_ms()
    if not s: return None
    if s['kedaluwarsa'] < now or not s['aktif']:
        hapus_sesi(db, t); db.commit(); return None
    masa = current_app.config['SESI_MENIT'] * 60000
    if s['kedaluwarsa'] - now < masa // 2:      # perpanjang hanya bila sisa < separuh masa: tanpa tulis+commit DB di setiap request
        db.run('UPDATE sesi SET kedaluwarsa=%s WHERE token_hash=%s', (now + masa, _th(t)))
    s.pop('kedaluwarsa')
    return s

def wajib(peran=None):
    """Dekorator RBAC. peran=None -> cukup login; 'customer' / 'admin' -> harus sesuai."""
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = user_sekarang(get_db())
            if not u: raise ApiError('Silakan masuk terlebih dahulu.', 401)
            if peran and u['peran'] != peran:
                raise ApiError('Fitur ini khusus akun customer.' if peran == 'customer' else 'Akses ditolak.', 403)
            g.user = u
            if u['peran'] == 'admin' and request.method != 'GET':      # jejak audit aksi admin
                current_app.logger.info('AUDIT admin=%s %s %s ip=%s', u['id'], request.method, request.path, ip_klien())
            return f(*a, **k)
        return w
    return deco

# ---- Pembatas percobaan login ----
def sisa_blokir(db, k):
    r = db.one('SELECT blokir_hingga FROM gagal_login WHERE kunci=%s', (k,))
    return -(-(r['blokir_hingga'] - now_ms()) // 60000) if r and r['blokir_hingga'] > now_ms() else 0

def catat_gagal(db, k, maks=None):
    c = current_app.config
    maks = maks or c['MAKS_GAGAL']
    r = db.one('SELECT n FROM gagal_login WHERE kunci=%s FOR UPDATE', (k,))
    n, blokir = (r['n'] if r else 0) + 1, 0
    if n >= maks: blokir, n = now_ms() + c['BLOKIR_MENIT'] * 60000, 0
    if r: db.run('UPDATE gagal_login SET n=%s, blokir_hingga=%s WHERE kunci=%s', (n, blokir, k))
    else: db.run('INSERT INTO gagal_login (kunci, n, blokir_hingga) VALUES (%s,%s,%s)', (k, n, blokir))

def reset_gagal(db, k): db.run('DELETE FROM gagal_login WHERE kunci=%s', (k,))


# ---- Pembatas laju per IP untuk endpoint publik (daftar, kontak) ----
# Disimpan di memori proses (jendela geser). Dengan N worker gunicorn batas efektifnya N kali lipat; tetap cukup untuk
# menahan spam sederhana. Untuk batas global yang ketat, tambahkan limit_req di Nginx.
_LAJU, _LAJU_LOCK = {}, threading.Lock()

def ip_klien(): return (request.remote_addr or '?')[:60]

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
