"""Fitur khusus akun customer: favorit, keranjang, checkout, pesanan, ulasan, profil."""
from flask import g, current_app, request
from . import bp, body, ok
from ..db import get_db, IntegrityErrors
from ..errors import ApiError
import re, secrets
from .. import otp
from ..security import now_ms, wajib, cek_pw, batasi_laju, sisa_blokir, catat_gagal, reset_gagal
from ..serializers import user_out, produk_out
from ..services import sapu, muat_pesanan, batalkan, hitung_rating
from ..uploads import simpan_data_url, resolve_gambar, hapus_media
from ..validators import username_ok, email_ok, password_ok, to_int, baca_alamat


# ---------------- Favorit ----------------
@bp.get('/favorit')
@wajib()
def favorit():
    return ok([r['produk_id'] for r in get_db().all('SELECT produk_id FROM favorit WHERE user_id=%s ORDER BY produk_id', (g.user['id'],))])


@bp.post('/favorit/<int:pid>/toggle')
@wajib('customer')
def fav_toggle(pid):
    db, uid = get_db(), g.user['id']
    if not db.one('SELECT id FROM produk WHERE id=%s', (pid,)): raise ApiError('Produk tidak ditemukan.', 404)
    if db.one('SELECT 1 AS x FROM favorit WHERE user_id=%s AND produk_id=%s', (uid, pid)):
        db.run('DELETE FROM favorit WHERE user_id=%s AND produk_id=%s', (uid, pid)); return ok({'aktif': False})
    db.run('INSERT INTO favorit (user_id,produk_id) VALUES (%s,%s)', (uid, pid)); return ok({'aktif': True})


# ---------------- Keranjang ----------------
@bp.get('/keranjang')
@wajib('customer')
def keranjang():
    rows = get_db().all('SELECT k.qty, p.* FROM keranjang k JOIN produk p ON p.id=k.produk_id WHERE k.user_id=%s ORDER BY p.id', (g.user['id'],))
    return ok([{'produkId': r['id'], 'qty': r['qty'], 'p': produk_out(r)} for r in rows])


@bp.post('/keranjang')
@wajib('customer')
def ker_add():
    db, b, uid = get_db(), body(), g.user['id']
    pid, qty = to_int(b.get('produkId'), 'Data produk tidak valid.'), to_int(b.get('qty', 1), 'Data produk tidak valid.')
    p = db.one('SELECT id, stok FROM produk WHERE id=%s', (pid,))
    if not p or qty <= 0: raise ApiError('Data produk tidak valid.')
    c = db.one('SELECT qty FROM keranjang WHERE user_id=%s AND produk_id=%s', (uid, pid))
    n = (c['qty'] if c else 0) + qty
    if n > p['stok']: raise ApiError(f"Stok hanya tersisa {p['stok']}.", 409)
    if c: db.run('UPDATE keranjang SET qty=%s WHERE user_id=%s AND produk_id=%s', (n, uid, pid))
    else: db.run('INSERT INTO keranjang (user_id,produk_id,qty) VALUES (%s,%s,%s)', (uid, pid, n))
    return ok(None, 201)


@bp.put('/keranjang/<int:pid>')
@wajib('customer')
def ker_set(pid):
    db, uid = get_db(), g.user['id']
    qty = to_int(body().get('qty'), 'Jumlah tidak valid.')
    p = db.one('SELECT stok FROM produk WHERE id=%s', (pid,))
    if not p or qty < 1 or qty > p['stok']: raise ApiError(f"Jumlah harus 1–{p['stok'] if p else 0}.")
    _, n = db.run('UPDATE keranjang SET qty=%s WHERE user_id=%s AND produk_id=%s', (qty, uid, pid))
    if not n and not db.one('SELECT 1 AS x FROM keranjang WHERE user_id=%s AND produk_id=%s', (uid, pid)):
        raise ApiError('Produk tidak ada di keranjang.', 404)
    return ok()


@bp.delete('/keranjang/<int:pid>')
@wajib('customer')
def ker_hapus(pid):
    get_db().run('DELETE FROM keranjang WHERE user_id=%s AND produk_id=%s', (g.user['id'], pid))
    return ok()


