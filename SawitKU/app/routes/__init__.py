"""Rute REST (`/api/...`) sebagai Blueprint Flask. Tiap modul mendaftarkan endpoint ke `api`; semua endpoint dibungkus transaksi database.

Opsi tambahan pada dekorator rute (`@api.post('/x', status_code=201, tags=['Akun'], summary='...')`) dibaca `Router` lalu dipakai untuk
status respons dan halaman dokumentasi `/api/docs`; Flask sendiri tidak melihatnya."""
from functools import wraps

from flask import Blueprint

from .. import db as basis

DAFTAR = []          # metadata semua endpoint, dipakai app/docs.py


def transaksi(fn):
    """Satu endpoint = satu transaksi: commit bila sukses, rollback bila ada galat (ApiError atau lainnya).
    Commit terjadi SEBELUM respons dikirim, jadi permintaan berikutnya dari klien selalu melihat hasilnya."""
    @wraps(fn)
    def bungkus(*a, **k):
        try: hasil = fn(*a, **k)
        except BaseException:
            basis.batal(); raise
        basis.simpan(); return hasil
    return bungkus


class Router(Blueprint):
    def add_url_rule(self, rule, endpoint=None, view_func=None, **opsi):
        if view_func is not None:
            status, ringkas, tags = opsi.pop('status_code', 200), opsi.pop('summary', None), opsi.pop('tags', None)
            DAFTAR.append({'path': (self.url_prefix or '') + rule, 'metode': sorted(m for m in opsi.get('methods', ['GET']) if m not in ('HEAD', 'OPTIONS')),
                           'ringkas': ringkas or (view_func.__doc__ or '').strip().split('\n')[0], 'tag': (tags or ['Lainnya'])[0],
                           'akses': getattr(view_func, 'peran', None) or 'publik', 'status': status})
            asli = view_func

            @wraps(asli)
            def beri_status(*a, **k):
                hasil = asli(*a, **k)
                return (hasil, status) if status != 200 else hasil
            view_func = transaksi(beri_status)
        return super().add_url_rule(rule, endpoint, view_func, **opsi)


api = Router('api', __name__, url_prefix='/api')


def ok(data=None):
    return {'data': data}


from . import publik, customer, pesanan, pembayaran, admin, chat  # noqa: E402,F401  (mendaftarkan rute ke api)
