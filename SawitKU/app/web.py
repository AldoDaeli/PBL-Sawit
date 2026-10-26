"""Melayani frontend statis, URL pendek halaman, dan berkas unggahan (/media). Satu origin dengan API: tanpa CORS, CSP 'self' berlaku."""
import gzip, os, re

from flask import Response, abort, redirect, request

from .config import cfg
from .uploads import baca_media

# folder halaman -> URL pendek
HALAMAN = {'landing': '/', 'login': '/masuk', 'register': '/daftar', 'lupa': '/lupa-password', 'customer': '/dashboard', 'admin': '/admin'}
ASET = re.compile(r'\.(js|css|svg|png|jpe?g|webp|ico)$', re.I)
MEDIA_NAMA = re.compile(r'[0-9a-f]{32}\.jpg')
REF = re.compile(r'(src|href)="(/(?:shared|landing|login|lupa|register|customer|admin|produk|bayar)/[A-Za-z0-9_.\-]+\.(?:js|css))"')
TW_CDN = re.compile(r'<script src="https://cdn\.tailwindcss\.com"></script>\s*<script src="/shared/tailwind\.js"></script>')
# Tipe berkas ditetapkan sendiri (bukan dari registri OS, yang di Windows kadang salah untuk .js)
TIPE = {'.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.webp': 'image/webp', '.ico': 'image/x-icon'}
KOMPRES = {'.js', '.css', '.svg'}
_html = {}      # folder -> (mtime, teks)
_aset = {}      # jalur -> ((mtime_ns, ukuran), isi, isi gzip | None): aset kecil disimpan di memori beserta versi terkompresnya


def _mtime(rel):
    try: return int(os.stat(os.path.join(cfg['FRONTEND_DIR'], rel)).st_mtime)
    except OSError: return 0


def halaman(folder):
    """Sajikan HTML halaman. (1) Tiap aset lokal diberi ?v=<waktu ubah> agar bisa di-cache browser selamanya tapi langsung segar
    saat berkas berubah. (2) Bila frontend/shared/app.css ada (hasil `npm run css`), Tailwind CDN yang berat dibuang dan CSP diperketat."""
    akar = cfg['FRONTEND_DIR']; jalur = os.path.join(akar, folder, 'index.html')
    mt = os.stat(jalur).st_mtime
    if folder not in _html or _html[folder][0] != mt:
        with open(jalur, encoding='utf-8') as f: _html[folder] = (mt, f.read())
    html = _html[folder][1]
    if os.path.isfile(os.path.join(akar, 'shared', 'app.css')):
        html = TW_CDN.sub('<link rel="stylesheet" href="/shared/app.css">', html).replace(" 'unsafe-eval' https://cdn.tailwindcss.com", '')
        html = re.sub(r"<!-- 'unsafe-eval'[^>]*-->\n?", '', html)
    html = REF.sub(lambda m: f'{m.group(1)}="{m.group(2)}?v={_mtime(m.group(2)[1:])}"', html)
    return Response(html, mimetype='text/html', headers={'Cache-Control': 'no-cache'})


def _kirim_aset(jalur, cache):
    """Kirim berkas statis: ETag + Last-Modified (balasan 304 otomatis) dan gzip yang di-cache di memori."""
    st = os.stat(jalur); kunci = (st.st_mtime_ns, st.st_size); ext = os.path.splitext(jalur)[1].lower()
    c = _aset.get(jalur)
    if not c or c[0] != kunci:
        with open(jalur, 'rb') as f: isi = f.read()
        c = _aset[jalur] = (kunci, isi, gzip.compress(isi, compresslevel=5, mtime=0) if ext in KOMPRES and len(isi) >= 700 else None)
    pakai_gzip = c[2] is not None and 'gzip' in request.headers.get('Accept-Encoding', '').lower()
    r = Response(c[2] if pakai_gzip else c[1], mimetype=TIPE.get(ext, 'application/octet-stream'))
    r.headers['Cache-Control'] = cache
    if c[2] is not None: r.headers['Vary'] = 'Accept-Encoding'
    if pakai_gzip: r.headers['Content-Encoding'] = 'gzip'
    r.set_etag(f'{kunci[0]:x}-{kunci[1]:x}' + ('-gz' if pakai_gzip else ''))
    r.last_modified = st.st_mtime
    return r.make_conditional(request, accept_ranges=False)