# ---------------- Checkout & pesanan ----------------
@bp.post('/checkout')
@wajib('customer')
def checkout():
    """Harga & stok dihitung dari database, bukan dari klien. Semua dalam satu transaksi dengan penguncian baris.
    Body wajib berisi alamat tujuan: penerima, telepon, alamat, kota, kodePos (+ simpan=true untuk menjadikannya alamat profil)."""
    db, uid, cfg, b = get_db(), g.user['id'], current_app.config, body()
    tujuan = baca_alamat(b)
    sapu(db)
    rows = db.all('SELECT k.qty, p.id, p.nama, p.gambar, p.harga, p.stok FROM keranjang k JOIN produk p ON p.id=k.produk_id '
                  'WHERE k.user_id=%s ORDER BY p.id FOR UPDATE', (uid,))
    if not rows: raise ApiError('Keranjang kosong.')
    for r in rows:
        if r['qty'] > r['stok']: raise ApiError(f"Stok {r['nama']} tidak mencukupi.", 409)
    # Stok langsung dipesan saat checkout; tanpa batas ini satu akun bisa menimbun seluruh stok tanpa membayar.
    if db.one('SELECT COUNT(*) AS n FROM pesanan WHERE user_id=%s AND status=%s', (uid, 'menunggu_bayar'))['n'] >= cfg['MAKS_PESANAN_TERTUNDA']:
        raise ApiError('Bayar atau batalkan pesananmu yang belum dibayar sebelum membuat pesanan baru.', 409)
    now = now_ms()
    total = sum(r['harga'] * r['qty'] for r in rows)
    oid, _ = db.run('INSERT INTO pesanan (user_id,total,status,alasan,penerima,telepon,alamat,kota,kode_pos,dibuat,batas_bayar) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (uid, total, 'menunggu_bayar', '', tujuan['penerima'], tujuan['telepon'], tujuan['alamat'], tujuan['kota'],
                     tujuan['kode_pos'], now, now + cfg['BATAS_BAYAR_JAM'] * 3600000))
    if b.get('simpan') is True:
        db.run('UPDATE pengguna SET telepon=%s, alamat=%s, kota=%s, kode_pos=%s WHERE id=%s',
               (tujuan['telepon'], tujuan['alamat'], tujuan['kota'], tujuan['kode_pos'], uid))
    for r in rows:
        db.run('INSERT INTO pesanan_item (pesanan_id,produk_id,nama,gambar,harga,qty) VALUES (%s,%s,%s,%s,%s,%s)',
               (oid, r['id'], r['nama'], r['gambar'], r['harga'], r['qty']))
        _, n = db.run('UPDATE produk SET stok = stok - %s WHERE id=%s AND stok >= %s', (r['qty'], r['id'], r['qty']))
        if n != 1: raise ApiError(f"Stok {r['nama']} tidak mencukupi.", 409)   # galat -> seluruh transaksi di-rollback
    db.run('DELETE FROM keranjang WHERE user_id=%s', (uid,))
    return ok(muat_pesanan(db, [db.one('SELECT * FROM pesanan WHERE id=%s', (oid,))])[0], 201)


@bp.get('/pesanan/saya')
@wajib('customer')
def pesanan_saya():
    db = get_db(); sapu(db)
    return ok(muat_pesanan(db, db.all('SELECT * FROM pesanan WHERE user_id=%s ORDER BY dibuat DESC, id DESC', (g.user['id'],))))


def _milik(db, oid):
    o = db.one('SELECT * FROM pesanan WHERE id=%s AND user_id=%s FOR UPDATE', (oid, g.user['id']))
    if not o: raise ApiError('Pesanan tidak ditemukan.', 404)
    return o


@bp.post('/pesanan/<int:oid>/bayar')
@wajib('customer')
def bayar(oid):
    db = get_db(); sapu(db)
    o = _milik(db, oid)
    if o['status'] != 'menunggu_bayar': raise ApiError('Pesanan tidak dapat dibayar.', 409)
    path = simpan_data_url(body().get('bukti'), 'bukti')
    db.run('UPDATE pesanan SET bukti=%s, status=%s WHERE id=%s', (path, 'menunggu_verifikasi', oid))
    return ok()


