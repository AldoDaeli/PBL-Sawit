"""Data awal contoh SawitKu: 12 produk, 3 akun demo, pesanan, ulasan."""
import json, os, random, secrets, time
from .config import KATEGORI
from .security import hash_pw

HARI = 86_400_000
AKUN = [  # (username, email, password, peran, umur_hari)
    ('admin', 'admin@sawitku.id', 'Admin12345', 'admin', 200),
    ('budi_santoso', 'budi@mail.com', 'Budi12345', 'customer', 90),
    ('siti_aulia', 'siti@mail.com', 'Siti12345', 'customer', 60),
]
ALAMAT = {  # id pengguna -> alamat demo (hanya contoh; ganti/hapus akun demo sebelum produksi)
    2: ('Budi Santoso', '081234567801', 'Jl. Merdeka No. 12, RT 03/RW 05, Kel. Sukajadi', 'Kota Bandung', '40162'),
    3: ('Siti Aulia', '081234567802', 'Jl. Melati Raya No. 7, Perum Griya Asri Blok C', 'Kota Batam', '29444'),
}
# (pembeli, [(produk_id, qty)], umur_hari, status, alasan)
PESANAN = [
    (2, [(1, 1), (10, 1)], 75, 'selesai', ''), (2, [(2, 2)], 48, 'selesai', ''), (3, [(4, 1)], 40, 'selesai', ''),
    (2, [(7, 2)], 33, 'selesai', ''), (2, [(6, 3), (12, 1)], 26, 'selesai', ''), (3, [(2, 2), (12, 2)], 22, 'selesai', ''),
    (3, [(3, 2), (7, 3)], 19, 'selesai', ''), (3, [(10, 2), (11, 1)], 15, 'selesai', ''), (2, [(5, 1)], 12, 'selesai', ''),
    (3, [(8, 1)], 9, 'dibatalkan', 'Bukti pembayaran tidak sesuai nominal.'), (2, [(4, 1)], 7, 'selesai', ''),
    (2, [(9, 2)], 5, 'selesai', ''), (3, [(1, 1), (11, 2)], 3, 'dikirim', ''), (2, [(3, 1)], 2, 'diproses', ''),
    (2, [(2, 1), (7, 2)], 1, 'menunggu_verifikasi', ''), (3, [(6, 2)], 0.2, 'menunggu_bayar', ''),
]
ULASAN = [  # (produk, user, rating, teks, balasan, umur_hari, umur_balasan)
    (1, 2, 5, 'Tanaman sampai segar dan packing rapi sekali.', 'Terima kasih Kak Budi! Selamat merawat monsteranya.', 70, 69),
    (2, 2, 5, 'Sansevieria kokoh, daunnya tebal. Recommended.', None, 44, 0),
    (4, 3, 4, 'Bunganya cantik, pengiriman agak lama tetapi aman.', 'Terima kasih masukannya, kami akan percepat pengiriman.', 36, 35),
    (3, 3, 5, 'Lucu banget untuk meja kerja!', None, 2, 0),
]


UMUR_PRODUK = {8: 1, 5: 3, 9: 5, 4: 9}   # id produk -> umur (hari); yang lain: 10 + id hari. Dipakai kotak "Baru Masuk" di landing


def kosong(db):
    return db.one('SELECT COUNT(*) AS n FROM pengguna')['n'] == 0


def jalankan(db, riwayat=True, acak=False):
    """acak=True (dipakai perintah `seed`): password tiap akun demo diacak dan dikembalikan sebagai [(username, password)],
    jadi tidak ada kredensial tetap yang bisa ditebak dari README. Default (acak=False) dipakai tes."""
    now = int(time.time() * 1000); kredensial = []
    for nama, email, pw, peran, umur in AKUN:
        if acak: pw = 'Sk' + secrets.token_hex(6) + '9'; kredensial.append((nama, pw))
        db.run('INSERT INTO pengguna (username,email,hash,peran,aktif,dibuat) VALUES (%s,%s,%s,%s,1,%s)',
               (nama, email, hash_pw(pw), peran, now - umur * HARI))
    for uid, (_, tel, alm, kota, pos) in ALAMAT.items():
        db.run('UPDATE pengguna SET telepon=%s, alamat=%s, kota=%s, kode_pos=%s WHERE id=%s', (tel, alm, kota, pos, uid))
    with open(os.path.join(os.path.dirname(__file__), 'seed_produk.json'), encoding='utf-8') as f:
        produk = json.load(f)
    info = {}
    for p in produk:
        db.run('INSERT INTO produk (id,nama,kategori,harga,stok,terjual,rating,best_seller,gambar,deskripsi,spesifikasi,dibuat) '
               'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
               (p['id'], p['nama'], p['kategori'], p['harga'], p['stok'], p['terjual'], p['rating'], int(p['bestSeller']),
                p['gambar'], p['deskripsi'], json.dumps(p['spesifikasi'], ensure_ascii=False), now - UMUR_PRODUK.get(p['id'], 10 + p['id']) * HARI))
        info[p['id']] = p

    daftar = [(u, i, d, s, a) for u, i, d, s, a in PESANAN]
    if riwayat:   # riwayat tambahan agar grafik tren punya sebaran wajar (deterministik)
        r = random.Random(20260930)
        for d in range(118, 3, -1):
            if r.random() >= 0.18 + (1 - d / 118) * 0.32: continue
            uid, dipakai, isi = r.choice([2, 3]), set(), []
            for _ in range(1 + (1 if r.random() < 0.35 else 0)):
                pid = r.randint(1, len(info))
                while pid in dipakai: pid = r.randint(1, len(info))
                dipakai.add(pid); isi.append((pid, r.randint(1, 3)))
            batal = r.random() < 0.07
            daftar.append((uid, isi, d + r.random(), 'dibatalkan' if batal else 'selesai',
                           'Bukti pembayaran tidak sesuai nominal.' if batal else ''))
    for uid, isi, umur, status, alasan in sorted(daftar, key=lambda x: -x[2]):   # terlama dulu -> id naik menurut waktu
        dibuat = int(now - umur * HARI)
        batas = now + 20 * 3600000 if status == 'menunggu_bayar' else dibuat + HARI
        total = sum(info[p]['harga'] * q for p, q in isi)
        pen, tel, alm, kota, pos = ALAMAT[uid]
        oid, _ = db.run('INSERT INTO pesanan (user_id,total,status,alasan,penerima,telepon,alamat,kota,kode_pos,dibuat,batas_bayar) '
                        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                        (uid, total, status, alasan, pen, tel, alm, kota, pos, dibuat, batas))
        for p, q in isi:
            db.run('INSERT INTO pesanan_item (pesanan_id,produk_id,nama,gambar,harga,qty) VALUES (%s,%s,%s,%s,%s,%s)',
                   (oid, p, info[p]['nama'], info[p]['gambar'], info[p]['harga'], q))
    for pid, uid, rating, teks, balasan, umur, umur_b in ULASAN:
        db.run('INSERT INTO ulasan (produk_id,user_id,rating,teks,balasan_teks,balasan_dibuat,dibuat) VALUES (%s,%s,%s,%s,%s,%s,%s)',
               (pid, uid, rating, teks, balasan, int(now - umur_b * HARI) if balasan else None, int(now - umur * HARI)))
    db.commit()
    return kredensial
