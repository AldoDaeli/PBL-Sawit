"""Fitur khusus admin: pesanan, produk, pengguna, ulasan, pesan kontak."""
import json
from . import bp, body, ok
from ..config import KATEGORI
from ..db import get_db
from ..errors import ApiError
from ..security import now_ms, wajib
from ..serializers import user_out, produk_out, ulasan_out
from ..services import sapu, muat_pesanan, batalkan, lunas, lanjutan_ulasan
from ..uploads import resolve_gambar, hapus_media
from flask import current_app, g
import re
from ..validators import to_int


# ---------------- Pesanan ----------------
@bp.get('/admin/pesanan')
@wajib('admin')
def admin_pesanan():
    db = get_db(); sapu(db)
    rows = db.all('SELECT o.*, u.username AS pembeli FROM pesanan o LEFT JOIN pengguna u ON u.id=o.user_id ORDER BY o.dibuat DESC, o.id DESC')
    return ok(muat_pesanan(db, rows, lambda o: {'pembeli': o['pembeli'] or '-'}))


@bp.post('/admin/pesanan/<int:oid>/verifikasi')
@wajib('admin')
def verifikasi(oid):
    db, b = get_db(), body()
    o = db.one('SELECT * FROM pesanan WHERE id=%s FOR UPDATE', (oid,))
    if not o or o['status'] != 'menunggu_verifikasi': raise ApiError('Pesanan tidak menunggu verifikasi.', 409)
    if b.get('setuju') is True:
        lunas(db, o, o['metode'] or 'qris')
    else:
        # Ditolak: pesanan TIDAK dibatalkan. Kembali ke 'menunggu_bayar' dengan alasan, supaya pembeli bisa mengunggah ulang bukti.
        alasan = (str(b.get('alasan') or '').strip()[:200]) or 'Bukti pembayaran tidak sesuai.'
        now = now_ms()
        db.run('UPDATE pesanan SET status=%s, alasan=%s, ditolak=ditolak+1, bukti=NULL, t_bayar=NULL, batas_bayar=%s WHERE id=%s',
               ('menunggu_bayar', alasan, now + current_app.config['BATAS_BAYAR_JAM'] * 3600000, oid))
        db.commit(); hapus_media(o['bukti'], db)
    return ok()


@bp.post('/admin/pesanan/<int:oid>/kirim')
@wajib('admin')
def kirim_pesanan(oid):
    db, b = get_db(), body()
    kurir, resi = str(b.get('kurir') or '').strip()[:30], re.sub(r'\s', '', str(b.get('resi') or '')).upper()
    if not 2 <= len(kurir) <= 30: raise ApiError('Isi nama kurir (mis. JNE, J&T, SiCepat).')
    if not re.fullmatch(r'[A-Z0-9\-]{5,40}', resi): raise ApiError('Nomor resi 5–40 karakter (huruf, angka, strip).')
    o = db.one('SELECT status FROM pesanan WHERE id=%s FOR UPDATE', (oid,))
    if not o or o['status'] != 'diproses': raise ApiError('Pesanan belum siap dikirim.', 409)
    if db.one('SELECT 1 AS x FROM pesanan WHERE resi=%s AND id<>%s', (resi, oid)): raise ApiError('Nomor resi itu sudah dipakai pesanan lain.', 409)
    db.run('UPDATE pesanan SET status=%s, kurir=%s, resi=%s, t_kirim=%s WHERE id=%s', ('dikirim', kurir, resi, now_ms(), oid))
    return ok()


# ---------------- Produk ----------------
def _data_produk(b):
    nama = str(b.get('nama') or '').strip()
    harga, stok = to_int(b.get('harga'), 'Harga tidak valid.'), to_int(b.get('stok'), 'Stok tidak valid.')
    if not 3 <= len(nama) <= 80: raise ApiError('Nama produk 3–80 karakter.')
    if b.get('kategori') not in KATEGORI: raise ApiError('Kategori tidak valid.')
    if not 1000 <= harga <= 100_000_000: raise ApiError('Harga tidak valid.')
    if not 0 <= stok <= 100_000: raise ApiError('Stok tidak valid.')
    spes = {}
    if isinstance(b.get('spesifikasi'), dict):
        pairs = [(str(k)[:30], str(v)[:120]) for k, v in b['spesifikasi'].items()]
    else:   # format teks "Nama: nilai" per baris, seperti form admin. Baris yang salah format DITOLAK dengan pesan, bukan dibuang diam-diam
        pairs = []
        for n, l in enumerate(str(b.get('spek') or '').splitlines(), 1):
            if not l.strip(): continue
            a, sep, v = l.partition(':')
            if not sep: a, sep, v = l.partition('=')
            if not (a.strip() and v.strip()):
                raise ApiError(f'Spesifikasi baris {n} harus berbentuk "Nama: nilai", contoh "Tinggi: 40 cm".')
            if len(a.strip()) > 30 or len(v.strip()) > 120:
                raise ApiError(f'Spesifikasi baris {n} terlalu panjang (nama maks 30 karakter, nilai maks 120 karakter).')
            pairs.append((a, v))
    if len(pairs) > 12: raise ApiError('Spesifikasi maksimal 12 baris.')
    for k, v in pairs: spes[k.strip()] = v.strip()
    return dict(nama=nama, kategori=b['kategori'], harga=harga, stok=stok, deskripsi=str(b.get('deskripsi') or '').strip()[:400],
                spesifikasi=json.dumps(spes, ensure_ascii=False), best_seller=1 if b.get('bestSeller') else 0)


