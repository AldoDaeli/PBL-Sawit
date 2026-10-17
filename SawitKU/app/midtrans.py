"""Midtrans Snap (virtual account). Tanpa pustaka tambahan: memakai urllib. Kunci server hanya ada di .env (tidak pernah ke browser).
Alur: server membuat transaksi Snap -> pembeli diarahkan ke halaman bayar Midtrans (BCA/BNI/BRI/Permata/CIMB VA, dll.)
-> Midtrans memanggil /api/midtrans/notifikasi (webhook) -> pesanan otomatis 'diproses'."""
import base64, hashlib, hmac, json, urllib.error, urllib.request
from flask import current_app
from .errors import ApiError

VA = ['bca_va', 'bni_va', 'bri_va', 'permata_va', 'cimb_va', 'other_va', 'echannel']


def aktif(): return bool(current_app.config['MIDTRANS_SERVER_KEY'])


def _basis():
    prod = current_app.config['MIDTRANS_PRODUKSI']
    return ('https://app.midtrans.com', 'https://api.midtrans.com') if prod else ('https://app.sandbox.midtrans.com', 'https://api.sandbox.midtrans.com')


def _panggil(url, payload=None):
    kunci = current_app.config['MIDTRANS_SERVER_KEY']
    h = {'Accept': 'application/json', 'Content-Type': 'application/json',
         'Authorization': 'Basic ' + base64.b64encode((kunci + ':').encode()).decode()}
    req = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode(), headers=h, method='GET' if payload is None else 'POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try: pesan = json.loads(e.read().decode()).get('error_messages') or ''
        except Exception: pesan = ''
        current_app.logger.warning('MIDTRANS HTTP %s %s %s', e.code, url, pesan)
        raise ApiError('Midtrans menolak permintaan. Periksa kunci server dan mode (sandbox/produksi).', 502)
    except Exception:
        current_app.logger.exception('MIDTRANS tidak terjangkau')
        raise ApiError('Tidak dapat terhubung ke Midtrans. Coba lagi sebentar.', 502)


def buat_transaksi(order_id, total, pembeli, items, finish_url, menit):
    app_url, _ = _basis()
    payload = {
        'transaction_details': {'order_id': order_id, 'gross_amount': int(total)},
        'item_details': [{'id': str(i['produk_id'] or 0), 'price': int(i['harga']), 'quantity': int(i['qty']), 'name': i['nama'][:50]} for i in items],
        'customer_details': {'first_name': pembeli['penerima'][:50], 'email': pembeli['email'], 'phone': pembeli['telepon']},
        'enable_payments': VA,
        'expiry': {'unit': 'minutes', 'duration': max(1, int(menit))},
        'callbacks': {'finish': finish_url},
    }
    d = _panggil(app_url + '/snap/v1/transactions', payload)
    if not d.get('redirect_url'): raise ApiError('Midtrans tidak mengembalikan tautan pembayaran.', 502)
    return d


def status(order_id):
    return _panggil(_basis()[1] + f'/v2/{order_id}/status')


def signature_sah(d):
    """signature_key = SHA512(order_id + status_code + gross_amount + ServerKey)."""
    try:
        isi = str(d['order_id']) + str(d['status_code']) + str(d['gross_amount']) + current_app.config['MIDTRANS_SERVER_KEY']
        return hmac.compare_digest(hashlib.sha512(isi.encode()).hexdigest(), str(d.get('signature_key', '')))
    except KeyError:
        return False


def berhasil(d):
    ts = d.get('transaction_status')
    return ts == 'settlement' or (ts == 'capture' and d.get('fraud_status', 'accept') == 'accept')
