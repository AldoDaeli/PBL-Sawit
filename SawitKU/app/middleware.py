"""Lapisan lintas-request untuk Flask: IP klien di belakang proxy (WSGI), konteks request, header keamanan, Server-Timing,
batas ukuran body, CORS, kompresi gzip, dan penanganan galat yang selalu berupa JSON {"error": "..."}."""
import gzip, logging, time

from flask import g, jsonify, make_response, request
from werkzeug.exceptions import HTTPException

from .config import cfg
from .db import mulai_konteks, konteks, tutup
from .errors import ApiError

log = logging.getLogger('sawitku')
PESAN_HTTP = {404: 'Data tidak ditemukan.', 405: 'Metode tidak diizinkan.', 413: 'Ukuran data terlalu besar.', 500: 'Terjadi kesalahan pada server.'}
HEADER_BOLEH = {'authorization', 'content-type', 'accept', 'accept-language', 'content-language'}
TIPE_GZIP = ('text/', 'application/json', 'application/javascript', 'image/svg+xml')
GZIP_MIN = 700


class IpProxy:
    """Middleware WSGI. IP klien asli dari X-Forwarded-For, HANYA bila PROXY_HOPS > 0 (aplikasi benar-benar di belakang proxy tepercaya):
    diambil entri ke-N dari kanan (N = jumlah proxy), sehingga entri palsu yang disisipkan klien di kiri diabaikan."""
    def __init__(self, app): self.app = app

    def __call__(self, environ, start_response):
        n = cfg['PROXY_HOPS']
        if n > 0:
            xff = [x.strip() for x in environ.get('HTTP_X_FORWARDED_FOR', '').split(',') if x.strip()]
            if len(xff) >= n: environ['REMOTE_ADDR'] = xff[-n]
            proto = environ.get('HTTP_X_FORWARDED_PROTO', '').split(',')[-1].strip()
            if proto in ('https', 'http'): environ['wsgi.url_scheme'] = proto
        return self.app(environ, start_response)


def _asal_ok(asal):
    izin = cfg['CORS_ORIGINS']
    return bool(asal) and ('*' in izin or asal in izin)


def _json_galat(pesan, status, headers=()):
    r = jsonify({'error': pesan}); r.status_code = status
    for k, v in headers: r.headers[k] = v
    return r


def pasang(app):
    """Daftarkan hook request dan penangan galat ke aplikasi Flask."""

    # ---------------- Sebelum request ----------------
    @app.before_request
    def _mulai():
        g.t0 = time.perf_counter()
        mulai_konteks().ip = request.remote_addr or '?'
        asal = request.headers.get('Origin')
        if request.method == 'OPTIONS' and asal and request.headers.get('Access-Control-Request-Method'):    # preflight CORS
            diminta = [x.strip().lower() for x in request.headers.get('Access-Control-Request-Headers', '').split(',') if x.strip()]
            if not _asal_ok(asal): return make_response('Disallowed CORS origin', 400)
            if any(x not in HEADER_BOLEH for x in diminta): return make_response('Disallowed CORS headers', 400)
            r = make_response('OK', 200)
            r.headers.update({'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS', 'Access-Control-Allow-Headers': 'Authorization, Content-Type',
                              'Access-Control-Max-Age': '600', 'Access-Control-Allow-Origin': '*' if '*' in cfg['CORS_ORIGINS'] else asal})
            r.headers.add('Vary', 'Origin')
            return r
        if request.content_length and request.content_length > cfg['MAKS_BODY_MB'] * 1048576: raise ApiError(PESAN_HTTP[413], 413)

    # ---------------- Setelah request ----------------
    @app.after_request
    def _akhir(r):
        ms = (time.perf_counter() - g.get('t0', time.perf_counter())) * 1000
        h = r.headers
        h.setdefault('X-Content-Type-Options', 'nosniff'); h.setdefault('X-Frame-Options', 'DENY'); h.setdefault('Referrer-Policy', 'same-origin')
        h.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        if request.scheme == 'https': h.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        if (r.content_type or '').startswith('text/html'): h.setdefault('Content-Security-Policy', "frame-ancestors 'none'")
        if request.path.startswith('/api/'): h.setdefault('Cache-Control', 'no-store')
        h['Server-Timing'] = f'app;dur={ms:.0f}'
        k = g.get('_sk')
        if k is not None and k.token_baru: h['X-Token-Baru'] = k.token_baru
        if ms > cfg['LAMBAT_MS']: log.warning('LAMBAT %s %s %.0fms', request.method, request.path, ms)
        asal = request.headers.get('Origin')
        if _asal_ok(asal):
            h['Access-Control-Allow-Origin'] = '*' if '*' in cfg['CORS_ORIGINS'] else asal
            h['Access-Control-Expose-Headers'] = 'X-Token-Baru'
            h.add('Vary', 'Origin')
        return _gzip(r)

    @app.teardown_request
    def _tutup(_exc):
        k = g.get('_sk')
        if k is not None: tutup(k)

    # ---------------- Galat -> selalu JSON ----------------
    @app.errorhandler(ApiError)
    def _api(e): return _json_galat(e.pesan, e.status)

    @app.errorhandler(HTTPException)
    def _http(e):
        extra = [(k, v) for k, v in e.get_headers() if k.lower() not in ('content-type', 'content-length')]     # mis. Allow pada 405
        return _json_galat(PESAN_HTTP.get(e.code) or e.description, e.code or 500, extra)

    @app.errorhandler(Exception)
    def _tak_terduga(e):
        log.exception('Galat tak terduga %s %s', request.method, request.path)
        return _json_galat(PESAN_HTTP[500], 500)


def _gzip(r):
    """Kompres respons teks/JSON besar bila klien meminta gzip. Respons yang sudah dikompres (aset statis di web.py) dilewati."""
    tipe = (r.content_type or '').lower()
    if r.direct_passthrough or r.is_streamed or r.status_code in (204, 304) or r.status_code < 200 or 'Content-Encoding' in r.headers: return r
    if not tipe.startswith(TIPE_GZIP): return r
    data = r.get_data()
    if len(data) < GZIP_MIN: return r
    r.headers.add('Vary', 'Accept-Encoding')
    if 'gzip' not in request.headers.get('Accept-Encoding', '').lower(): return r
    r.set_data(gzip.compress(data, compresslevel=5, mtime=0))
    r.headers['Content-Encoding'] = 'gzip'
    return r
