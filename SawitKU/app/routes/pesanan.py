"""Pesanan: checkout, riwayat, batal, konfirmasi terima (customer) dan verifikasi/pengiriman (admin), plus lacak paket."""
import logging, re
from flask import request

from . import api, ok
from .. import midtrans
from ..config import cfg
from ..db import get_db
from ..errors import ApiError
from ..schemas import badan, CheckoutIn, TerimaIn, VerifikasiIn, KirimIn
from ..security import now_ms, wajib
from ..services import sapu, muat_pesanan, batalkan, lunas
from ..uploads import simpan_data_url, hapus_media
from ..validators import baca_alamat

log = logging.getLogger('sawitku')
pelanggan, admin_saja, siapa_saja = wajib('customer'), wajib('admin'), wajib()


# ---------------- Customer ----------------
@api.post('/checkout', status_code=201, tags=['Pesanan'], summary='Buat pesanan dari keranjang (harga & stok dihitung server)')
@pelanggan
def checkout(u):
    """Body wajib berisi alamat tujuan (penerima, telepon, alamat, kota, kodePos), metode bayar, dan opsional simpan=true."""
    b = badan(CheckoutIn)
    db, uid = get_db(), u['id']
    tujuan = baca_alamat(b.data())
    if b.metode not in midtrans.METODE: raise ApiError('Pilih metode pembayaran.')
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
    oid, _ = db.run('INSERT INTO pesanan (user_id,total,status,alasan,metode,penerima,telepon,alamat,kota,kode_pos,dibuat,batas_bayar) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (uid, total, 'menunggu_bayar', '', b.metode, tujuan['penerima'], tujuan['telepon'], tujuan['alamat'], tujuan['kota'],
                     tujuan['kode_pos'], now, now + cfg['BATAS_BAYAR_JAM'] * 3600000))
    if b.simpan is True:
        db.run('UPDATE pengguna SET telepon=%s, alamat=%s, kota=%s, kode_pos=%s WHERE id=%s',
               (tujuan['telepon'], tujuan['alamat'], tujuan['kota'], tujuan['kode_pos'], uid))
    for r in rows:
        db.run('INSERT INTO pesanan_item (pesanan_id,produk_id,nama,gambar,harga,qty) VALUES (%s,%s,%s,%s,%s,%s)',
               (oid, r['id'], r['nama'], r['gambar'], r['harga'], r['qty']))
        _, n = db.run('UPDATE produk SET stok = stok - %s WHERE id=%s AND stok >= %s', (r['qty'], r['id'], r['qty']))
        if n != 1: raise ApiError(f"Stok {r['nama']} tidak mencukupi.", 409)   # galat -> seluruh transaksi di-rollback
    db.run('DELETE FROM keranjang WHERE user_id=%s', (uid,))
    return ok(muat_pesanan(db, [db.one('SELECT * FROM pesanan WHERE id=%s', (oid,))])[0])


@api.get('/pesanan/saya', tags=['Pesanan'])
@pelanggan
def pesanan_saya(u):
    db = get_db(); sapu(db)
    return ok(muat_pesanan(db, db.all('SELECT * FROM pesanan WHERE user_id=%s ORDER BY dibuat DESC, id DESC', (u['id'],))))


def milik(db, oid, uid):
    """Baris pesanan milik pengguna (dikunci untuk diubah) atau 404."""
    o = db.one('SELECT * FROM pesanan WHERE id=%s AND user_id=%s FOR UPDATE', (oid, uid))
    if not o: raise ApiError('Pesanan tidak ditemukan.', 404)
    return o


@api.get('/pesanan/<int:oid>', tags=['Pesanan'])
@pelanggan
def pesanan_detail(u, oid):
    db = get_db(); sapu(db)
    o = db.one('SELECT * FROM pesanan WHERE id=%s AND user_id=%s', (oid, u['id']))
    if not o: raise ApiError('Pesanan tidak ditemukan.', 404)
    return ok(muat_pesanan(db, [o])[0])


