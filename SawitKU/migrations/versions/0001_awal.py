"""Skema awal SawitKu (17 tabel) -- setara schema.sql.

Database BARU: `flask --app main db upgrade`.
Database LAMA yang dibuat dari schema.sql / `manage.py init-db`: `flask --app main db stamp head` (tanpa mengubah tabel).

Revision ID: 0001_awal
Revises:
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0001_awal'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pengguna',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(20), nullable=False),
        sa.Column('email', sa.String(100), nullable=False),
        sa.Column('hash', sa.String(255), nullable=False),
        sa.Column('peran', sa.String(10), nullable=False, server_default='customer'),
        sa.Column('aktif', sa.SmallInteger(), nullable=False, server_default='1'),
        sa.Column('foto', sa.String(255), nullable=True),
        sa.Column('telepon', sa.String(20), nullable=True),
        sa.Column('alamat', sa.String(255), nullable=True),
        sa.Column('kota', sa.String(60), nullable=True),
        sa.Column('kode_pos', sa.String(10), nullable=True),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("peran IN ('admin','customer')", name='ck_pengguna_peran'),
        sa.UniqueConstraint('username', name='uq_pengguna_username'),
        sa.UniqueConstraint('email', name='uq_pengguna_email'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'produk',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nama', sa.String(80), nullable=False),
        sa.Column('kategori', sa.String(40), nullable=False),
        sa.Column('harga', sa.Integer(), nullable=False),
        sa.Column('stok', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('terjual', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rating', sa.Numeric(2, 1, asdecimal=False), nullable=False, server_default='0'),
        sa.Column('best_seller', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('gambar', sa.String(500), nullable=False),
        sa.Column('deskripsi', sa.String(400), nullable=False, server_default=''),
        sa.Column('spesifikasi', sa.Text(), nullable=False),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('harga >= 0', name='ck_produk_harga'),
        sa.CheckConstraint('stok >= 0', name='ck_produk_stok'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('idx_produk_kategori', 'produk', ['kategori'])
    op.create_table(
        'keranjang',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('produk_id', sa.Integer(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.CheckConstraint('qty > 0', name='ck_keranjang_qty'),
        sa.ForeignKeyConstraint(['user_id'], ['pengguna.id'], ondelete='CASCADE', name='fk_keranjang_user_id'),
        sa.ForeignKeyConstraint(['produk_id'], ['produk.id'], ondelete='CASCADE', name='fk_keranjang_produk_id'),
        sa.PrimaryKeyConstraint('user_id', 'produk_id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'favorit',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('produk_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['pengguna.id'], ondelete='CASCADE', name='fk_favorit_user_id'),
        sa.ForeignKeyConstraint(['produk_id'], ['produk.id'], ondelete='CASCADE', name='fk_favorit_produk_id'),
        sa.PrimaryKeyConstraint('user_id', 'produk_id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'pesanan',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('total', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='menunggu_bayar'),
        sa.Column('bukti', sa.String(255), nullable=True),
        sa.Column('alasan', sa.String(255), nullable=False, server_default=''),
        sa.Column('penerima', sa.String(80), nullable=False, server_default=''),
        sa.Column('telepon', sa.String(20), nullable=False, server_default=''),
        sa.Column('alamat', sa.String(255), nullable=False, server_default=''),
        sa.Column('kota', sa.String(60), nullable=False, server_default=''),
        sa.Column('kode_pos', sa.String(10), nullable=False, server_default=''),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.Column('batas_bayar', sa.BigInteger(), nullable=False),
        sa.Column('ditolak', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('kurir', sa.String(30), nullable=True),
        sa.Column('resi', sa.String(40), nullable=True),
        sa.Column('t_bayar', sa.BigInteger(), nullable=True),
        sa.Column('t_proses', sa.BigInteger(), nullable=True),
        sa.Column('t_kirim', sa.BigInteger(), nullable=True),
        sa.Column('t_selesai', sa.BigInteger(), nullable=True),
        sa.Column('metode', sa.String(12), nullable=True),
        sa.Column('midtrans_id', sa.String(50), nullable=True),
        sa.Column('midtrans_status', sa.String(20), nullable=True),
        sa.Column('midtrans_data', sa.Text(), nullable=True),
        sa.Column('t_sampai', sa.BigInteger(), nullable=True),
        sa.Column('foto_terima', sa.String(255), nullable=True),
        sa.Column('otomatis', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.CheckConstraint("status IN ('menunggu_bayar','menunggu_verifikasi','diproses','dikirim','selesai','dibatalkan')", name='ck_pesanan_status'),
        sa.ForeignKeyConstraint(['user_id'], ['pengguna.id'], ondelete='CASCADE', name='fk_pesanan_user_id'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('idx_pesanan_user', 'pesanan', ['user_id', 'dibuat'])
    op.create_index('idx_pesanan_status', 'pesanan', ['status', 'batas_bayar'])
    op.create_table(
        'pesanan_item',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pesanan_id', sa.Integer(), nullable=False),
        sa.Column('produk_id', sa.Integer(), nullable=True),
        sa.Column('nama', sa.String(80), nullable=False),
        sa.Column('gambar', sa.String(500), nullable=False),
        sa.Column('harga', sa.Integer(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.CheckConstraint('qty > 0', name='ck_pesanan_item_qty'),
        sa.ForeignKeyConstraint(['pesanan_id'], ['pesanan.id'], ondelete='CASCADE', name='fk_pesanan_item_pesanan_id'),
        sa.ForeignKeyConstraint(['produk_id'], ['produk.id'], ondelete='SET NULL', name='fk_pesanan_item_produk_id'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('idx_item_pesanan', 'pesanan_item', ['pesanan_id'])
    op.create_table(
        'ulasan',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('produk_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.SmallInteger(), nullable=False),
        sa.Column('teks', sa.String(300), nullable=False),
        sa.Column('balasan_teks', sa.String(300), nullable=True),
        sa.Column('balasan_dibuat', sa.BigInteger(), nullable=True),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('rating BETWEEN 1 AND 5', name='ck_ulasan_rating'),
        sa.UniqueConstraint('produk_id', 'user_id', name='uq_ulasan_produk_id_user_id'),
        sa.ForeignKeyConstraint(['produk_id'], ['produk.id'], ondelete='CASCADE', name='fk_ulasan_produk_id'),
        sa.ForeignKeyConstraint(['user_id'], ['pengguna.id'], ondelete='CASCADE', name='fk_ulasan_user_id'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'pesan_kontak',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nama', sa.String(100), nullable=False),
        sa.Column('email', sa.String(100), nullable=False),
        sa.Column('jenis', sa.String(20), nullable=False),
        sa.Column('isi', sa.String(500), nullable=False),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'log_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(30), nullable=False, server_default=''),
        sa.Column('peran', sa.String(10), nullable=False, server_default=''),
        sa.Column('aksi', sa.String(40), nullable=False),
        sa.Column('kategori', sa.String(20), nullable=False, server_default=''),
        sa.Column('target', sa.String(80), nullable=False, server_default=''),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(60), nullable=False, server_default=''),
        sa.Column('perangkat', sa.String(200), nullable=False, server_default=''),
        sa.Column('waktu', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('idx_audit_waktu', 'log_audit', ['waktu'])
    op.create_index('idx_audit_user', 'log_audit', ['user_id', 'waktu'])
    op.create_index('idx_audit_kategori', 'log_audit', ['kategori', 'waktu'])
    op.create_table(
        'sesi',
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kedaluwarsa', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['pengguna.id'], ondelete='CASCADE', name='fk_sesi_user_id'),
        sa.PrimaryKeyConstraint('token_hash'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('idx_sesi_exp', 'sesi', ['kedaluwarsa'])
    op.create_table(
        'gagal_login',
        sa.Column('kunci', sa.String(100), nullable=False),
        sa.Column('n', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('blokir_hingga', sa.BigInteger(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('kunci'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'otp_daftar',
        sa.Column('email', sa.String(100), nullable=False),
        sa.Column('username', sa.String(20), nullable=False),
        sa.Column('hash', sa.String(255), nullable=False),
        sa.Column('kode_hash', sa.String(64), nullable=False),
        sa.Column('garam', sa.String(32), nullable=False),
        sa.Column('kedaluwarsa', sa.BigInteger(), nullable=False),
        sa.Column('salah', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('kirim_n', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('kirim_terakhir', sa.BigInteger(), nullable=False),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('email'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'otp_email',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(100), nullable=False),
        sa.Column('kode_hash', sa.String(64), nullable=False),
        sa.Column('garam', sa.String(32), nullable=False),
        sa.Column('kedaluwarsa', sa.BigInteger(), nullable=False),
        sa.Column('salah', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('kirim_n', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('kirim_terakhir', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['pengguna.id'], ondelete='CASCADE', name='fk_otp_email_user_id'),
        sa.PrimaryKeyConstraint('user_id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'chat_pesan',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('dari', sa.String(8), nullable=False),
        sa.Column('admin_id', sa.Integer(), nullable=True),
        sa.Column('isi', sa.String(1000), nullable=False),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.Column('dibaca', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['pengguna.id'], ondelete='CASCADE', name='fk_chat_pesan_user_id'),
        sa.ForeignKeyConstraint(['admin_id'], ['pengguna.id'], ondelete='SET NULL', name='fk_chat_pesan_admin_id'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('idx_chat_user', 'chat_pesan', ['user_id', 'id'])
    op.create_index('idx_chat_belum', 'chat_pesan', ['dari', 'dibaca', 'user_id'])
    op.create_table(
        'media',
        sa.Column('folder', sa.String(10), nullable=False),
        sa.Column('nama', sa.String(40), nullable=False),
        sa.Column('data', sa.LargeBinary().with_variant(mysql.LONGBLOB(), 'mysql', 'mariadb'), nullable=False),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('folder', 'nama'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_table(
        'ulasan_balas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ulasan_id', sa.Integer(), nullable=False),
        sa.Column('dari', sa.String(8), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('teks', sa.String(300), nullable=False),
        sa.Column('dibuat', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['ulasan_id'], ['ulasan.id'], ondelete='CASCADE', name='fk_ulasan_balas_ulasan_id'),
        sa.ForeignKeyConstraint(['user_id'], ['pengguna.id'], ondelete='SET NULL', name='fk_ulasan_balas_user_id'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('idx_ulasan_balas', 'ulasan_balas', ['ulasan_id', 'id'])
    op.create_table(
        'otp_reset',
        sa.Column('email', sa.String(100), nullable=False),
        sa.Column('kode_hash', sa.String(64), nullable=False),
        sa.Column('garam', sa.String(32), nullable=False),
        sa.Column('kedaluwarsa', sa.BigInteger(), nullable=False),
        sa.Column('salah', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('kirim_n', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('kirim_terakhir', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('email'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )


def downgrade():
    op.drop_table('otp_reset')
    op.drop_table('ulasan_balas')
    op.drop_table('media')
    op.drop_table('chat_pesan')
    op.drop_table('otp_email')
    op.drop_table('otp_daftar')
    op.drop_table('gagal_login')
    op.drop_table('sesi')
    op.drop_table('log_audit')
    op.drop_table('pesan_kontak')
    op.drop_table('ulasan')
    op.drop_table('pesanan_item')
    op.drop_table('pesanan')
    op.drop_table('favorit')
    op.drop_table('keranjang')
    op.drop_table('produk')
    op.drop_table('pengguna')
