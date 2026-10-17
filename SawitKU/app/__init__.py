import gzip, logging, re, time
import os
from flask import Flask, jsonify, request, send_from_directory, abort, g, redirect, Response
from .config import Config
from .errors import ApiError
from . import db as dbm
from .security import reset_laju
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import safe_join


def create_app(overrides=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    dbm.init_app(app)
    reset_laju()
    if app.config['PROXY_HOPS'] > 0:     # IP klien asli dari X-Forwarded-For (hanya bila benar-benar di belakang proxy tepercaya)
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=app.config['PROXY_HOPS'], x_proto=app.config['PROXY_HOPS'])

    from .routes import bp
    app.register_blueprint(bp, url_prefix='/api')

    from .cli import daftarkan
    daftarkan(app)

    # ---- Berkas unggahan (foto produk, bukti bayar, foto profil) ----
    @app.get('/media/<folder>/<nama>')
    def media(folder, nama):
        from .uploads import baca_media
        if not re.fullmatch(r'(produk|bukti|foto)', folder) or not re.fullmatch(r'[0-9a-f]{32}\.jpg', nama):
            abort(404)
        data = baca_media(folder, nama)
        if data is None: abort(404)
        r = Response(data, mimetype='image/jpeg')
        r.headers['Content-Security-Policy'] = "default-src 'none'"
        # Nama berkas = 128-bit acak dan tiap unggahan baru berganti nama -> isinya tidak pernah berubah: aman di-cache 1 tahun
        r.headers['Cache-Control'] = 'private, max-age=3600' if folder == 'bukti' else 'public, max-age=31536000, immutable'   # bukti bayar jangan di cache bersama
        r.set_etag(nama[:-4]); return r.make_conditional(request)

    # ---- Frontend (satu origin dengan API: tanpa CORS, CSP 'self' tetap berlaku) ----
    # Halaman dilayani lewat URL pendek; berkas aset (js/css) tetap di /shared/... dan /<halaman>/...
    HALAMAN = {'landing': '/', 'login': '/masuk', 'register': '/daftar', 'lupa': '/lupa-password', 'customer': '/dashboard', 'admin': '/admin'}
    ASET = re.compile(r'\.(js|css|svg|png|jpe?g|webp|ico)$', re.I)

    REF = re.compile(r'(src|href)="(/(?:shared|landing|login|lupa|register|customer|admin|produk)/[A-Za-z0-9_.\-]+\.(?:js|css))"')
    TW_CDN = re.compile(r'<script src="https://cdn\.tailwindcss\.com"></script>\s*<script src="/shared/tailwind\.js"></script>')
    _html = {}      # folder -> (mtime, teks)

    def _mtime(rel):
        try: return int(os.stat(os.path.join(app.config['FRONTEND_DIR'], rel)).st_mtime)
        except OSError: return 0

    def _halaman(folder):
        """Sajikan HTML halaman. (1) Tiap aset lokal diberi ?v=<waktu ubah> agar bisa di-cache browser selamanya tapi langsung
        segar saat berkas berubah. (2) Bila frontend/shared/app.css ada (hasil `npm run css`), Tailwind CDN yang berat dibuang
        dan CSP diperketat otomatis."""
        akar = app.config['FRONTEND_DIR']; jalur = os.path.join(akar, folder, 'index.html')
        mt = os.stat(jalur).st_mtime
        if folder not in _html or _html[folder][0] != mt:
            with open(jalur, encoding='utf-8') as f: _html[folder] = (mt, f.read())
        html = _html[folder][1]
        if os.path.isfile(os.path.join(akar, 'shared', 'app.css')):
            html = TW_CDN.sub('<link rel="stylesheet" href="/shared/app.css">', html).replace(" 'unsafe-eval' https://cdn.tailwindcss.com", '')
            html = re.sub(r"<!-- 'unsafe-eval'[^>]*-->\n?", '', html)       # komentar yang sudah tidak relevan
        html = REF.sub(lambda m: f'{m.group(1)}="{m.group(2)}?v={_mtime(m.group(2)[1:])}"', html)
        r = Response(html, mimetype='text/html'); r.headers['Cache-Control'] = 'no-cache'
        return r

    @app.get('/favicon.ico')
    def favicon(): return redirect('/shared/favicon.ico', 301)

    @app.get('/')
    def beranda(): return _halaman('landing')

    @app.get('/masuk', strict_slashes=False)
    def halaman_masuk(): return _halaman('login')

    @app.get('/lupa-password', strict_slashes=False)
    def halaman_lupa(): return _halaman('lupa')

    @app.get('/daftar', strict_slashes=False)
    def halaman_daftar(): return _halaman('register')

    @app.get('/dashboard', strict_slashes=False)
    def halaman_customer(): return _halaman('customer')

    @app.get('/admin', strict_slashes=False)
    def halaman_admin(): return _halaman('admin')

    @app.get('/produk', strict_slashes=False)
    def daftar_produk(): return redirect('/#katalog')

    @app.get('/produk/<int:pid>')
    def halaman_produk(pid): return _halaman('produk')

    @app.get('/<path:p>')
    def frontend(p):
        if p.split('/')[0] in ('api', 'media'): abort(404)
        # Alamat lama (/login/index.html, /landing/, ...) dialihkan permanen ke URL pendek
        bagian = [x for x in p.split('/') if x]
        if bagian and bagian[0] in HALAMAN and (len(bagian) == 1 or (len(bagian) == 2 and bagian[1] == 'index.html')):
            qs = request.query_string.decode('latin-1')
            return redirect(HALAMAN[bagian[0]] + ('?' + qs if qs else ''), 301)
        if bagian[:1] == ['produk'] and bagian[1:] == ['index.html']:
            pid = request.args.get('id', '')
            return redirect(f'/produk/{pid}' if pid.isdigit() else '/produk', 301)
        if not ASET.search(p): abort(404)                # HTML hanya lewat URL pendek di atas
        akar = app.config['FRONTEND_DIR']
        aman = safe_join(akar, p)                       # tolak path absolut / '..' sebelum menyentuh sistem berkas
        if aman is None or not os.path.isfile(aman): abort(404)
        r = send_from_directory(akar, p, max_age=0)
        # URL berversi (?v=...) tidak pernah berubah isinya -> cache 1 tahun; tanpa versi -> selalu cek ulang
        r.headers['Cache-Control'] = 'public, max-age=31536000, immutable' if request.args.get('v') else 'no-cache'
        return r

    # ---- Kompresi gzip (JSON, HTML, JS, CSS) + pengukuran waktu; berkas statis dikompresi sekali lalu disimpan di memori ----
    KOMPRES = {'text/html', 'text/css', 'text/javascript', 'application/javascript', 'application/json', 'image/svg+xml'}
    _gz = {}

    @app.before_request
    def _mulai(): g.t0 = time.perf_counter()

    @app.after_request
    def kompres(r):
        if r.status_code != 200 or r.mimetype not in KOMPRES or 'Content-Encoding' in r.headers or r.is_streamed and not r.direct_passthrough: return r
        if 'gzip' not in request.headers.get('Accept-Encoding', ''): return r
        r.direct_passthrough = False
        data = r.get_data()
        if len(data) < 700: return r
        etag = r.headers.get('ETag'); kunci = (request.path, etag) if etag else None
        z = _gz.get(kunci) if kunci else None
        if z is None:
            z = gzip.compress(data, compresslevel=5, mtime=0)
            if kunci and len(_gz) < 300: _gz[kunci] = z
        r.set_data(z); r.headers['Content-Encoding'] = 'gzip'; r.headers.add('Vary', 'Accept-Encoding')
        return r

    @app.after_request
    def waktu(r):
        t0 = g.get('t0')
        if t0 is not None:
            ms = (time.perf_counter() - t0) * 1000
            r.headers['Server-Timing'] = f'app;dur={ms:.0f}'          # terlihat di DevTools > Network > Timing
            if ms > app.config['LAMBAT_MS']: app.logger.warning('LAMBAT %s %s %.0fms', request.method, request.path, ms)
        return r

    # ---- CORS: hanya origin yang didaftarkan; autentikasi lewat header Bearer (tanpa cookie) ----
    @app.after_request
    def header(r):
        o = request.headers.get('Origin')
        izin = app.config['CORS_ORIGINS']
        if o and (o in izin or '*' in izin):
            r.headers['Access-Control-Allow-Origin'] = o
            r.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
            r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            r.headers['Access-Control-Max-Age'] = '600'
            r.headers.add('Vary', 'Origin')
        r.headers['X-Content-Type-Options'] = 'nosniff'
        r.headers['X-Frame-Options'] = 'DENY'                       # cegah clickjacking
        r.headers['Referrer-Policy'] = 'same-origin'
        r.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.is_secure:
            r.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'   # hanya lewat HTTPS
        if r.mimetype == 'text/html':
            r.headers['Content-Security-Policy'] = "frame-ancestors 'none'"   # digabung (irisan) dengan CSP <meta> tiap halaman
        if request.path.startswith('/api/'):
            r.headers['Cache-Control'] = 'no-store'
        return r

    # ---- Penanganan galat: selalu JSON {"error": "..."} ----
    def _err(pesan, status):
        return jsonify({'error': pesan}), status

    def _rollback():
        # Galat yang sudah ditangani tidak diteruskan ke teardown, jadi batalkan transaksi setengah jalan di sini.
        d = g.get('db')
        if d is not None:
            d.rollback()

    @app.errorhandler(ApiError)
    def _api(e):
        _rollback()
        return _err(e.pesan, e.status)

    for kode, pesan in ((404, 'Data tidak ditemukan.'), (405, 'Metode tidak diizinkan.'), (413, 'Ukuran data terlalu besar.')):
        app.register_error_handler(kode, lambda e, p=pesan, k=kode: _err(p, k))

    @app.errorhandler(Exception)
    def _tak_terduga(e):
        from werkzeug.exceptions import HTTPException
        _rollback()
        if isinstance(e, HTTPException):
            return _err(e.description, e.code)
        app.logger.exception('Galat tak terduga')
        return _err('Terjadi kesalahan pada server.', 500)

    logging.basicConfig(level=logging.INFO)
    return app
