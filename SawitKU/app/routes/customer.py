"""Fitur akun customer: favorit, keranjang, ulasan, profil dan ganti email."""
import logging, re, secrets


from . import api, ok
from .. import otp
from ..config import cfg
from ..db import get_db, IntegrityErrors
from ..errors import ApiError
from ..schemas import badan, KeranjangIn, QtyIn, UlasanIn, TeksIn, ProfilIn, EmailMintaIn, KodeSajaIn
from ..security import now_ms, wajib, cek_pw, batasi_laju, sisa_blokir, catat_gagal, reset_gagal, ip_klien
from ..serializers import user_out, produk_out
from ..services import PRODUK_SQL, hitung_rating
from ..uploads import resolve_gambar, hapus_media
from ..validators import username_ok, email_ok, to_int, baca_alamat

log = logging.getLogger('sawitku')
pelanggan, siapa_saja = wajib('customer'), wajib()


# ---------------- Favorit ----------------
@api.get('/favorit', tags=['Belanja'])
@siapa_saja
def favorit(u):
    return ok([r['produk_id'] for r in get_db().all('SELECT produk_id FROM favorit WHERE user_id=%s ORDER BY produk_id', (u['id'],))])


@api.post('/favorit/<int:pid>/toggle', tags=['Belanja'])
@pelanggan
def fav_toggle(u, pid):
    db, uid = get_db(), u['id']
    if not db.one('SELECT id FROM produk WHERE id=%s', (pid,)): raise ApiError('Produk tidak ditemukan.', 404)
    if db.one('SELECT 1 AS x FROM favorit WHERE user_id=%s AND produk_id=%s', (uid, pid)):
        db.run('DELETE FROM favorit WHERE user_id=%s AND produk_id=%s', (uid, pid)); return ok({'aktif': False})
    db.run('INSERT INTO favorit (user_id,produk_id) VALUES (%s,%s)', (uid, pid)); return ok({'aktif': True})


# ---------------- Keranjang ----------------
@api.get('/keranjang', tags=['Belanja'])
@pelanggan
def keranjang(u):
    rows = get_db().all('SELECT k.qty, p.* FROM keranjang k JOIN produk p ON p.id=k.produk_id WHERE k.user_id=%s ORDER BY p.id', (u['id'],))
    return ok([{'produkId': r['id'], 'qty': r['qty'], 'p': produk_out(r)} for r in rows])


@api.post('/keranjang', status_code=201, tags=['Belanja'])
@pelanggan
def ker_add(u):
    b = badan(KeranjangIn)
    db, uid = get_db(), u['id']
    pid, qty = to_int(b.produkId, 'Data produk tidak valid.'), to_int(b.qty, 'Data produk tidak valid.')
    p = db.one('SELECT id, stok FROM produk WHERE id=%s', (pid,))
    if not p or qty <= 0: raise ApiError('Data produk tidak valid.')
    c = db.one('SELECT qty FROM keranjang WHERE user_id=%s AND produk_id=%s', (uid, pid))
    n = (c['qty'] if c else 0) + qty
    if n > p['stok']: raise ApiError(f"Stok hanya tersisa {p['stok']}.", 409)
    if c: db.run('UPDATE keranjang SET qty=%s WHERE user_id=%s AND produk_id=%s', (n, uid, pid))
    else: db.run('INSERT INTO keranjang (user_id,produk_id,qty) VALUES (%s,%s,%s)', (uid, pid, n))
    return ok()


@api.put('/keranjang/<int:pid>', tags=['Belanja'])
@pelanggan
def ker_set(u, pid):
    b = badan(QtyIn)
    db, uid = get_db(), u['id']
    qty = to_int(b.qty, 'Jumlah tidak valid.')
    p = db.one('SELECT stok FROM produk WHERE id=%s', (pid,))
    if not p or qty < 1 or qty > p['stok']: raise ApiError(f"Jumlah harus 1–{p['stok'] if p else 0}.")
    _, n = db.run('UPDATE keranjang SET qty=%s WHERE user_id=%s AND produk_id=%s', (qty, uid, pid))
    if not n and not db.one('SELECT 1 AS x FROM keranjang WHERE user_id=%s AND produk_id=%s', (uid, pid)):
        raise ApiError('Produk tidak ada di keranjang.', 404)
    return ok()