def pasang(app):
    """Daftarkan rute web. Rute /api sudah terdaftar (blueprint); catch-all di bawah menolak /api/* yang tidak dikenal dengan 404 JSON."""

    @app.get('/media/<folder>/<nama>')
    def media(folder, nama):
        if folder not in ('produk', 'bukti', 'foto', 'terima') or not MEDIA_NAMA.fullmatch(nama): abort(404)
        data = baca_media(folder, nama)      # gambar ada di tabel media; koneksi ditutup di teardown_request
        if data is None: abort(404)
        # Nama berkas = 128-bit acak dan tiap unggahan baru berganti nama -> isinya tidak pernah berubah: aman di-cache 1 tahun.
        # Bukti bayar & foto terima bersifat privat: jangan di-cache bersama.
        cache = 'private, max-age=3600' if folder in ('bukti', 'terima') else 'public, max-age=31536000, immutable'
        r = Response(data, mimetype='image/jpeg', headers={'Cache-Control': cache, 'Content-Security-Policy': "default-src 'none'"})
        r.set_etag(nama[:-4])
        return r.make_conditional(request, accept_ranges=False)

    @app.get('/favicon.ico')
    def favicon(): return redirect('/shared/favicon.ico', 301)

    for folder, url in (('landing', '/'), ('login', '/masuk'), ('lupa', '/lupa-password'), ('register', '/daftar'),
                        ('customer', '/dashboard'), ('admin', '/admin')):
        # strict_slashes=False: '/masuk' dan '/masuk/' sama-sama dilayani (tanpa pengalihan)
        app.add_url_rule(url, 'halaman_' + folder, (lambda f: lambda: halaman(f))(folder), methods=['GET'], strict_slashes=False)

    @app.get('/produk', strict_slashes=False)
    def daftar_produk(): return redirect('/#katalog', 307)

    @app.get('/produk/<pid>')
    def halaman_produk(pid):
        if pid == 'index.html':                                        # alamat lama: /produk/index.html?id=5
            i = request.args.get('id', '')
            return redirect(f'/produk/{i}' if i.isdigit() else '/produk', 301)
        if not pid.isdigit(): return frontend('produk/' + pid)         # /produk/script.js, style.css
        return halaman('produk')

    @app.get('/bayar/<oid>')
    def halaman_bayar(oid):
        if not oid.isdigit(): return frontend('bayar/' + oid)          # /bayar/script.js, style.css
        return halaman('bayar')

    @app.get('/<path:p>')
    def frontend(p):
        if p.split('/')[0] in ('api', 'media'): abort(404)
        # Alamat lama (/login/index.html, /landing/, ...) dialihkan permanen ke URL pendek
        bagian = [x for x in p.split('/') if x]
        if bagian and bagian[0] in HALAMAN and (len(bagian) == 1 or (len(bagian) == 2 and bagian[1] == 'index.html')):
            qs = request.query_string.decode('latin-1')
            return redirect(HALAMAN[bagian[0]] + ('?' + qs if qs else ''), 301)
        if not ASET.search(p): abort(404)                              # HTML hanya lewat URL pendek di atas
        akar = os.path.realpath(cfg['FRONTEND_DIR'])
        aman = os.path.realpath(os.path.join(akar, p))                 # tolak path absolut / '..' / symlink keluar folder
        if os.path.commonpath([akar, aman]) != akar or not os.path.isfile(aman): abort(404)
        # URL berversi (?v=...) tidak pernah berubah isinya -> cache 1 tahun; tanpa versi -> selalu cek ulang
        return _kirim_aset(aman, 'public, max-age=31536000, immutable' if request.args.get('v') else 'no-cache')
