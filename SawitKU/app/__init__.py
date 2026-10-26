"""SawitKu: REST API Flask + frontend statis dalam satu aplikasi. `create_app()` menyusun semuanya (application factory)."""
import logging

from flask import Flask

from . import config, docs, middleware, web
from .middleware import IpProxy
from .security import reset_laju


def create_app(overrides=None):
    cfg = config.muat(overrides)
    app = Flask('sawitku', static_folder=None)          # frontend dilayani web.py, bukan rute /static bawaan Flask
    app.json.sort_keys = False                          # urutan kolom JSON sama dengan yang disusun serializer
    app.json.ensure_ascii = False
    app.url_map.strict_slashes = False
    app.config['MAX_CONTENT_LENGTH'] = cfg['MAKS_BODY_MB'] * 1048576
    app.wsgi_app = IpProxy(app.wsgi_app)                # IP klien asli di belakang proxy (PROXY_HOPS)
    reset_laju()

    from .routes import api
    app.register_blueprint(api)
    docs.pasang(app)
    web.pasang(app)                                     # setelah /api: catch-all frontend tidak menelan API
    middleware.pasang(app)                              # hook request, CORS, gzip, penangan galat JSON

    logging.basicConfig(level=logging.INFO)
    return app
