"""Lapisan basis data tipis di atas PyMySQL (MariaDB) + konteks per-request.
Satu koneksi per request (dibuat saat pertama dipakai); commit saat request sukses, rollback bila ada galat.
Konteks request disimpan di `flask.g`, jadi otomatis terpisah antar request dan antar thread."""
import sqlite3

from flask import g, has_app_context

from .config import cfg

try:
    import pymysql
    import pymysql.cursors
    _IE = (pymysql.err.IntegrityError,)
except ImportError:  # hanya untuk pengujian tanpa PyMySQL
    pymysql, _IE = None, ()

IntegrityErrors = _IE + (sqlite3.IntegrityError,)


class Db:
    def __init__(self, conn): self.conn = conn

    def all(self, sql, args=()):
        with self.conn.cursor() as c:
            c.execute(sql, args)
            return list(c.fetchall())

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def run(self, sql, args=()):
        """Jalankan INSERT/UPDATE/DELETE. Mengembalikan (lastrowid, rowcount)."""
        with self.conn.cursor() as c:
            c.execute(sql, args)
            return c.lastrowid, c.rowcount

    def commit(self): self.conn.commit()
    def rollback(self): self.conn.rollback()
    def close(self): self.conn.close()


def connect():
    return Db(pymysql.connect(
        host=cfg['DB_HOST'], port=cfg['DB_PORT'], user=cfg['DB_USER'], password=cfg['DB_PASSWORD'],
        database=cfg['DB_NAME'], charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    ))


# ---------------- Konteks request ----------------
class Konteks:
    """Keadaan satu request: koneksi DB (lazy), token JWT baru bila sesi diperpanjang, dan IP klien."""
    __slots__ = ('db', 'token_baru', 'ip')

    def __init__(self): self.db, self.token_baru, self.ip = None, None, '?'


def mulai_konteks():
    """Dipanggil di awal request (before_request): siapkan konteks baru di `g`."""
    k = Konteks(); g._sk = k; return k


def konteks():
    if not has_app_context(): return Konteks()        # di luar request (CLI, skrip): konteks sekali pakai
    k = g.get('_sk')
    if k is None: k = g._sk = Konteks()
    return k


def get_db():
    k = konteks()
    if k.db is None: k.db = connect()
    return k.db


def simpan():
    """Commit transaksi request ini (bila koneksi pernah dibuka)."""
    k = g.get('_sk') if has_app_context() else None
    if k is not None and k.db is not None: k.db.commit()


def batal():
    k = g.get('_sk') if has_app_context() else None
    if k is not None and k.db is not None: k.db.rollback()


def tutup(k):
    """Akhir request: transaksi yang menggantung dibatalkan, koneksi ditutup."""
    if k.db is None: return
    try: k.db.rollback()
    finally:
        k.db.close(); k.db = None
