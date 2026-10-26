"""Dokumentasi API otomatis: `/api/docs` (daftar endpoint untuk dibaca manusia) dan `/api/openapi.json` (skema OpenAPI 3 ringkas).
Dibuat dari metadata rute (`routes.DAFTAR`), tanpa pustaka tambahan dan tanpa memuat apa pun dari internet."""
from html import escape

from flask import Response, jsonify

from .routes import DAFTAR

AKSES = {'publik': 'Tanpa login', 'login': 'Perlu login', 'customer': 'Khusus customer', 'admin': 'Khusus admin'}
TAMPIL = ('Akun', 'Katalog', 'Belanja', 'Pesanan', 'Pembayaran', 'Ulasan', 'Chat', 'Admin', 'Sistem')


def _urut():
    return sorted(DAFTAR, key=lambda e: (TAMPIL.index(e['tag']) if e['tag'] in TAMPIL else 99, e['path'], e['metode']))


def openapi():
    paths = {}
    for e in _urut():
        jalur = e['path'].replace('<int:', '{').replace('>', '}')
        for m in e['metode']:
            op = {'summary': e['ringkas'], 'tags': [e['tag']], 'responses': {str(e['status']): {'description': 'Berhasil'}}}
            if e['akses'] != 'publik': op['security'] = [{'bearerAuth': []}]; op['description'] = AKSES[e['akses']]
            paths.setdefault(jalur, {})[m.lower()] = op
    return {'openapi': '3.0.3', 'info': {'title': 'SawitKu API', 'version': '2.0', 'description': 'REST API toko SawitKu (Flask). Autentikasi: JWT Bearer dari POST /api/auth/masuk.'},
            'paths': paths, 'components': {'securitySchemes': {'bearerAuth': {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'}}}}


def halaman():
    baris, tag = [], None
    for e in _urut():
        if e['tag'] != tag:
            tag = e['tag']; baris.append(f'<tr class="g"><td colspan="4">{escape(tag)}</td></tr>')
        jalur = escape(e['path'].replace('<int:', '{').replace('>', '}'))
        baris.append(f'<tr><td><b class="m {e["metode"][0].lower()}">{"/".join(e["metode"])}</b></td><td><code>{jalur}</code></td>'
                     f'<td>{escape(e["ringkas"])}</td><td>{AKSES[e["akses"]]}</td></tr>')
    return ('<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SawitKu API</title>'
            '<style>body{font:14px/1.5 system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#1c2b1f}table{border-collapse:collapse;width:100%}'
            'td{padding:.4rem .6rem;border-bottom:1px solid #dde5dd;vertical-align:top}tr.g td{background:#eaf2ea;font-weight:700;padding-top:.8rem}'
            'code{font-size:13px}.m{font-size:11px;padding:.1rem .4rem;border-radius:4px;background:#d9e6f7}.post{background:#d8f0dc}.put{background:#faebc8}.delete{background:#f8d7d7}'
            '</style></head><body><h1>SawitKu API <small>v2.0</small></h1>'
            '<p>Semua respons berbentuk <code>{"data": ...}</code> atau <code>{"error": "..."}</code>. Endpoint bertanda login memakai header '
            '<code>Authorization: Bearer &lt;token&gt;</code>; token didapat dari <code>POST /api/auth/masuk</code>. Skema mesin-baca: <a href="/api/openapi.json">/api/openapi.json</a>.</p>'
            f'<table>{"".join(baris)}</table></body></html>')


def pasang(app):
    app.add_url_rule('/api/docs', 'api_docs', lambda: Response(halaman(), mimetype='text/html'), methods=['GET'])
    app.add_url_rule('/api/openapi.json', 'api_openapi', lambda: jsonify(openapi()), methods=['GET'])