@api.delete('/keranjang/<int:pid>', tags=['Belanja'])
@pelanggan
def ker_hapus(u, pid):
    get_db().run('DELETE FROM keranjang WHERE user_id=%s AND produk_id=%s', (u['id'], pid))
    return ok()


# ---------------- Ulasan ----------------
@api.post('/ulasan', status_code=201, tags=['Ulasan'], summary='Kirim ulasan (rating 1–5) untuk barang yang sudah diterima')
@pelanggan
def kirim_ulasan(u):
    b = badan(UlasanIn)
    db, uid = get_db(), u['id']
    pid = to_int(b.produkId, 'Produk tidak valid.')
    rating = to_int(b.rating, 'Pilih rating 1–5.')
    teks = str(b.teks or '').strip()
    if not 1 <= rating <= 5: raise ApiError('Pilih rating 1–5.')
    if not 5 <= len(teks) <= 300: raise ApiError('Ulasan 5–300 karakter.')
    if not db.one('SELECT 1 AS x FROM pesanan o JOIN pesanan_item i ON i.pesanan_id=o.id '
                  'WHERE o.user_id=%s AND o.status=%s AND i.produk_id=%s LIMIT 1', (uid, 'selesai', pid)):
        raise ApiError('Ulasan hanya untuk barang yang sudah diterima.', 403)
    if db.one('SELECT 1 AS x FROM ulasan WHERE user_id=%s AND produk_id=%s', (uid, pid)):
        raise ApiError('Kamu sudah mengulas produk ini.', 409)
    try:
        db.run('INSERT INTO ulasan (produk_id,user_id,rating,teks,dibuat) VALUES (%s,%s,%s,%s,%s)', (pid, uid, rating, teks, now_ms()))
    except IntegrityErrors:
        raise ApiError('Kamu sudah mengulas produk ini.', 409)
    hitung_rating(db, pid)
    return ok()


@api.post('/ulasan/<int:rid>/balas', status_code=201, tags=['Ulasan'])
@pelanggan
def balas_ulasan(u, rid):
    """Pemilik ulasan membalas komentar admin. Bergantian: hanya boleh bila pesan terakhir dari admin; maks 5 balasan pelanggan per ulasan."""
    b = badan(TeksIn)
    db, uid = get_db(), u['id']
    teks = str(b.teks or '').strip()
    r = db.one('SELECT id, user_id, balasan_teks FROM ulasan WHERE id=%s FOR UPDATE', (rid,))
    if not r or r['user_id'] != uid: raise ApiError('Ulasan tidak ditemukan.', 404)
    if not r['balasan_teks']: raise ApiError('Admin belum membalas ulasan ini.', 409)
    if not 3 <= len(teks) <= 300: raise ApiError('Balasan 3–300 karakter.')
    lanj = db.all('SELECT dari FROM ulasan_balas WHERE ulasan_id=%s ORDER BY id', (rid,))
    if lanj and lanj[-1]['dari'] == 'customer': raise ApiError('Tunggu balasan admin dulu.', 409)
    if sum(1 for x in lanj if x['dari'] == 'customer') >= 5: raise ApiError('Batas balasan untuk ulasan ini sudah tercapai.', 409)
    db.run('INSERT INTO ulasan_balas (ulasan_id,dari,user_id,teks,dibuat) VALUES (%s,%s,%s,%s,%s)', (rid, 'customer', uid, teks, now_ms()))
    return ok()


@api.get('/ulasan/sudah/<int:pid>', tags=['Ulasan'])
@siapa_saja
def sudah_ulas(u, pid):
    return ok({'sudah': bool(get_db().one('SELECT 1 AS x FROM ulasan WHERE user_id=%s AND produk_id=%s', (u['id'], pid)))})


