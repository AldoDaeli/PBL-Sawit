"""Autentikasi, katalog produk, ulasan (baca), dan formulir kontak."""
import re, secrets
from flask import g, current_app
from . import bp, body, ok
from .. import otp
from ..config import KATEGORI
from ..db import get_db, IntegrityErrors
from ..errors import ApiError
from ..security import (now_ms, hash_pw, cek_pw, DUMMY_HASH, buat_sesi, hapus_sesi, wajib, sisa_blokir,
                        catat_gagal, reset_gagal, _token, batasi_laju, ip_klien)
from ..serializers import user_out, produk_out, ulasan_out
from ..services import sapu
from ..validators import username_ok, email_ok, password_ok, to_int


@bp.get('/kesehatan')
def kesehatan():
    get_db().one('SELECT 1 AS ok')
    return ok({'status': 'ok'})


# ---------------- Auth ----------------
@bp.post('/auth/masuk')
def masuk():
    db, b = get_db(), body()
    k = str(b.get('username') or '').strip().lower()[:90]
    pw = str(b.get('password') or '')[:200]
    if not k or not pw: raise ApiError('Username dan password wajib diisi.')
    # Dua pembatas: per username ('u:' + nama) dan per IP ('ip:' + alamat). Awalan memisahkan ruang kunci sehingga
    # input pengguna tidak bisa menabrak kunci IP. Batas IP lebih longgar karena satu IP bisa dipakai banyak orang (NAT).
    ku, ki = 'u:' + k, 'ip:' + ip_klien()
    sisa = max(sisa_blokir(db, ku), sisa_blokir(db, ki))
    if sisa: raise ApiError(f'Terlalu banyak percobaan. Coba lagi {sisa} menit lagi.', 429)
    u = db.one('SELECT * FROM pengguna WHERE LOWER(username)=%s', (k,))
    benar = cek_pw(u['hash'] if u else DUMMY_HASH, pw) and u is not None   # selalu verifikasi hash: waktu respons seragam
    if not benar:
        current_app.logger.warning('LOGIN GAGAL akun_ada=%s ip=%s', bool(u), ip_klien())   # nama pengguna tidak dicatat (bisa berisi password salah ketik)
        catat_gagal(db, ku); catat_gagal(db, ki, current_app.config['MAKS_GAGAL'] * 4)
        db.commit()                              # commit agar hitungan gagal tetap tersimpan
        raise ApiError('Username atau password salah.', 401)
    if not u['aktif']: raise ApiError('Akun dinonaktifkan. Hubungi admin.', 403)
    reset_gagal(db, ku)
    current_app.logger.info('LOGIN OK user_id=%s ip=%s', u['id'], ip_klien())
    return ok({'token': buat_sesi(db, u['id']), 'user': user_out(u)})


