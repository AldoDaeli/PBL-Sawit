"""Midtrans Core API: QRIS dan Virtual Account (BCA, BNI, BRI, Permata, Mandiri Bill). Tanpa pustaka tambahan: memakai urllib.

Kunci server hanya ada di .env (tidak pernah ke browser). Alur:
  1. checkout membuat pesanan, pembeli memilih metode;
  2. halaman bayar memanggil `charge` -> Midtrans mengembalikan gambar QR / nomor VA yang ditampilkan di halaman sendiri;
  3. pembeli membayar lalu MENGUNGGAH BUKTI; admin memeriksa bukti dan status Midtrans sebelum menyetujui.
Status dari Midtrans (webhook / cek manual) hanya dicatat sebagai bahan verifikasi admin: pesanan TIDAK otomatis disetujui."""
import base64, hashlib, hmac, json, logging, urllib.error, urllib.request

from .config import cfg
from .errors import ApiError

log = logging.getLogger('sawitku')

# kode metode -> (label, jenis tampilan, bagian payload khusus metode)
METODE = {
    'qris':    ('QRIS (semua e-wallet & m-banking)', 'qris', {'payment_type': 'qris', 'qris': {'acquirer': 'gopay'}}),
    'bca':     ('BCA Virtual Account', 'va', {'payment_type': 'bank_transfer', 'bank_transfer': {'bank': 'bca'}}),
    'bni':     ('BNI Virtual Account', 'va', {'payment_type': 'bank_transfer', 'bank_transfer': {'bank': 'bni'}}),
    'bri':     ('BRI Virtual Account', 'va', {'payment_type': 'bank_transfer', 'bank_transfer': {'bank': 'bri'}}),
    'permata': ('Permata Virtual Account', 'va', {'payment_type': 'bank_transfer', 'bank_transfer': {'bank': 'permata'}}),
    'mandiri': ('Mandiri Bill Payment', 'bill', {'payment_type': 'echannel', 'echannel': {'bill_info1': 'Pembayaran:', 'bill_info2': 'SawitKu'}}),
}
HOST_QR = ('https://api.sandbox.midtrans.com/', 'https://api.midtrans.com/')     # gambar QR hanya diterima dari Midtrans


def aktif(): return bool(cfg['MIDTRANS_SERVER_KEY'])


def daftar_metode():
    return [{'kode': k, 'label': v[0], 'jenis': v[1]} for k, v in METODE.items()]


def _api(): return 'https://api.midtrans.com' if cfg['MIDTRANS_PRODUKSI'] else 'https://api.sandbox.midtrans.com'


def _panggil(url, payload=None):
    """GET (payload None) atau POST JSON ke Midtrans dengan Basic Auth kunci server."""
    kunci = cfg['MIDTRANS_SERVER_KEY']
    h = {'Accept': 'application/json', 'Content-Type': 'application/json',
         'Authorization': 'Basic ' + base64.b64encode((kunci + ':').encode()).decode()}
    req = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode(), headers=h,
                                 method='GET' if payload is None else 'POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read().decode() or '{}')  # nosec B310 - URL selalu https ke Midtrans
    except urllib.error.HTTPError as e:
        log.warning('MIDTRANS HTTP %s %s', e.code, url)
        raise ApiError('Midtrans menolak permintaan. Periksa kunci server dan mode (sandbox/produksi).', 502)
    except Exception:
        log.exception('MIDTRANS tidak terjangkau')
        raise ApiError('Tidak dapat terhubung ke Midtrans. Coba lagi sebentar.', 502)


def charge(order_id, total, pembeli, items, menit, metode):
    """Buat tagihan di Midtrans. Kembalikan (data_tampil, status_awal). Midtrans membalas HTTP 200 dengan `status_code` di badan."""
    if metode not in METODE: raise ApiError('Metode pembayaran tidak dikenal.')
    payload = {
        **METODE[metode][2],
        'transaction_details': {'order_id': order_id, 'gross_amount': int(total)},
        'item_details': [{'id': str(i['produk_id'] or 0), 'price': int(i['harga']), 'quantity': int(i['qty']), 'name': i['nama'][:50]} for i in items],
        'customer_details': {'first_name': pembeli['penerima'][:50], 'email': pembeli['email'], 'phone': pembeli['telepon']},
        'custom_expiry': {'expiry_duration': max(1, int(menit)), 'unit': 'minute'},
    }
    d = _panggil(_api() + '/v2/charge', payload)
    if str(d.get('status_code')) not in ('200', '201'):
        log.warning('MIDTRANS charge ditolak: %s %s', d.get('status_code'), d.get('status_message'))
        raise ApiError('Midtrans menolak pembuatan tagihan. Coba metode lain atau ulangi sebentar lagi.', 502)
    return ringkas(metode, d), str(d.get('transaction_status') or 'pending')


def ringkas(metode, d):
    """Ambil hanya yang perlu ditampilkan di halaman bayar dari balasan charge."""
    label, jenis, _ = METODE[metode]
    out = {'metode': metode, 'label': label, 'jenis': jenis, 'transaksiId': str(d.get('transaction_id') or '')}
    if jenis == 'qris':
        url = next((a.get('url') for a in d.get('actions') or [] if a.get('name') == 'generate-qr-code'), '')
        out['qrUrl'] = url if str(url).startswith(HOST_QR) else ''
        out['qrString'] = str(d.get('qr_string') or '')
    elif jenis == 'bill':
        out['kodePerusahaan'], out['kodeBayar'] = str(d.get('biller_code') or ''), str(d.get('bill_key') or '')
    else:
        va = (d.get('va_numbers') or [{}])[0]
        out['bank'] = str(va.get('bank') or metode)
        out['va'] = str(va.get('va_number') or d.get('permata_va_number') or '')
    return out


def status(order_id): return _panggil(_api() + f'/v2/{order_id}/status')


def batalkan(order_id):
    """Batalkan tagihan lama (upaya terbaik): dipakai saat pembeli mengganti metode atau membatalkan pesanan."""
    try: _panggil(_api() + f'/v2/{order_id}/cancel', {})
    except ApiError: pass


def signature_sah(d):
    """signature_key = SHA512(order_id + status_code + gross_amount + ServerKey)."""
    try:
        isi = str(d['order_id']) + str(d['status_code']) + str(d['gross_amount']) + cfg['MIDTRANS_SERVER_KEY']
        return hmac.compare_digest(hashlib.sha512(isi.encode()).hexdigest(), str(d.get('signature_key', '')))
    except (KeyError, TypeError):
        return False


def berhasil(d):
    ts = d.get('transaction_status')
    return ts == 'settlement' or (ts == 'capture' and d.get('fraud_status', 'accept') == 'accept')