# ---------------- Profil ----------------
@api.put('/profil', tags=['Akun'])
@siapa_saja
def profil(u):
    b = badan(ProfilIn)
    db = get_db()
    username, email, foto = b.username, b.email, b.foto
    if not username_ok(username): raise ApiError('Username 4–20 karakter (huruf, angka, garis bawah).')
    if not email_ok(email): raise ApiError('Format email tidak valid.')
    if email.strip().lower() != u['email'].lower():      # ganti email wajib lewat verifikasi OTP ke email baru
        raise ApiError('Email hanya bisa diganti lewat verifikasi kode OTP (tombol Ganti di samping email).')
    email = u['email']                                   # email tidak pernah diubah oleh endpoint ini
    if db.one('SELECT id FROM pengguna WHERE id<>%s AND LOWER(username)=LOWER(%s)', (u['id'], username)): raise ApiError('Username sudah dipakai.', 409)
    if db.one('SELECT id FROM pengguna WHERE id<>%s AND LOWER(email)=LOWER(%s)', (u['id'], email)): raise ApiError('Email sudah terdaftar.', 409)
    path_foto = u['foto']
    if foto:   # hanya unggahan baru (atau foto sendiri yang tak berubah); URL eksternal ditolak: pelacakan IP admin & kolom DB 255
        path_foto = resolve_gambar(foto, 'foto', saat_ini=u['foto'], boleh_url=False)
    db.run('UPDATE pengguna SET username=%s, email=%s, foto=%s WHERE id=%s', (username, email, path_foto, u['id']))
    if b.ada('alamat'):       # kunci ada: semua kosong = hapus alamat; selain itu divalidasi utuh
        isi = [str(getattr(b, k) or '').strip() for k in ('telepon', 'alamat', 'kota', 'kodePos')]
        if any(isi):
            a = baca_alamat(b.data(), perlu_penerima=False)
            db.run('UPDATE pengguna SET telepon=%s, alamat=%s, kota=%s, kode_pos=%s WHERE id=%s', (a['telepon'], a['alamat'], a['kota'], a['kode_pos'], u['id']))
        else:
            db.run('UPDATE pengguna SET telepon=NULL, alamat=NULL, kota=NULL, kode_pos=NULL WHERE id=%s', (u['id'],))
    if path_foto != u['foto']:
        db.commit(); hapus_media(u['foto'], db)     # hapus berkas lama hanya setelah basis data tersimpan
    return ok(user_out(db.one('SELECT * FROM pengguna WHERE id=%s', (u['id'],))))


