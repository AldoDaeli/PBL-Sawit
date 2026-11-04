"""Fitur khusus admin: produk, pengguna, ulasan, pesan kontak. (Pesanan admin ada di pesanan.py.)"""
import json

from flask import request

from . import api, ok
from .. import aktivitas
from ..config import KATEGORI
from ..db import get_db
from ..errors import ApiError
from ..schemas import badan, ProdukIn, TeksIn
from ..security import now_ms, wajib
from ..serializers import user_out, produk_out, ulasan_out
from ..produk_service import ProdukService
from ..services import lanjutan_ulasan
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
def produk_buat(adm):
    b = badan(ProdukIn)
    db = get_db()
    d = _data_produk(b.data())
    if not b.gambar: raise ApiError('Foto produk wajib (URL https atau unggah gambar).')
    d['gambar'] = resolve_gambar(b.gambar, 'produk')
    db.commit()                                         # lepas transaksi koneksi mentah (sesi) sebelum sesi ORM menulis
    p = ProdukService.buat(d, now_ms())                 # INSERT lewat ORM
    aktivitas.catat(db, 'produk.tambah', adm, f'produk#{p.id}', {'nama': d['nama'], 'kategori': d['kategori'], 'harga': d['harga'], 'stok': d['stok'],
                                                            'best_seller': bool(d['best_seller']), 'deskripsi': aktivitas.ringkas(d['deskripsi'], 100)})
    return ok(produk_out(ProdukService.baris(p.id)))


@api.put('/admin/produk/<int:pid>', tags=['Admin'])
@admin_saja
def produk_ubah(adm, pid):
    b = badan(ProdukIn)
    db = get_db()
    db.commit()
    p = ProdukService.ambil(pid, kunci=True)
    if not p: raise ApiError('Produk tidak ditemukan.', 404)
    lama = {k: getattr(p, k) for k in p.KOLOM}          # salinan nilai lama untuk jejak audit
    d = _data_produk(b.data())
    d['gambar'] = resolve_gambar(b.gambar, 'produk', saat_ini=lama['gambar']) if b.gambar else lama['gambar']
    db.commit()                                         # resolve_gambar menulis tabel media lewat koneksi mentah: commit dulu agar tidak mengunci sesi ORM
    ProdukService.ubah(p, d)                            # UPDATE lewat ORM
    jejak = {}
    for k in ('nama', 'kategori', 'harga', 'stok', 'deskripsi', 'spesifikasi'):
        if lama[k] != d[k]: jejak[k] = [aktivitas.ringkas(str(lama[k]), 100), aktivitas.ringkas(str(d[k]), 100)] if k in ('deskripsi', 'spesifikasi') else [lama[k], d[k]]
    if bool(lama['best_seller']) != bool(d['best_seller']): jejak['best_seller'] = [bool(lama['best_seller']), bool(d['best_seller'])]
    if d['gambar'] != lama['gambar']: jejak['gambar'] = 'diganti'
    aktivitas.catat(db, 'produk.ubah', adm, f'produk#{pid}', {'nama': lama['nama'], 'perubahan': jejak or 'tidak ada perubahan'})
    if d['gambar'] != lama['gambar']:
        db.commit(); hapus_media(lama['gambar'], db)
    return ok(produk_out(ProdukService.baris(pid)))


@api.delete('/admin/produk/<int:pid>', tags=['Admin'])
@admin_saja
def produk_hapus(adm, pid):
    db = get_db()
    db.commit()
    p = ProdukService.ambil(pid)
    if not p: raise ApiError('Produk tidak ditemukan.', 404)
    ringkas = {'nama': p.nama, 'kategori': p.kategori, 'harga': p.harga, 'stok_terakhir': p.stok}; gambar = p.gambar
    ProdukService.hapus(p)                              # DELETE lewat ORM; keranjang/favorit/ulasan ikut terhapus (FK CASCADE)
    aktivitas.catat(db, 'produk.hapus', adm, f'produk#{pid}', ringkas)
    db.commit(); hapus_media(gambar, db)
    return ok()


# ---------------- Pengguna ----------------
@api.get('/admin/pengguna', tags=['Admin'])
@admin_saja
def pengguna_all(_):
    return ok([user_out(u) for u in get_db().all('SELECT * FROM pengguna WHERE peran=%s ORDER BY id', ('customer',))])