@api.post('/pesanan/<int:oid>/batal', tags=['Pesanan'])
@pelanggan
def batal(u, oid):
    db = get_db(); o = milik(db, oid, u['id'])
    if o['status'] != 'menunggu_bayar': raise ApiError('Pesanan tidak dapat dibatalkan.', 409)
    batalkan(db, o, 'Dibatalkan oleh pembeli.')
    db.commit()
    if o['midtrans_id'] and midtrans.aktif(): midtrans.batalkan(o['midtrans_id'])    # tagihan di Midtrans ikut dibatalkan
    return ok()


@api.post('/pesanan/<int:oid>/terima', tags=['Pesanan'], summary='Konfirmasi barang diterima (foto opsional)')
@pelanggan
def terima(u, oid):
    """Pembeli boleh melampirkan foto barang yang tiba. Tanpa konfirmasi, pesanan selesai otomatis AUTO_TERIMA_JAM jam
    setelah admin menandai barang tiba."""
    b = badan(TerimaIn, wajib=False)
    db = get_db(); o = milik(db, oid, u['id'])
    if o['status'] != 'dikirim': raise ApiError('Pesanan belum dikirim.', 409)
    foto = simpan_data_url(b.foto, 'terima') if b is not None and b.foto else None
    db.run('UPDATE pesanan SET status=%s, t_selesai=%s, foto_terima=%s WHERE id=%s', ('selesai', now_ms(), foto, oid))
    return ok()


# ---------------- Pelacakan paket ----------------
def _kode_pesanan(kode):
    m = re.fullmatch(r'#?(?:SK-?)?0*(\d{1,9})', kode.strip().upper())
    return int(m.group(1)) if m else None


@api.get('/lacak', tags=['Pesanan'], summary='Lacak berdasarkan nomor pesanan atau nomor resi')
@siapa_saja
def lacak(u):
    """Customer hanya pesanannya sendiri; admin semua."""
    db, kode = get_db(), str(request.args.get('kode') or '').strip()[:40]
    if len(kode) < 1: raise ApiError('Isi nomor pesanan atau nomor resi.')
    batas, arg = ('', ()) if u['peran'] == 'admin' else (' AND user_id=%s', (u['id'],))
    nomor = _kode_pesanan(kode)
    o = db.one('SELECT * FROM pesanan WHERE id=%s' + batas, (nomor,) + arg) if nomor else None
    if not o: o = db.one('SELECT * FROM pesanan WHERE resi=%s' + batas, (re.sub(r'\s', '', kode).upper(),) + arg)
    if not o: raise ApiError('Pesanan atau resi tidak ditemukan.', 404)
    p = muat_pesanan(db, [o])[0]; w = p['waktu']
    if o['status'] == 'dibatalkan':
        langkah = [('Pesanan dibuat', p['dibuat']), ('Pesanan dibatalkan', None)]
        selesai = [True, True]
    else:
        langkah = [('Pesanan dibuat', p['dibuat']), ('Pembayaran diterima', w['bayar'] if w['proses'] else None), ('Pesanan dikemas', w['proses']),
                   ('Dalam pengiriman', w['kirim']), ('Tiba di tujuan', w['sampai'] or (w['selesai'] if w['kirim'] else None)),
                   ('Pesanan diterima', w['selesai'])]
        selesai = [t is not None for _, t in langkah]
    return ok({'pesanan': p, 'timeline': [{'label': l, 'waktu': t, 'selesai': s} for (l, t), s in zip(langkah, selesai)]})


# ---------------- Admin ----------------
@api.get('/admin/pesanan', tags=['Admin'])
@admin_saja
def admin_pesanan(_):
    db = get_db(); sapu(db)
    rows = db.all('SELECT o.*, u.username AS pembeli FROM pesanan o LEFT JOIN pengguna u ON u.id=o.user_id ORDER BY o.dibuat DESC, o.id DESC')
    return ok(muat_pesanan(db, rows, lambda o: {'pembeli': o['pembeli'] or '-'}))