# ---------------- Ganti email (verifikasi OTP ke email baru) ----------------
@api.post('/profil/email/minta', tags=['Akun'], summary='Ganti email langkah 1: password + email baru, kode OTP dikirim')
@siapa_saja
def email_minta(u):
    """Email lama tetap berlaku sampai kode benar."""
    b = badan(EmailMintaIn)
    batasi_laju('otp', cfg['LAJU_OTP'], 600)
    db = get_db()
    kunci = 'pw:' + str(u['id'])
    sisa = sisa_blokir(db, kunci)
    if sisa: raise ApiError(f'Terlalu banyak percobaan. Coba lagi {sisa} menit lagi.', 429)
    if not cek_pw(u['hash'], str(b.password or '')[:200]):
        catat_gagal(db, kunci); db.commit()
        raise ApiError('Password saat ini salah.', 403)          # 403 (bukan 401) agar frontend tidak mengira sesi berakhir
    reset_gagal(db, kunci)
    email = str(b.email or '').strip().lower()[:100]
    if not email_ok(email): raise ApiError('Format email tidak valid.')
    if email == u['email'].lower(): raise ApiError('Itu sudah email akunmu saat ini.')
    if db.one('SELECT id FROM pengguna WHERE id<>%s AND LOWER(email)=LOWER(%s)', (u['id'], email)): raise ApiError('Email sudah terdaftar.', 409)
    p, now = db.one('SELECT * FROM otp_email WHERE user_id=%s', (u['id'],)), now_ms()
    if p and now - p['kirim_terakhir'] < cfg['OTP_JEDA_DETIK'] * 1000:
        raise ApiError(f"Tunggu {max(1, -(-(p['kirim_terakhir'] + cfg['OTP_JEDA_DETIK'] * 1000 - now) // 1000))} detik sebelum meminta kode lagi.", 429)
    n = p['kirim_n'] if p and now - p['kirim_terakhir'] < 3_600_000 else 0       # jendela 1 jam
    if n >= cfg['OTP_MAKS_KIRIM']: raise ApiError('Batas pengiriman kode tercapai. Coba lagi dalam 1 jam.', 429)
    kode, garam = otp.buat_kode(), secrets.token_hex(16)
    nilai = (email, otp.hash_kode(email, kode, garam), garam, now + cfg['OTP_MENIT'] * 60000, n + 1, now)
    if p: db.run('UPDATE otp_email SET email=%s, kode_hash=%s, garam=%s, kedaluwarsa=%s, salah=0, kirim_n=%s, kirim_terakhir=%s WHERE user_id=%s', nilai + (u['id'],))
    else: db.run('INSERT INTO otp_email (email,kode_hash,garam,kedaluwarsa,salah,kirim_n,kirim_terakhir,user_id) VALUES (%s,%s,%s,%s,0,%s,%s,%s)', nilai + (u['id'],))
    otp.kirim_kode(email, u['username'], kode, perihal='penggantian email')
    return ok({'email': email, 'berlaku': cfg['OTP_MENIT'], 'jeda': cfg['OTP_JEDA_DETIK']})


@api.post('/profil/email/verifikasi', tags=['Akun'], summary='Ganti email langkah 2: kode OTP')
@siapa_saja
def email_verifikasi(u):
    """Kode benar -> email akun diganti, email lama diberi pemberitahuan."""
    b = badan(KodeSajaIn)
    batasi_laju('otp', cfg['LAJU_OTP'], 600)
    db = get_db()
    kode = re.sub(r'\s', '', str(b.kode or ''))
    if not re.fullmatch(r'\d{6}', kode): raise ApiError('Kode OTP terdiri dari 6 angka.')
    p = db.one('SELECT * FROM otp_email WHERE user_id=%s', (u['id'],))
    if not p: raise ApiError('Tidak ada permintaan ganti email. Mulai lagi dari awal.', 404)
    if p['kedaluwarsa'] < now_ms(): raise ApiError('Kode OTP sudah kedaluwarsa. Minta kode baru.', 400)
    if p['salah'] >= cfg['OTP_MAKS_SALAH']: raise ApiError('Terlalu banyak kode salah. Minta kode baru.', 429)
    if not otp.cocok(otp.hash_kode(p['email'], kode, p['garam']), p['kode_hash']):
        log.warning('OTP EMAIL SALAH user_id=%s ip=%s', u['id'], ip_klien())
        db.run('UPDATE otp_email SET salah=salah+1 WHERE user_id=%s', (u['id'],)); db.commit()
        sisa = cfg['OTP_MAKS_SALAH'] - p['salah'] - 1
        raise ApiError(f'Kode OTP salah. Sisa percobaan: {sisa}.' if sisa > 0 else 'Kode OTP salah. Minta kode baru.', 400)
    if db.one('SELECT id FROM pengguna WHERE id<>%s AND LOWER(email)=LOWER(%s)', (u['id'], p['email'])): raise ApiError('Email sudah terdaftar.', 409)
    db.run('UPDATE pengguna SET email=%s WHERE id=%s', (p['email'], u['id']))
    db.run('DELETE FROM otp_email WHERE user_id=%s', (u['id'],))
    db.commit()
    otp.kirim_info_email_diganti(u['email'], u['username'], p['email'])
    return ok(user_out(db.one('SELECT * FROM pengguna WHERE id=%s', (u['id'],))))
