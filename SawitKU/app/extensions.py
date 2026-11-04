"""Ekstensi Flask yang dipakai bersama: SQLAlchemy (ORM) dan Flask-Migrate (Alembic).
Dibuat di sini (belum terikat ke app) lalu dipasang di `create_app()` lewat `init_app` agar tidak ada import melingkar."""
import sqlite3

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()


@event.listens_for(Engine, 'connect')
def _aktifkan_fk_sqlite(dbapi_conn, _rec):
    """SQLite mengabaikan FOREIGN KEY (ON DELETE CASCADE / SET NULL) kecuali diaktifkan per koneksi. MariaDB tidak butuh ini."""
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor(); cur.execute('PRAGMA foreign_keys=ON'); cur.close()
