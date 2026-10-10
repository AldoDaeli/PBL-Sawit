import os
import click
from .db import connect
from .security import hash_pw, now_ms
from .validators import username_ok, email_ok, password_ok

TABEL = ['sesi', 'gagal_login', 'otp_daftar', 'otp_email', 'ulasan', 'favorit', 'keranjang', 'pesanan_item', 'pesanan', 'pesan_kontak', 'chat_pesan', 'produk', 'pengguna']


def daftarkan(app):
    @app.cli.command('init-db')
    def init_db():
        """Buat semua tabel dari schema.sql (aman diulang: CREATE TABLE IF NOT EXISTS)."""
        teks = open(os.path.join(os.path.dirname(app.root_path), 'schema.sql'), encoding='utf-8').read()
        teks = '\n'.join(l for l in teks.splitlines() if not l.strip().startswith('--'))
        db = connect()
        for stmt in (s.strip() for s in teks.split(';')):
            if stmt:
                db.run(stmt)
        db.commit(); db.close()
        click.echo('Tabel siap.')

    @app.cli.command('seed')
    @click.option('--riwayat/--tanpa-riwayat', default=True, help='Tambahkan riwayat pesanan ±4 bulan untuk grafik.')
    @click.option('--reset', is_flag=True, help='KOSONGKAN semua tabel lebih dulu (menghapus seluruh data!).')
    def seed(riwayat, reset):
        """Isi data awal (produk, akun demo, pesanan, ulasan)."""
        from . import seed as s
        db = connect()
        if reset:
            click.confirm('Semua data akan dihapus. Lanjutkan?', abort=True)
            db.run('SET FOREIGN_KEY_CHECKS=0')
            for t in TABEL: db.run(f'TRUNCATE TABLE {t}')
            db.run('SET FOREIGN_KEY_CHECKS=1')
        if not s.kosong(db):
            raise click.ClickException('Database sudah berisi data. Pakai --reset bila ingin mengulang dari nol.')
        kredensial = s.jalankan(db, riwayat, acak=True); db.close()
        click.echo('Seed selesai. Password akun demo diacak; catat sekarang (tidak ditampilkan lagi):')
        for u, pw in kredensial: click.echo(f'  {u} / {pw}')
        click.echo('PENTING: hapus akun demo sebelum produksi.')

    @app.cli.command('buat-admin')
    @click.argument('username')
    @click.argument('email')
    def buat_admin(username, email):
        """Buat akun admin baru; password ditanyakan secara interaktif."""
        if not username_ok(username): raise click.ClickException('Username 4–20 karakter (huruf, angka, garis bawah).')
        if not email_ok(email): raise click.ClickException('Format email tidak valid.')
        pw = click.prompt('Password', hide_input=True, confirmation_prompt=True)
        if not password_ok(pw): raise click.ClickException('Password 8–64 karakter, kombinasi huruf dan angka.')
        db = connect()
        db.run('INSERT INTO pengguna (username,email,hash,peran,aktif,dibuat) VALUES (%s,%s,%s,%s,1,%s)',
               (username, email, hash_pw(pw), 'admin', now_ms()))
        db.commit(); db.close()
        click.echo(f'Admin {username} dibuat.')
