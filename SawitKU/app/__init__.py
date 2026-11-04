"""SawitKu: REST API Flask + frontend statis dalam satu aplikasi. `create_app()` menyusun semuanya (application factory)."""
import logging, os

from flask import Flask

from . import aktivitas, config, docs, middleware, models, web   # noqa: F401  (models: daftarkan tabel ke metadata SQLAlchemy)
from .extensions import db as orm, migrate
from .middleware import IpProxy
from .security import reset_laju


def create_app(overrides=None):
    cfg = config.muat(overrides)
    app = Flask('sawitku', static_folder=None,          # aset statis dilayani web.py, bukan rute /static bawaan Flask
                template_folder=os.path.join(os.path.dirname(__file__), 'templates'))   # halaman = template Jinja2
    app.json.sort_keys = False                          # urutan kolom JSON sama dengan yang disusun serializer
    app.json.ensure_ascii = False
    app.url_map.strict_slashes = False
    app.config['MAX_CONTENT_LENGTH'] = cfg['MAKS_BODY_MB'] * 1048576
    app.config['SQLALCHEMY_DATABASE_URI'] = cfg['SQLALCHEMY_DATABASE_URI']
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    orm.init_app(app)                                   # ORM SQLAlchemy (app/models.py)
    migrate.init_app(app, orm)                          # perintah `flask db ...` (folder migrations/)
    app.wsgi_app = IpProxy(app.wsgi_app)                # IP klien asli di belakang proxy (PROXY_HOPS)
    reset_laju()

    from .routes import api
    app.register_blueprint(api)
    docs.pasang(app)
    web.pasang(app)                                     # setelah /api: catch-all frontend tidak menelan API
    middleware.pasang(app)                              # hook request, CORS, gzip, penangan galat JSON

    logging.basicConfig(level=logging.INFO)
    aktivitas.siapkan()                                 # berkas logs/aktivitas.log (masuk/keluar)
    return app