@bp.post('/pesanan/<int:oid>/batal')
@wajib('customer')
def batal(oid):
    db = get_db(); o = _milik(db, oid)
    if o['status'] != 'menunggu_bayar': raise ApiError('Pesanan tidak dapat dibatalkan.', 409)
    batalkan(db, o, 'Dibatalkan oleh pembeli.')
    return ok()


@bp.post('/pesanan/<int:oid>/terima')
@wajib('customer')
def terima(oid):
    db = get_db(); o = _milik(db, oid)
    if o['status'] != 'dikirim': raise ApiError('Pesanan belum dikirim.', 409)
    db.run('UPDATE pesanan SET status=%s WHERE id=%s', ('selesai', oid))
    return ok()


# ---------------- Ulasan ----------------
@bp.post('/ulasan')
@wajib('customer')
def kirim_ulasan():
    db, b, uid = get_db(), body(), g.user['id']
    pid = to_int(b.get('produkId'), 'Produk tidak valid.')
    rating = to_int(b.get('rating'), 'Pilih rating 1–5.')
    teks = str(b.get('teks') or '').strip()
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
    return ok(None, 201)


@bp.get('/ulasan/sudah/<int:pid>')
@wajib()
def sudah_ulas(pid):
    return ok({'sudah': bool(get_db().one('SELECT 1 AS x FROM ulasan WHERE user_id=%s AND produk_id=%s', (g.user['id'], pid)))})


# ---------------- Profil ----------------
@bp.put('/profil')
@wajib()
def profil():
    db, b, u = get_db(), body(), g.user
    username, email, foto = b.get('username'), b.get('email'), b.get('foto')
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
    if 'alamat' in b:       # kunci ada: semua kosong = hapus alamat; selain itu divalidasi utuh
        isi = [str(b.get(k) or '').strip() for k in ('telepon', 'alamat', 'kota', 'kodePos')]
        if any(isi):
            a = baca_alamat(b, perlu_penerima=False)
            db.run('UPDATE pengguna SET telepon=%s, alamat=%s, kota=%s, kode_pos=%s WHERE id=%s', (a['telepon'], a['alamat'], a['kota'], a['kode_pos'], u['id']))
        else:
            db.run('UPDATE pengguna SET telepon=NULL, alamat=NULL, kota=NULL, kode_pos=NULL WHERE id=%s', (u['id'],))
    if path_foto != u['foto']:
        db.commit(); hapus_media(u['foto'], db)     # hapus berkas lama hanya setelah basis data tersimpan
    return ok(user_out(db.one('SELECT * FROM pengguna WHERE id=%s', (u['id'],))))


