"""Lapisan basis data tipis di atas PyMySQL (MariaDB). Satu koneksi per request; commit otomatis bila sukses."""
import sqlite3
from flask import g, current_app

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
    cfg = current_app.config
    return Db(pymysql.connect(
        host=cfg['DB_HOST'], port=cfg['DB_PORT'], user=cfg['DB_USER'], password=cfg['DB_PASSWORD'],
        database=cfg['DB_NAME'], charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    ))


def get_db():
    if 'db' not in g:
        g.db = connect()
    return g.db


def _teardown(exc):
    db = g.pop('db', None)
    if db is None:
        return
    try:
        db.commit() if exc is None else db.rollback()
    finally:
        db.close()


def init_app(app):
    app.teardown_appcontext(_teardown)