@bp.post('/admin/produk')
@wajib('admin')
def produk_buat():
    db, b = get_db(), body()
    d = _data_produk(b)
    if not b.get('gambar'): raise ApiError('Foto produk wajib (URL https atau unggah gambar).')
    d['gambar'] = resolve_gambar(b['gambar'], 'produk')
    pid, _ = db.run('INSERT INTO produk (nama,kategori,harga,stok,terjual,rating,best_seller,gambar,deskripsi,spesifikasi,dibuat) '
                    'VALUES (%s,%s,%s,%s,0,4.5,%s,%s,%s,%s,%s)',
                    (d['nama'], d['kategori'], d['harga'], d['stok'], d['best_seller'], d['gambar'], d['deskripsi'], d['spesifikasi'], now_ms()))
    return ok(produk_out(db.one('SELECT * FROM produk WHERE id=%s', (pid,))), 201)


@bp.put('/admin/produk/<int:pid>')
@wajib('admin')
def produk_ubah(pid):
    db, b = get_db(), body()
    lama = db.one('SELECT * FROM produk WHERE id=%s FOR UPDATE', (pid,))
    if not lama: raise ApiError('Produk tidak ditemukan.', 404)
    d = _data_produk(b)
    d['gambar'] = resolve_gambar(b['gambar'], 'produk', saat_ini=lama['gambar']) if b.get('gambar') else lama['gambar']
    db.run('UPDATE produk SET nama=%s,kategori=%s,harga=%s,stok=%s,best_seller=%s,gambar=%s,deskripsi=%s,spesifikasi=%s WHERE id=%s',
           (d['nama'], d['kategori'], d['harga'], d['stok'], d['best_seller'], d['gambar'], d['deskripsi'], d['spesifikasi'], pid))
    if d['gambar'] != lama['gambar']:
        db.commit(); hapus_media(lama['gambar'], db)
    return ok(produk_out(db.one('SELECT * FROM produk WHERE id=%s', (pid,))))


@bp.delete('/admin/produk/<int:pid>')
@wajib('admin')
def produk_hapus(pid):
    db = get_db()
    p = db.one('SELECT gambar FROM produk WHERE id=%s', (pid,))
    if not p: raise ApiError('Produk tidak ditemukan.', 404)
    db.run('DELETE FROM produk WHERE id=%s', (pid,))   # keranjang/favorit/ulasan ikut terhapus; riwayat pesanan tetap (salinan item)
    db.commit(); hapus_media(p['gambar'], db)
    return ok()


# ---------------- Pengguna ----------------
@bp.get('/admin/pengguna')
@wajib('admin')
def pengguna_all():
    return ok([user_out(u) for u in get_db().all('SELECT * FROM pengguna WHERE peran=%s ORDER BY id', ('customer',))])


@bp.post('/admin/pengguna/<int:uid>/toggle')
@wajib('admin')
def pengguna_toggle(uid):
    db = get_db()
    u = db.one('SELECT id, aktif FROM pengguna WHERE id=%s AND peran=%s FOR UPDATE', (uid, 'customer'))
    if not u: raise ApiError('Akun tidak dapat diubah.', 404)
    baru = 0 if u['aktif'] else 1
    db.run('UPDATE pengguna SET aktif=%s WHERE id=%s', (baru, uid))
    if not baru: db.run('DELETE FROM sesi WHERE user_id=%s', (uid,))     # akun dinonaktifkan -> langsung keluar
    return ok({'aktif': bool(baru)})


# ---------------- Ulasan & kontak ----------------
@bp.get('/admin/ulasan')
@wajib('admin')
def ulasan_all():
    rows = get_db().all('SELECT r.*, u.username AS nama, p.nama AS produk_nama FROM ulasan r '
                        'JOIN pengguna u ON u.id=r.user_id LEFT JOIN produk p ON p.id=r.produk_id ORDER BY r.dibuat DESC')
    lj = lanjutan_ulasan(get_db(), [r['id'] for r in rows])
    return ok([{**ulasan_out(r, lj.get(r['id'])), 'produk': r['produk_nama'] or '-'} for r in rows])


@bp.post('/admin/ulasan/<int:rid>/balas')
@wajib('admin')
def ulasan_balas(rid):
    """Balasan pertama admin disimpan di ulasan (boleh diubah selama pelanggan belum membalas).
    Setelah pelanggan membalas, balasan admin berikutnya ditambahkan sebagai percakapan lanjutan."""
    db = get_db()
    teks = str(body().get('teks') or '').strip()
    r = db.one('SELECT id, balasan_teks FROM ulasan WHERE id=%s FOR UPDATE', (rid,))
    if not r: raise ApiError('Ulasan tidak ditemukan.', 404)
    if not 3 <= len(teks) <= 300: raise ApiError('Komentar 3–300 karakter.')
    lanj = db.all('SELECT dari FROM ulasan_balas WHERE ulasan_id=%s ORDER BY id', (rid,))
    if not lanj:
        db.run('UPDATE ulasan SET balasan_teks=%s, balasan_dibuat=%s WHERE id=%s', (teks, now_ms(), rid))
    elif lanj[-1]['dari'] == 'customer':
        db.run('INSERT INTO ulasan_balas (ulasan_id,dari,user_id,teks,dibuat) VALUES (%s,%s,%s,%s,%s)', (rid, 'admin', g.user['id'], teks, now_ms()))
    else:
        raise ApiError('Tunggu pelanggan membalas dulu.', 409)
    return ok()


@bp.get('/admin/kontak')
@wajib('admin')
def pesan_kontak():
    return ok(get_db().all('SELECT id, nama, email, jenis, isi, dibuat FROM pesan_kontak ORDER BY dibuat DESC'))