def _detik_sisa(p, jeda):
    return max(1, -(-(p['kirim_terakhir'] + jeda * 1000 - now_ms()) // 1000))


def _email_dari(b):
    return str(b.get('email') or '').strip().lower()[:100]


def _simpan_kode(db, p, email, username, hash_password):
    """Buat kode baru untuk pendaftaran tertunda (INSERT bila baru, UPDATE bila ada). Kembalikan kode asli untuk dikirim."""
    c, now = current_app.config, now_ms()
    kode, garam = otp.buat_kode(), secrets.token_hex(16)
    kh, exp = otp.hash_kode(email, kode, garam), now + c['OTP_MENIT'] * 60000
    if p:
        db.run('UPDATE otp_daftar SET username=%s, hash=%s, kode_hash=%s, garam=%s, kedaluwarsa=%s, salah=0, kirim_n=%s, kirim_terakhir=%s WHERE email=%s',
               (username, hash_password, kh, garam, exp, p['kirim_n'] + 1, now, email))
    else:
        db.run('INSERT INTO otp_daftar (email,username,hash,kode_hash,garam,kedaluwarsa,salah,kirim_n,kirim_terakhir,dibuat) VALUES (%s,%s,%s,%s,%s,%s,0,1,%s,%s)',
               (email, username, hash_password, kh, garam, exp, now, now))
    return kode


@bp.post('/auth/lupa')
def lupa_password():
    """Langkah 1 reset password: kirim kode OTP ke email akun. Respons SELALU sama (email terdaftar atau tidak)
    agar penyerang tidak bisa memeriksa email mana yang punya akun."""
    c = current_app.config
    batasi_laju('lupa', c['LAJU_OTP'], 600)
    db, email = get_db(), _email_dari(body())
    if not email_ok(email): raise ApiError('Format email tidak valid.')
    umum = ok({'berlaku': c['OTP_MENIT'], 'jeda': c['OTP_JEDA_DETIK']})
    u, now = db.one('SELECT id, username, aktif FROM pengguna WHERE LOWER(email)=%s', (email,)), now_ms()
    if not u or not u['aktif']: return umum
    p = db.one('SELECT * FROM otp_reset WHERE email=%s', (email,))
    if p and now - p['kirim_terakhir'] < c['OTP_JEDA_DETIK'] * 1000: return umum          # jeda kirim ulang
    n = p['kirim_n'] if p and now - p['kirim_terakhir'] < 3_600_000 else 0                 # jendela 1 jam
    if n >= c['OTP_MAKS_KIRIM']: return umum
    kode, garam = otp.buat_kode(), secrets.token_hex(16)
    nilai = (otp.hash_kode(email, kode, garam), garam, now + c['OTP_MENIT'] * 60000, n + 1, now)
    if p: db.run('UPDATE otp_reset SET kode_hash=%s, garam=%s, kedaluwarsa=%s, salah=0, kirim_n=%s, kirim_terakhir=%s WHERE email=%s', nilai + (email,))
    else: db.run('INSERT INTO otp_reset (kode_hash,garam,kedaluwarsa,salah,kirim_n,kirim_terakhir,email) VALUES (%s,%s,%s,0,%s,%s,%s)', nilai + (email,))
    db.commit()
    try: otp.kirim_reset(email, u['username'], kode)
    except ApiError as e:
        if e.status == 503: raise                       # SMTP belum dikonfigurasi: pesan jelas untuk admin (tidak membocorkan keberadaan akun)
        current_app.logger.warning('Reset password: email gagal terkirim')
    return umum


@bp.post('/auth/lupa/reset')
def lupa_reset():
    """Langkah 2: email + kode OTP + password baru. Berhasil -> password diganti, semua sesi lama dikeluarkan, blokir login dibuka."""
    c, b = current_app.config, body()
    batasi_laju('otp', c['LAJU_OTP'], 600)
    db, email = get_db(), _email_dari(b)
    kode, pw = re.sub(r'\s', '', str(b.get('kode') or '')), str(b.get('password') or '')
    if not re.fullmatch(r'\d{6}', kode): raise ApiError('Kode OTP terdiri dari 6 angka.')
    if not password_ok(pw): raise ApiError('Password 8–64 karakter, kombinasi huruf dan angka.')
    gagal = 'Kode salah atau sudah kedaluwarsa. Minta kode baru.'
    p = db.one('SELECT * FROM otp_reset WHERE email=%s', (email,))
    if not p or p['kedaluwarsa'] < now_ms() or p['salah'] >= c['OTP_MAKS_SALAH']: raise ApiError(gagal, 400)
    if not otp.cocok(otp.hash_kode(email, kode, p['garam']), p['kode_hash']):
        current_app.logger.warning('OTP RESET SALAH ip=%s', ip_klien())
        db.run('UPDATE otp_reset SET salah=salah+1 WHERE email=%s', (email,)); db.commit()
        raise ApiError(gagal, 400)
    u = db.one('SELECT id, username, aktif FROM pengguna WHERE LOWER(email)=%s', (email,))
    if not u or not u['aktif']: raise ApiError(gagal, 400)
    db.run('UPDATE pengguna SET hash=%s WHERE id=%s', (hash_pw(pw), u['id']))
    db.run('DELETE FROM otp_reset WHERE email=%s', (email,))
    db.run('DELETE FROM sesi WHERE user_id=%s', (u['id'],))
    reset_gagal(db, 'u:' + u['username'].lower()); db.commit()
    current_app.logger.info('PASSWORD RESET user_id=%s ip=%s', u['id'], ip_klien())
    otp.kirim_info_password_diubah(email, u['username'])
    return ok()


@bp.post('/auth/daftar')
def daftar():
    """Langkah 1: validasi data, simpan sebagai pendaftaran tertunda, kirim kode OTP ke email. Akun BELUM dibuat."""
    c = current_app.config
    batasi_laju('daftar', c['LAJU_DAFTAR'], 600)
    db, b = get_db(), body()
    username, pw, email = b.get('username'), b.get('password'), _email_dari(b)
    if not username_ok(username): raise ApiError('Username 4–20 karakter (huruf, angka, garis bawah).')
    if not email_ok(email): raise ApiError('Format email tidak valid.')
    if not password_ok(pw): raise ApiError('Password minimal 8 karakter, kombinasi huruf dan angka.')
    if db.one('SELECT id FROM pengguna WHERE LOWER(username)=LOWER(%s)', (username,)): raise ApiError('Username sudah dipakai.', 409)
    if db.one('SELECT id FROM pengguna WHERE LOWER(email)=LOWER(%s)', (email,)): raise ApiError('Email sudah terdaftar.', 409)
    db.run('DELETE FROM otp_daftar WHERE dibuat < %s', (now_ms() - 86_400_000,))      # buang pendaftaran tertunda yang basi (>1 hari)
    p = db.one('SELECT * FROM otp_daftar WHERE email=%s', (email,))
    if p and now_ms() - p['kirim_terakhir'] < c['OTP_JEDA_DETIK'] * 1000:
        raise ApiError(f"Kode sudah dikirim. Tunggu {_detik_sisa(p, c['OTP_JEDA_DETIK'])} detik sebelum mencoba lagi.", 429)
    if p: p['kirim_n'] = 0                      # pendaftaran ulang dari awal: hitungan kirim dimulai lagi
    kode = _simpan_kode(db, p, email, username, hash_pw(pw))
    otp.kirim_kode(email, username, kode)       # gagal kirim -> ApiError -> transaksi di-rollback
    return ok({'email': email, 'berlaku': c['OTP_MENIT'], 'jeda': c['OTP_JEDA_DETIK']})


@bp.post('/auth/daftar/verifikasi')
def daftar_verifikasi():
    """Langkah 2: cocokkan kode OTP; bila benar, akun dibuat."""
    c = current_app.config
    batasi_laju('otp', c['LAJU_OTP'], 600)
    db, b = get_db(), body()
    email, kode = _email_dari(b), re.sub(r'\s', '', str(b.get('kode') or ''))
    if not re.fullmatch(r'\d{6}', kode): raise ApiError('Kode OTP terdiri dari 6 angka.')
    p = db.one('SELECT * FROM otp_daftar WHERE email=%s', (email,))
    if not p: raise ApiError('Pendaftaran tidak ditemukan. Silakan daftar ulang.', 404)
    if p['kedaluwarsa'] < now_ms(): raise ApiError('Kode OTP sudah kedaluwarsa. Kirim ulang kode baru.', 400)
    if p['salah'] >= c['OTP_MAKS_SALAH']: raise ApiError('Terlalu banyak kode salah. Kirim ulang kode baru.', 429)
    if not otp.cocok(otp.hash_kode(email, kode, p['garam']), p['kode_hash']):
        current_app.logger.warning('OTP DAFTAR SALAH ip=%s', ip_klien())
        db.run('UPDATE otp_daftar SET salah=salah+1 WHERE email=%s', (email,))
        db.commit()                              # commit agar hitungan salah tetap tersimpan
        sisa = c['OTP_MAKS_SALAH'] - p['salah'] - 1
        raise ApiError(f'Kode OTP salah. Sisa percobaan: {sisa}.' if sisa > 0 else 'Kode OTP salah. Kirim ulang kode baru.', 400)
    if db.one('SELECT id FROM pengguna WHERE LOWER(username)=LOWER(%s)', (p['username'],)): raise ApiError('Username sudah dipakai. Silakan daftar ulang.', 409)
    if db.one('SELECT id FROM pengguna WHERE LOWER(email)=LOWER(%s)', (email,)): raise ApiError('Email sudah terdaftar.', 409)
    try:
        db.run('INSERT INTO pengguna (username,email,hash,peran,aktif,dibuat) VALUES (%s,%s,%s,%s,1,%s)',
               (p['username'], email, p['hash'], 'customer', now_ms()))
    except IntegrityErrors:
        raise ApiError('Username atau email sudah terdaftar.', 409)
    db.run('DELETE FROM otp_daftar WHERE email=%s', (email,))
    return ok(None, 201)


@bp.post('/auth/daftar/kirim-ulang')
def daftar_kirim_ulang():
    """Kirim kode OTP baru (kode lama tidak berlaku lagi). Dibatasi jeda antar kirim dan jumlah kirim per pendaftaran."""
    c = current_app.config
    batasi_laju('otp', c['LAJU_OTP'], 600)
    db, b = get_db(), body()
    email = _email_dari(b)
    p = db.one('SELECT * FROM otp_daftar WHERE email=%s', (email,))
    if not p: raise ApiError('Pendaftaran tidak ditemukan. Silakan daftar ulang.', 404)
    if now_ms() - p['kirim_terakhir'] < c['OTP_JEDA_DETIK'] * 1000:
        raise ApiError(f"Tunggu {_detik_sisa(p, c['OTP_JEDA_DETIK'])} detik sebelum meminta kode lagi.", 429)
    if p['kirim_n'] >= c['OTP_MAKS_KIRIM']: raise ApiError('Batas pengiriman kode tercapai. Silakan daftar ulang beberapa saat lagi.', 429)
    kode = _simpan_kode(db, p, email, p['username'], p['hash'])
    otp.kirim_kode(email, p['username'], kode)
    return ok({'email': email, 'berlaku': c['OTP_MENIT'], 'jeda': c['OTP_JEDA_DETIK']})


@bp.post('/auth/keluar')
@wajib()
def keluar():
    hapus_sesi(get_db(), _token())
    return ok()


@bp.get('/auth/saya')
@wajib()
def saya():
    return ok(user_out(g.user))


# ---------------- Katalog ----------------
@bp.get('/kategori')
def kategori(): return ok(KATEGORI)


@bp.get('/produk')
def produk_list():
    db = get_db(); sapu(db)     # pesanan kedaluwarsa dibatalkan dulu agar stok yang tampil akurat
    return ok([produk_out(p) for p in db.all('SELECT * FROM produk ORDER BY id')])


@bp.get('/produk/<int:pid>')
def produk_detail(pid):
    p = get_db().one('SELECT * FROM produk WHERE id=%s', (pid,))
    if not p: raise ApiError('Produk tidak ditemukan.', 404)
    return ok(produk_out(p))


@bp.get('/produk/<int:pid>/ulasan')
def produk_ulasan(pid):
    rows = get_db().all('SELECT r.*, u.username AS nama FROM ulasan r JOIN pengguna u ON u.id=r.user_id '
                        'WHERE r.produk_id=%s ORDER BY r.dibuat DESC', (pid,))
    from ..services import lanjutan_ulasan
    lj = lanjutan_ulasan(get_db(), [r['id'] for r in rows])
    return ok([ulasan_out(r, lj.get(r['id'])) for r in rows])


# ---------------- Kontak ----------------
@bp.post('/kontak')
def kontak():
    batasi_laju('kontak', current_app.config['LAJU_KONTAK'], 600)
    b = body()
    nama, email, jenis, isi = str(b.get('nama') or '').strip(), b.get('email'), b.get('jenis'), str(b.get('isi') or '').strip()
    if len(nama) < 3 or len(nama) > 100: raise ApiError('Nama minimal 3 karakter.')
    if not email_ok(email): raise ApiError('Format email tidak valid.')
    if jenis not in ('Pertanyaan', 'Keluhan', 'Kerja sama'): raise ApiError('Jenis pesan tidak valid.')
    if len(isi) < 10 or len(isi) > 500: raise ApiError('Pesan 10–500 karakter.')
    get_db().run('INSERT INTO pesan_kontak (nama,email,jenis,isi,dibuat) VALUES (%s,%s,%s,%s,%s)', (nama, email, jenis, isi, now_ms()))
    return ok(None, 201)