@api.post('/admin/pesanan/<int:oid>/verifikasi', tags=['Admin'], summary='Setujui / tolak bukti pembayaran')
@admin_saja
def verifikasi(_, oid):
    b = badan(VerifikasiIn)
    db = get_db()
    o = db.one('SELECT * FROM pesanan WHERE id=%s FOR UPDATE', (oid,))
    if not o or o['status'] != 'menunggu_verifikasi': raise ApiError('Pesanan tidak menunggu verifikasi.', 409)
    if b.setuju is True:
        if o['midtrans_id'] and midtrans.aktif():       # perbarui status Midtrans dulu agar pendapatan di grafik (hanya yang lunas) akurat
            try:
                d = midtrans.status(o['midtrans_id'])
                if d.get('transaction_status') and int(float(d.get('gross_amount') or 0)) == int(o['total']):
                    db.run('UPDATE pesanan SET midtrans_status=%s WHERE id=%s', (str(d['transaction_status'])[:20], o['id']))
            except Exception: pass                       # gagal cek tidak menghalangi persetujuan; admin bisa klik "Cek status"
        lunas(db, o)
    else:
        # Ditolak: pesanan TIDAK dibatalkan. Kembali ke 'menunggu_bayar' dengan alasan, supaya pembeli bisa mengunggah ulang bukti.
        alasan = (str(b.alasan or '').strip()[:200]) or 'Bukti pembayaran tidak sesuai.'
        db.run('UPDATE pesanan SET status=%s, alasan=%s, ditolak=ditolak+1, bukti=NULL, t_bayar=NULL, batas_bayar=%s WHERE id=%s',
               ('menunggu_bayar', alasan, now_ms() + cfg['BATAS_BAYAR_JAM'] * 3600000, oid))
        db.commit(); hapus_media(o['bukti'], db)
    return ok()


@api.post('/admin/pesanan/<int:oid>/kirim', tags=['Admin'], summary='Tandai dikirim (kurir + resi)')
@admin_saja
def kirim_pesanan(_, oid):
    b = badan(KirimIn)
    db = get_db()
    kurir, resi = str(b.kurir or '').strip()[:30], re.sub(r'\s', '', str(b.resi or '')).upper()
    if not 2 <= len(kurir) <= 30: raise ApiError('Isi nama kurir (mis. JNE, J&T, SiCepat).')
    if not re.fullmatch(r'[A-Z0-9\-]{5,40}', resi): raise ApiError('Nomor resi 5–40 karakter (huruf, angka, strip).')
    o = db.one('SELECT status FROM pesanan WHERE id=%s FOR UPDATE', (oid,))
    if not o or o['status'] != 'diproses': raise ApiError('Pesanan belum siap dikirim.', 409)
    if db.one('SELECT 1 AS x FROM pesanan WHERE resi=%s AND id<>%s', (resi, oid)): raise ApiError('Nomor resi itu sudah dipakai pesanan lain.', 409)
    db.run('UPDATE pesanan SET status=%s, kurir=%s, resi=%s, t_kirim=%s WHERE id=%s', ('dikirim', kurir, resi, now_ms(), oid))
    return ok()


@api.post('/admin/pesanan/<int:oid>/sampai', tags=['Admin'], summary='Tandai barang sudah tiba/diantar ke pembeli')
@admin_saja
def tandai_sampai(_, oid):
    """Memulai hitung mundur AUTO_TERIMA_JAM: tanpa konfirmasi pembeli, pesanan selesai otomatis."""
    db = get_db()
    o = db.one('SELECT status, t_sampai FROM pesanan WHERE id=%s FOR UPDATE', (oid,))
    if not o or o['status'] != 'dikirim': raise ApiError('Pesanan belum dalam pengiriman.', 409)
    if o['t_sampai']: raise ApiError('Pesanan sudah ditandai tiba.', 409)
    db.run('UPDATE pesanan SET t_sampai=%s WHERE id=%s', (now_ms(), oid))
    return ok()
