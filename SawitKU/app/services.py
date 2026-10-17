"""Logika bisnis bersama: pembatalan pesanan, sapu pesanan kedaluwarsa, muat item, hitung ulang rating."""
from flask import current_app
from .security import now_ms
from .serializers import pesanan_out

_terakhir = 0

def muat_pesanan(db, rows, ekstra=None):
    """Lampirkan item ke daftar pesanan (satu query untuk semua)."""
    if not rows: return []
    ids = [o['id'] for o in rows]
    items = db.all(f"SELECT * FROM pesanan_item WHERE pesanan_id IN ({','.join(['%s'] * len(ids))}) ORDER BY id", ids)
    per = {}
    for i in items: per.setdefault(i['pesanan_id'], []).append(i)
    out = []
    for o in rows:
        d = pesanan_out(o, per.get(o['id'], []))
        if ekstra: d.update(ekstra(o))
        out.append(d)
    return out

def batalkan(db, o, alasan):
    """Batalkan pesanan yang belum diproses & kembalikan stok. Pesanan diproses/dikirim/selesai tidak disentuh."""
    if o['status'] in ('dibatalkan', 'diproses', 'dikirim', 'selesai'): return
    for i in db.all('SELECT produk_id, qty FROM pesanan_item WHERE pesanan_id=%s', (o['id'],)):
        if i['produk_id'] is not None:
            db.run('UPDATE produk SET stok = stok + %s WHERE id=%s', (i['qty'], i['produk_id']))
    db.run('UPDATE pesanan SET status=%s, alasan=%s WHERE id=%s', ('dibatalkan', alasan[:255], o['id']))

def sapu(db, paksa=False):
    """Batalkan pesanan yang lewat batas bayar. Dipanggil dari endpoint terkait (dibatasi frekuensinya);
    idempoten & aman dijalankan bersamaan berkat FOR UPDATE."""
    global _terakhir
    now = now_ms()
    if not paksa and now - _terakhir < current_app.config['SWEEP_INTERVAL_MS']: return
    _terakhir = now
    for o in db.all('SELECT * FROM pesanan WHERE status=%s AND batas_bayar<%s FOR UPDATE', ('menunggu_bayar', now)):
        batalkan(db, o, 'Melewati batas waktu pembayaran.')
    db.run('DELETE FROM sesi WHERE kedaluwarsa<%s', (now,))
    db.commit()   # simpan sekarang: pembatalan otomatis tidak boleh ikut ter-rollback bila request ini berakhir dengan galat

def hitung_rating(db, produk_id):
    db.run('UPDATE produk SET rating=(SELECT ROUND(AVG(rating),1) FROM ulasan WHERE produk_id=%s) WHERE id=%s',
           (produk_id, produk_id))


def lunas(db, o, metode):
    """Pembayaran sah (disetujui admin / lunas di Midtrans): pesanan masuk 'diproses', terjual bertambah. Idempoten."""
    if o['status'] not in ('menunggu_bayar', 'menunggu_verifikasi'): return False
    now = now_ms()
    db.run('UPDATE pesanan SET status=%s, alasan=%s, metode=%s, t_bayar=COALESCE(t_bayar,%s), t_proses=%s WHERE id=%s',
           ('diproses', '', metode, now, now, o['id']))
    for i in db.all('SELECT produk_id, qty FROM pesanan_item WHERE pesanan_id=%s', (o['id'],)):
        if i['produk_id'] is not None: db.run('UPDATE produk SET terjual = terjual + %s WHERE id=%s', (i['qty'], i['produk_id']))
    return True


def lanjutan_ulasan(db, ids):
    """{ulasan_id: [balasan lanjutan berurutan]} dalam satu query."""
    if not ids: return {}
    out = {}
    for x in db.all(f"SELECT * FROM ulasan_balas WHERE ulasan_id IN ({','.join(['%s'] * len(ids))}) ORDER BY id", list(ids)):
        out.setdefault(x['ulasan_id'], []).append(x)
    return out