# ---------------- Ganti email (verifikasi OTP ke email baru) ----------------
@bp.post('/profil/email/minta')
@wajib()
def email_minta():
    """Langkah 1: password saat ini + email baru -> kode OTP dikirim ke email BARU. Email lama tetap berlaku sampai kode benar."""
    c = current_app.config
    batasi_laju('otp', c['LAJU_OTP'], 600)
    db, b, u = get_db(), body(), g.user
    kunci = 'pw:' + str(u['id'])
    sisa = sisa_blokir(db, kunci)
    if sisa: raise ApiError(f'Terlalu banyak percobaan. Coba lagi {sisa} menit lagi.', 429)
    if not cek_pw(u['hash'], str(b.get('password') or '')[:200]):
        catat_gagal(db, kunci); db.commit()
        raise ApiError('Password saat ini salah.', 403)          # 403 (bukan 401) agar frontend tidak mengira sesi berakhir
    reset_gagal(db, kunci)
    email = str(b.get('email') or '').strip().lower()[:100]
    if not email_ok(email): raise ApiError('Format email tidak valid.')
    if email == u['email'].lower(): raise ApiError('Itu sudah email akunmu saat ini.')
    if db.one('SELECT id FROM pengguna WHERE id<>%s AND LOWER(email)=LOWER(%s)', (u['id'], email)): raise ApiError('Email sudah terdaftar.', 409)
    p, now = db.one('SELECT * FROM otp_email WHERE user_id=%s', (u['id'],)), now_ms()
    if p and now - p['kirim_terakhir'] < c['OTP_JEDA_DETIK'] * 1000:
        raise ApiError(f"Tunggu {max(1, -(-(p['kirim_terakhir'] + c['OTP_JEDA_DETIK'] * 1000 - now) // 1000))} detik sebelum meminta kode lagi.", 429)
    n = p['kirim_n'] if p and now - p['kirim_terakhir'] < 3_600_000 else 0       # jendela 1 jam
    if n >= c['OTP_MAKS_KIRIM']: raise ApiError('Batas pengiriman kode tercapai. Coba lagi dalam 1 jam.', 429)
    kode, garam = otp.buat_kode(), secrets.token_hex(16)
    nilai = (email, otp.hash_kode(email, kode, garam), garam, now + c['OTP_MENIT'] * 60000, n + 1, now)
    if p: db.run('UPDATE otp_email SET email=%s, kode_hash=%s, garam=%s, kedaluwarsa=%s, salah=0, kirim_n=%s, kirim_terakhir=%s WHERE user_id=%s', nilai + (u['id'],))
    else: db.run('INSERT INTO otp_email (email,kode_hash,garam,kedaluwarsa,salah,kirim_n,kirim_terakhir,user_id) VALUES (%s,%s,%s,%s,0,%s,%s,%s)', nilai + (u['id'],))
    otp.kirim_kode(email, u['username'], kode, perihal='penggantian email')
    return ok({'email': email, 'berlaku': c['OTP_MENIT'], 'jeda': c['OTP_JEDA_DETIK']})


@bp.post('/profil/email/verifikasi')
@wajib()
def email_verifikasi():
    """Langkah 2: kode benar -> email akun diganti, email lama diberi pemberitahuan."""
    c = current_app.config
    batasi_laju('otp', c['LAJU_OTP'], 600)
    db, u = get_db(), g.user
    kode = re.sub(r'\s', '', str(body().get('kode') or ''))
    if not re.fullmatch(r'\d{6}', kode): raise ApiError('Kode OTP terdiri dari 6 angka.')
    p = db.one('SELECT * FROM otp_email WHERE user_id=%s', (u['id'],))
    if not p: raise ApiError('Tidak ada permintaan ganti email. Mulai lagi dari awal.', 404)
    if p['kedaluwarsa'] < now_ms(): raise ApiError('Kode OTP sudah kedaluwarsa. Minta kode baru.', 400)
    if p['salah'] >= c['OTP_MAKS_SALAH']: raise ApiError('Terlalu banyak kode salah. Minta kode baru.', 429)
    if not otp.cocok(otp.hash_kode(p['email'], kode, p['garam']), p['kode_hash']):
        current_app.logger.warning('OTP EMAIL SALAH user_id=%s ip=%s', u['id'], request.remote_addr)
        db.run('UPDATE otp_email SET salah=salah+1 WHERE user_id=%s', (u['id'],)); db.commit()
        sisa = c['OTP_MAKS_SALAH'] - p['salah'] - 1
        raise ApiError(f'Kode OTP salah. Sisa percobaan: {sisa}.' if sisa > 0 else 'Kode OTP salah. Minta kode baru.', 400)
    if db.one('SELECT id FROM pengguna WHERE id<>%s AND LOWER(email)=LOWER(%s)', (u['id'], p['email'])): raise ApiError('Email sudah terdaftar.', 409)
    db.run('UPDATE pengguna SET email=%s WHERE id=%s', (p['email'], u['id']))
    db.run('DELETE FROM otp_email WHERE user_id=%s', (u['id'],))
    db.commit()
    otp.kirim_info_email_diganti(u['email'], u['username'], p['email'])
    return ok(user_out(db.one('SELECT * FROM pengguna WHERE id=%s', (u['id'],))))
