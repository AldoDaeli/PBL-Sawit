"""Pembayaran lewat Midtrans (QRIS / Virtual Account) + unggah bukti bayar.

Alur aman: pembeli membayar ke QR/VA Midtrans, lalu WAJIB mengunggah bukti; admin memeriksa bukti dan status Midtrans
sebelum menyetujui. Webhook/cek status Midtrans hanya mencatat status (bahan verifikasi), tidak pernah menyetujui pesanan."""
import json, logging, secrets

from flask import request

from . import api, ok
from .. import midtrans
from ..db import get_db
from ..errors import ApiError
from ..schemas import badan, Isi, MetodeIn, BuktiIn
from ..security import now_ms, wajib
from ..serializers import baca_json
from ..services import sapu, muat_pesanan
from ..uploads import simpan_data_url, hapus_media
from .pesanan import milik

log = logging.getLogger('sawitku')
pelanggan, admin_saja = wajib('customer'), wajib('admin')


def _tagihan(db, oid, u, o, metode):
    """Buat tagihan Midtrans untuk pesanan `o` dengan `metode` dan catat hasilnya."""
    items = db.all('SELECT produk_id, nama, harga, qty FROM pesanan_item WHERE pesanan_id=%s', (oid,))
    menit = max(1, int((o['batas_bayar'] - now_ms()) / 60000))
    order_id = f'SK{oid}-{secrets.token_hex(3)}'
    data, status = midtrans.charge(order_id, o['total'], {'penerima': o['penerima'] or u['username'], 'email': u['email'], 'telepon': o['telepon']},
                                   items, menit, metode)
    db.run('UPDATE pesanan SET metode=%s, midtrans_id=%s, midtrans_status=%s, midtrans_data=%s WHERE id=%s',
           (metode, order_id, status, json.dumps(data), oid))


@api.post('/pesanan/<int:oid>/pembayaran', tags=['Pembayaran'], summary='Buat (atau ambil) tagihan Midtrans: QR atau nomor VA')
@pelanggan
def buat_pembayaran(u, oid):
    """Tanpa `metode`: memakai pilihan saat checkout. Metode sama dengan tagihan aktif -> tagihan yang sama dikembalikan.
    Metode berbeda -> tagihan lama dibatalkan dan dibuat yang baru (hanya sebelum bukti diunggah)."""
    b = badan(MetodeIn)
    db = get_db(); sapu(db)
    if not midtrans.aktif(): raise ApiError('Pembayaran Midtrans belum diaktifkan oleh admin.', 503)
    o = milik(db, oid, u['id'])
    if o['status'] != 'menunggu_bayar': raise ApiError('Pesanan tidak dapat dibayar.', 409)
    metode = b.metode or o['metode']
    if metode not in midtrans.METODE: raise ApiError('Metode pembayaran tidak dikenal.')
    lama = baca_json(o['midtrans_data'], {})
    if not (o['midtrans_id'] and lama.get('metode') == metode and o['midtrans_status'] in ('pending', 'authorize')):
        db.commit()
        if o['midtrans_id']: midtrans.batalkan(o['midtrans_id'])
        _tagihan(db, oid, u, o, metode)
    return ok(muat_pesanan(db, [db.one('SELECT * FROM pesanan WHERE id=%s', (oid,))])[0])


@api.post('/pesanan/<int:oid>/pembayaran/cek', tags=['Pembayaran'], summary='Sinkronkan status tagihan dari Midtrans')
@pelanggan
def cek_pembayaran(u, oid):
    db = get_db(); o = milik(db, oid, u['id'])
    _sinkron(db, o)
    return ok(muat_pesanan(db, [db.one('SELECT * FROM pesanan WHERE id=%s', (oid,))])[0])


def _sinkron(db, o):
    """Ambil status terbaru dari Midtrans dan catat (tanpa mengubah status pesanan)."""
    if not (midtrans.aktif() and o['midtrans_id']): return
    d = midtrans.status(o['midtrans_id'])
    if d.get('transaction_status'): _catat(db, o, d)


def _catat(db, o, d):
    if int(float(d.get('gross_amount') or 0)) != int(o['total']):
        log.warning('MIDTRANS jumlah tidak cocok pesanan=%s', o['id']); return
    db.run('UPDATE pesanan SET midtrans_status=%s WHERE id=%s', (str(d['transaction_status'])[:20], o['id']))


@api.post('/pesanan/<int:oid>/bukti', tags=['Pembayaran'], summary='Unggah bukti bayar (wajib) untuk diperiksa admin')
@pelanggan
def unggah_bukti(u, oid):
    """Juga dipakai unggah ULANG setelah bukti ditolak (status kembali 'menunggu_bayar')."""
    b = badan(BuktiIn)
    db = get_db(); sapu(db)
    o = milik(db, oid, u['id'])
    if o['status'] != 'menunggu_bayar': raise ApiError('Pesanan tidak dapat dibayar.', 409)
    if not o['midtrans_id']: raise ApiError('Buat tagihan pembayaran dulu sebelum mengunggah bukti.', 409)
    path = simpan_data_url(b.bukti, 'bukti')
    db.run('UPDATE pesanan SET bukti=%s, status=%s, alasan=%s, t_bayar=%s WHERE id=%s', (path, 'menunggu_verifikasi', '', now_ms(), oid))
    db.commit(); hapus_media(o['bukti'], db)
    return ok()


@api.post('/midtrans/notifikasi', tags=['Pembayaran'], summary='Webhook Midtrans (wajib tanda tangan sah)')
def notifikasi():
    b = badan(Isi)
    d = b.data()
    if not midtrans.aktif() or not midtrans.signature_sah(d):
        log.warning('MIDTRANS notifikasi ditolak (tanda tangan)')
        raise ApiError('Tanda tangan tidak sah.', 403)
    db = get_db()
    o = db.one('SELECT * FROM pesanan WHERE midtrans_id=%s FOR UPDATE', (str(d.get('order_id')),))
    if o: _catat(db, o, d)
    return ok()


@api.post('/admin/pesanan/<int:oid>/midtrans/cek', tags=['Admin'], summary='Admin: cek status pembayaran ke Midtrans')
@admin_saja
def admin_cek(_, oid):
    db = get_db()
    o = db.one('SELECT * FROM pesanan WHERE id=%s FOR UPDATE', (oid,))
    if not o: raise ApiError('Pesanan tidak ditemukan.', 404)
    if not o['midtrans_id']: raise ApiError('Pesanan ini belum punya tagihan Midtrans.', 409)
    _sinkron(db, o)
    return ok(muat_pesanan(db, [db.one('SELECT * FROM pesanan WHERE id=%s', (oid,))])[0])
