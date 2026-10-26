"""Perintah pengelolaan. Jalankan:  python manage.py --help
   init-db | seed | buat-admin | impor-media"""
import os, time

import click

from app.config import cfg, AKAR
from app.db import connect
from app.security import hash_pw, now_ms
from app.validators import username_ok, email_ok, password_ok

TABEL = ['otp_reset', 'ulasan_balas', 'media', 'sesi', 'gagal_login', 'otp_daftar', 'otp_email', 'ulasan', 'favorit', 'keranjang',
         'pesanan_item', 'pesanan', 'pesan_kontak', 'chat_pesan', 'produk', 'pengguna']
# Kolom yang ditambahkan setelah versi awal: database lama dilengkapi otomatis oleh init-db (sudah ada = dilewati)
KOLOM_PESANAN = ['ditolak INT NOT NULL DEFAULT 0', 'kurir VARCHAR(30) NULL', 'resi VARCHAR(40) NULL', 't_bayar BIGINT NULL', 't_proses BIGINT NULL',
                 't_kirim BIGINT NULL', 't_selesai BIGINT NULL', 'metode VARCHAR(12) NULL', 'midtrans_id VARCHAR(50) NULL',
                 'midtrans_status VARCHAR(20) NULL', 'midtrans_data TEXT NULL', 't_sampai BIGINT NULL', 'foto_terima VARCHAR(255) NULL',
                 'otomatis TINYINT NOT NULL DEFAULT 0']


@click.group()
def cli(): """Pengelolaan database & akun SawitKu."""


@cli.command('init-db')
def init_db():
    """Buat semua tabel dari schema.sql (aman diulang: CREATE TABLE IF NOT EXISTS) dan lengkapi kolom baru di database lama."""
    teks = open(os.path.join(AKAR, 'schema.sql'), encoding='utf-8').read()
    teks = '\n'.join(l for l in teks.splitlines() if not l.strip().startswith('--'))
    db = connect()
    for stmt in (s.strip() for s in teks.split(';')):
        if stmt: db.run(stmt)
    db.commit()
    for kolom in KOLOM_PESANAN:
        try: db.run(f'ALTER TABLE pesanan ADD COLUMN {kolom}'); db.commit()
        except Exception as e:
            db.rollback()
            if not any(k in str(e) for k in ('1060', 'Duplicate column')): raise
    db.close()
    click.echo('Tabel siap.')


@cli.command('impor-media')
def impor_media():
    """Pindahkan gambar lama di folder uploads/ ke database (sekali saja setelah upgrade; aman diulang)."""
    akar, n, db = cfg['UPLOAD_DIR'], 0, connect()
    for folder in ('produk', 'bukti', 'foto'):
        d = os.path.join(akar, folder)
        if not os.path.isdir(d): continue
        for nama in os.listdir(d):
            if not nama.endswith('.jpg') or db.one('SELECT 1 AS x FROM media WHERE folder=%s AND nama=%s', (folder, nama)): continue
            with open(os.path.join(d, nama), 'rb') as f:
                db.run('INSERT INTO media (folder,nama,data,dibuat) VALUES (%s,%s,%s,%s)', (folder, nama, f.read(), int(time.time() * 1000))); n += 1
    db.commit(); db.close()
    click.echo(f'{n} gambar dipindahkan ke database.')


@cli.command('seed')
@click.option('--pesanan-contoh', is_flag=True, help='Buat pesanan contoh (hanya demo lokal; tidak lunas di Midtrans sehingga tidak masuk grafik).')
@click.option('--riwayat/--tanpa-riwayat', default=True, help='Dengan --pesanan-contoh: tambahkan riwayat ±4 bulan.')
@click.option('--reset', is_flag=True, help='KOSONGKAN semua tabel lebih dulu (menghapus seluruh data!).')
def seed(pesanan_contoh, riwayat, reset):
    """Isi data awal (produk, akun demo, pesanan, ulasan)."""
    from app import seed as s
    db = connect()
    if reset:
        click.confirm('Semua data akan dihapus. Lanjutkan?', abort=True)
        db.run('SET FOREIGN_KEY_CHECKS=0')
        for t in TABEL: db.run(f'TRUNCATE TABLE {t}')
        db.run('SET FOREIGN_KEY_CHECKS=1')
    if not s.kosong(db):
        raise click.ClickException('Database sudah berisi data. Pakai --reset bila ingin mengulang dari nol.')
    kredensial = s.jalankan(db, riwayat, acak=True, pesanan=pesanan_contoh); db.close()
    click.echo('Seed selesai. Password akun demo diacak; catat sekarang (tidak ditampilkan lagi):')
    for u, pw in kredensial: click.echo(f'  {u} / {pw}')
    click.echo('PENTING: hapus akun demo sebelum produksi.')


@cli.command('buat-admin')
@click.argument('username')
@click.argument('email')
def buat_admin(username, email):
    """Buat akun admin baru; password ditanyakan secara interaktif."""
    if not username_ok(username): raise click.ClickException('Username 4–20 karakter (huruf, angka, garis bawah).')
    if not email_ok(email): raise click.ClickException('Format email tidak valid.')
    pw = click.prompt('Password', hide_input=True, confirmation_prompt=True)
    if not password_ok(pw): raise click.ClickException('Password 8–64 karakter, kombinasi huruf dan angka.')
    db = connect()
    db.run('INSERT INTO pengguna (username,email,hash,peran,aktif,dibuat) VALUES (%s,%s,%s,%s,1,%s)', (username, email, hash_pw(pw), 'admin', now_ms()))
    db.commit(); db.close()
    click.echo(f'Admin {username} dibuat.')


if __name__ == '__main__':
    cli()
