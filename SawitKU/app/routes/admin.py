"""Fitur khusus admin: produk, pengguna, ulasan, pesan kontak. (Pesanan admin ada di pesanan.py.)"""
import json


from . import api, ok
from ..config import KATEGORI
from ..db import get_db
from ..errors import ApiError
from ..schemas import badan, ProdukIn, TeksIn
from ..security import now_ms, wajib
from ..serializers import user_out, produk_out, ulasan_out
from ..services import PRODUK_SQL, lanjutan_ulasan
from ..uploads import resolve_gambar, hapus_media
from ..validators import to_int

admin_saja = wajib('admin')


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


@api.post('/admin/produk', status_code=201, tags=['Admin'])
@admin_saja
def produk_buat(_):
    b = badan(ProdukIn)
    db = get_db()
    d = _data_produk(b.data())
    if not b.gambar: raise ApiError('Foto produk wajib (URL https atau unggah gambar).')
    d['gambar'] = resolve_gambar(b.gambar, 'produk')
    pid, _ = db.run('INSERT INTO produk (nama,kategori,harga,stok,terjual,rating,best_seller,gambar,deskripsi,spesifikasi,dibuat) '
                    'VALUES (%s,%s,%s,%s,0,0,%s,%s,%s,%s,%s)',
                    (d['nama'], d['kategori'], d['harga'], d['stok'], d['best_seller'], d['gambar'], d['deskripsi'], d['spesifikasi'], now_ms()))
    return ok(produk_out(db.one(PRODUK_SQL + ' WHERE p.id=%s', (pid,))))


@api.put('/admin/produk/<int:pid>', tags=['Admin'])
@admin_saja
def produk_ubah(_, pid):
    b = badan(ProdukIn)
    db = get_db()
    lama = db.one('SELECT * FROM produk WHERE id=%s FOR UPDATE', (pid,))
    if not lama: raise ApiError('Produk tidak ditemukan.', 404)
    d = _data_produk(b.data())
    d['gambar'] = resolve_gambar(b.gambar, 'produk', saat_ini=lama['gambar']) if b.gambar else lama['gambar']
    db.run('UPDATE produk SET nama=%s,kategori=%s,harga=%s,stok=%s,best_seller=%s,gambar=%s,deskripsi=%s,spesifikasi=%s WHERE id=%s',
           (d['nama'], d['kategori'], d['harga'], d['stok'], d['best_seller'], d['gambar'], d['deskripsi'], d['spesifikasi'], pid))
    if d['gambar'] != lama['gambar']:
        db.commit(); hapus_media(lama['gambar'], db)
    return ok(produk_out(db.one(PRODUK_SQL + ' WHERE p.id=%s', (pid,))))


@api.delete('/admin/produk/<int:pid>', tags=['Admin'])
@admin_saja
def produk_hapus(_, pid):
    db = get_db()
    p = db.one('SELECT gambar FROM produk WHERE id=%s', (pid,))
    if not p: raise ApiError('Produk tidak ditemukan.', 404)
    db.run('DELETE FROM produk WHERE id=%s', (pid,))   # keranjang/favorit/ulasan ikut terhapus; riwayat pesanan tetap (salinan item)
    db.commit(); hapus_media(p['gambar'], db)
    return ok()


# ---------------- Pengguna ----------------
@api.get('/admin/pengguna', tags=['Admin'])
@admin_saja
def pengguna_all(_):
    return ok([user_out(u) for u in get_db().all('SELECT * FROM pengguna WHERE peran=%s ORDER BY id', ('customer',))])


@api.post('/admin/pengguna/<int:uid>/toggle', tags=['Admin'])
@admin_saja
def pengguna_toggle(_, uid):
    db = get_db()
    u = db.one('SELECT id, aktif FROM pengguna WHERE id=%s AND peran=%s FOR UPDATE', (uid, 'customer'))
    if not u: raise ApiError('Akun tidak dapat diubah.', 404)
    baru = 0 if u['aktif'] else 1
    db.run('UPDATE pengguna SET aktif=%s WHERE id=%s', (baru, uid))
    if not baru: db.run('DELETE FROM sesi WHERE user_id=%s', (uid,))     # akun dinonaktifkan -> langsung keluar
    return ok({'aktif': bool(baru)})


# ---------------- Ulasan & kontak ----------------
@api.get('/admin/ulasan', tags=['Admin'])
@admin_saja
def ulasan_all(_):
    rows = get_db().all('SELECT r.*, u.username AS nama, p.nama AS produk_nama FROM ulasan r '
                        'JOIN pengguna u ON u.id=r.user_id LEFT JOIN produk p ON p.id=r.produk_id ORDER BY r.dibuat DESC')
    lj = lanjutan_ulasan(get_db(), [r['id'] for r in rows])
    return ok([{**ulasan_out(r, lj.get(r['id'])), 'produk': r['produk_nama'] or '-'} for r in rows])


@api.post('/admin/ulasan/<int:rid>/balas', tags=['Admin'])
@admin_saja
def ulasan_balas(a, rid):
    """Balasan pertama admin disimpan di ulasan (boleh diubah selama pelanggan belum membalas).
    Setelah pelanggan membalas, balasan admin berikutnya ditambahkan sebagai percakapan lanjutan."""
    b = badan(TeksIn)
    db = get_db()
    teks = str(b.teks or '').strip()
    r = db.one('SELECT id, balasan_teks FROM ulasan WHERE id=%s FOR UPDATE', (rid,))
    if not r: raise ApiError('Ulasan tidak ditemukan.', 404)
    if not 3 <= len(teks) <= 300: raise ApiError('Komentar 3–300 karakter.')
    lanj = db.all('SELECT dari FROM ulasan_balas WHERE ulasan_id=%s ORDER BY id', (rid,))
    if not lanj:
        db.run('UPDATE ulasan SET balasan_teks=%s, balasan_dibuat=%s WHERE id=%s', (teks, now_ms(), rid))
    elif lanj[-1]['dari'] == 'customer':
        db.run('INSERT INTO ulasan_balas (ulasan_id,dari,user_id,teks,dibuat) VALUES (%s,%s,%s,%s,%s)', (rid, 'admin', a['id'], teks, now_ms()))
    else:
        raise ApiError('Tunggu pelanggan membalas dulu.', 409)
    return ok()


@api.get('/admin/kontak', tags=['Admin'])
@admin_saja
def pesan_kontak(_):
    return ok(get_db().all('SELECT id, nama, email, jenis, isi, dibuat FROM pesan_kontak ORDER BY dibuat DESC'))