@api.post('/admin/pengguna/<int:uid>/toggle', tags=['Admin'])
@admin_saja
def pengguna_toggle(adm, uid):
    db = get_db()
    u = db.one('SELECT id, username, aktif FROM pengguna WHERE id=%s AND peran=%s FOR UPDATE', (uid, 'customer'))
    if not u: raise ApiError('Akun tidak dapat diubah.', 404)
    baru = 0 if u['aktif'] else 1
    db.run('UPDATE pengguna SET aktif=%s WHERE id=%s', (baru, uid))
    if not baru: db.run('DELETE FROM sesi WHERE user_id=%s', (uid,))     # akun dinonaktifkan -> langsung keluar
    aktivitas.catat(db, 'pengguna.aktifkan' if baru else 'pengguna.nonaktifkan', adm, f'pengguna#{uid}',
                    {'username': u['username'], 'sesi_dicabut': not baru})
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
    r = db.one('SELECT id, user_id, produk_id, balasan_teks FROM ulasan WHERE id=%s FOR UPDATE', (rid,))
    if not r: raise ApiError('Ulasan tidak ditemukan.', 404)
    if not 3 <= len(teks) <= 300: raise ApiError('Komentar 3–300 karakter.')
    lanj = db.all('SELECT dari FROM ulasan_balas WHERE ulasan_id=%s ORDER BY id', (rid,))
    if not lanj:
        db.run('UPDATE ulasan SET balasan_teks=%s, balasan_dibuat=%s WHERE id=%s', (teks, now_ms(), rid))
    elif lanj[-1]['dari'] == 'customer':
        db.run('INSERT INTO ulasan_balas (ulasan_id,dari,user_id,teks,dibuat) VALUES (%s,%s,%s,%s,%s)', (rid, 'admin', a['id'], teks, now_ms()))
    else:
        raise ApiError('Tunggu pelanggan membalas dulu.', 409)
    aktivitas.catat(db, 'ulasan.balas_admin', a, f'ulasan#{rid}', {'pelanggan_id': r['user_id'], 'produk_id': r['produk_id'], 'isi': aktivitas.ringkas(teks, 100),
                                                              'ubah_balasan': bool(not lanj and r['balasan_teks']), 'panjang': len(teks)})
    return ok()


@api.get('/admin/kontak', tags=['Admin'])
@admin_saja
def pesan_kontak(_):
    return ok(get_db().all('SELECT id, nama, email, jenis, isi, dibuat FROM pesan_kontak ORDER BY dibuat DESC'))


def _angka(v):
    """Parameter query opsional: bilangan bulat, atau None bila kosong/tidak valid (filter diabaikan)."""
    try: return int(v)
    except (TypeError, ValueError): return None


@api.get('/admin/log', tags=['Admin'], summary='Log audit seluruh aktivitas')
@admin_saja
def log_audit(_):
    """Filter (semua opsional): aksi (kode persis, mis. produk.hapus), kategori (auth, produk, pesanan, ...), peran (admin|customer|tamu|sistem),
    q (username / IP / target / isi detail), dari & sampai (ms epoch), hal, per (maks 200). Terbaru dulu.
    Respons: {total, hal, per, items: [{..., detail: {...}}]}."""
    a, db = request.args, get_db()
    syarat, arg = [], []
    for kolom in ('aksi', 'kategori', 'peran'):
        v = (a.get(kolom) or '').strip()[:40]
        if v: syarat.append(kolom + '=%s'); arg.append(v)
    q = (a.get('q') or '').strip()[:60]
    if q: syarat.append('(username LIKE %s OR ip LIKE %s OR target LIKE %s OR detail LIKE %s)'); arg += ['%' + q + '%'] * 4
    dari, sampai = _angka(a.get('dari')), _angka(a.get('sampai'))
    if dari is not None: syarat.append('waktu>=%s'); arg.append(dari)
    if sampai is not None: syarat.append('waktu<=%s'); arg.append(sampai)
    where = (' WHERE ' + ' AND '.join(syarat)) if syarat else ''
    per = min(max(_angka(a.get('per')) or 50, 1), 200); hal = max(_angka(a.get('hal')) or 1, 1)
    total = db.one('SELECT COUNT(*) AS n FROM log_audit' + where, tuple(arg))['n']
    rows = db.all('SELECT id, user_id, username, peran, aksi, kategori, target, detail, ip, perangkat, waktu FROM log_audit' + where +
                  ' ORDER BY waktu DESC, id DESC LIMIT %s OFFSET %s', tuple(arg) + (per, (hal - 1) * per))

    def detail(t):
        try: return json.loads(t) if t else {}
        except ValueError: return {'mentah': t}
    return ok({'total': total, 'hal': hal, 'per': per,
               'items': [{'id': r['id'], 'userId': r['user_id'], 'username': r['username'], 'peran': r['peran'], 'aksi': r['aksi'],
                          'kategori': r['kategori'], 'target': r['target'], 'detail': detail(r['detail']),
                          'ip': r['ip'], 'perangkat': r['perangkat'], 'waktu': r['waktu']} for r in rows]})
