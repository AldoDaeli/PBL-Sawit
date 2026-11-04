"""Model ORM (SQLAlchemy) untuk seluruh tabel SawitKu. Sumber kebenaran skema untuk migration (`flask db migrate`).
Nama tabel/kolom sama persis dengan schema.sql, jadi database lama tetap cocok. Waktu = epoch milidetik (BIGINT)."""
from sqlalchemy import CheckConstraint, Index, LargeBinary, Numeric, UniqueConstraint
from sqlalchemy.dialects import mysql
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

MYSQL_OPSI = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
BigInt = db.BigInteger
TinyInt = db.SmallInteger
LongBlob = LargeBinary().with_variant(mysql.LONGBLOB(), 'mysql', 'mariadb')


def _fk(tujuan, hapus='CASCADE'): return db.ForeignKey(tujuan, ondelete=hapus)


class Pengguna(db.Model):
    """Akun pengguna. peran: 'admin' | 'customer'. Password disimpan sebagai hash (scrypt + salt), tidak pernah teks asli."""
    __tablename__ = 'pengguna'
    __table_args__ = (CheckConstraint("peran IN ('admin','customer')", name='ck_pengguna_peran'), MYSQL_OPSI)

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    hash = db.Column(db.String(255), nullable=False)
    peran = db.Column(db.String(10), nullable=False, default='customer', server_default='customer')
    aktif = db.Column(TinyInt, nullable=False, default=1, server_default='1')
    foto = db.Column(db.String(255))
    telepon = db.Column(db.String(20))
    alamat = db.Column(db.String(255))
    kota = db.Column(db.String(60))
    kode_pos = db.Column(db.String(10))
    dibuat = db.Column(BigInt, nullable=False)

    def set_password(self, pw): self.hash = generate_password_hash(pw)
    def cek_password(self, pw): return check_password_hash(self.hash, pw)
    @property
    def admin(self): return self.peran == 'admin'

    def __repr__(self): return f'<Pengguna {self.username} ({self.peran})>'


class Produk(db.Model):
    __tablename__ = 'produk'
    __table_args__ = (CheckConstraint('harga >= 0', name='ck_produk_harga'), CheckConstraint('stok >= 0', name='ck_produk_stok'),
                      Index('idx_produk_kategori', 'kategori'), MYSQL_OPSI)

    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(80), nullable=False)
    kategori = db.Column(db.String(40), nullable=False)
    harga = db.Column(db.Integer, nullable=False)
    stok = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    terjual = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    rating = db.Column(Numeric(2, 1, asdecimal=False), nullable=False, default=0, server_default='0')   # rata-rata ulasan, 0 = belum ada
    best_seller = db.Column(TinyInt, nullable=False, default=0, server_default='0')
    gambar = db.Column(db.String(500), nullable=False)
    deskripsi = db.Column(db.String(400), nullable=False, default='', server_default='')
    spesifikasi = db.Column(db.Text, nullable=False)        # JSON teks {"Nama": "nilai"}
    dibuat = db.Column(BigInt, nullable=False)

    KOLOM = ('id', 'nama', 'kategori', 'harga', 'stok', 'terjual', 'rating', 'best_seller', 'gambar', 'deskripsi', 'spesifikasi', 'dibuat')

    def sebagai_baris(self, n_ulasan=0):
        """Dict dengan nama kolom DB; bentuk yang dibaca serializers.produk_out."""
        d = {k: getattr(self, k) for k in self.KOLOM}
        d['n_ulasan'] = n_ulasan
        return d

    def __repr__(self): return f'<Produk {self.id} {self.nama}>'


class Keranjang(db.Model):
    __tablename__ = 'keranjang'
    __table_args__ = (CheckConstraint('qty > 0', name='ck_keranjang_qty'), MYSQL_OPSI)
    user_id = db.Column(db.Integer, _fk('pengguna.id'), primary_key=True)
    produk_id = db.Column(db.Integer, _fk('produk.id'), primary_key=True)
    qty = db.Column(db.Integer, nullable=False)


class Favorit(db.Model):
    __tablename__ = 'favorit'
    __table_args__ = (MYSQL_OPSI,)
    user_id = db.Column(db.Integer, _fk('pengguna.id'), primary_key=True)
    produk_id = db.Column(db.Integer, _fk('produk.id'), primary_key=True)


class Pesanan(db.Model):
    __tablename__ = 'pesanan'
    __table_args__ = (
        CheckConstraint("status IN ('menunggu_bayar','menunggu_verifikasi','diproses','dikirim','selesai','dibatalkan')", name='ck_pesanan_status'),
        Index('idx_pesanan_user', 'user_id', 'dibuat'), Index('idx_pesanan_status', 'status', 'batas_bayar'), MYSQL_OPSI)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, _fk('pengguna.id'), nullable=False)
    total = db.Column(BigInt, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='menunggu_bayar', server_default='menunggu_bayar')
    bukti = db.Column(db.String(255))
    alasan = db.Column(db.String(255), nullable=False, default='', server_default='')
    penerima = db.Column(db.String(80), nullable=False, default='', server_default='')
    telepon = db.Column(db.String(20), nullable=False, default='', server_default='')
    alamat = db.Column(db.String(255), nullable=False, default='', server_default='')
    kota = db.Column(db.String(60), nullable=False, default='', server_default='')
    kode_pos = db.Column(db.String(10), nullable=False, default='', server_default='')
    dibuat = db.Column(BigInt, nullable=False)
    batas_bayar = db.Column(BigInt, nullable=False)
    ditolak = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    kurir = db.Column(db.String(30))
    resi = db.Column(db.String(40))
    t_bayar = db.Column(BigInt)
    t_proses = db.Column(BigInt)
    t_kirim = db.Column(BigInt)
    t_selesai = db.Column(BigInt)
    metode = db.Column(db.String(12))
    midtrans_id = db.Column(db.String(50))
    midtrans_status = db.Column(db.String(20))
    midtrans_data = db.Column(db.Text)
    t_sampai = db.Column(BigInt)
    foto_terima = db.Column(db.String(255))
    otomatis = db.Column(TinyInt, nullable=False, default=0, server_default='0')


class PesananItem(db.Model):
    """Salinan nama/harga/gambar saat checkout; produk boleh dihapus tanpa merusak riwayat (produk_id jadi NULL)."""
    __tablename__ = 'pesanan_item'
    __table_args__ = (CheckConstraint('qty > 0', name='ck_pesanan_item_qty'), Index('idx_item_pesanan', 'pesanan_id'), MYSQL_OPSI)
    id = db.Column(db.Integer, primary_key=True)
    pesanan_id = db.Column(db.Integer, _fk('pesanan.id'), nullable=False)
    produk_id = db.Column(db.Integer, _fk('produk.id', 'SET NULL'))
    nama = db.Column(db.String(80), nullable=False)
    gambar = db.Column(db.String(500), nullable=False)
    harga = db.Column(db.Integer, nullable=False)
    qty = db.Column(db.Integer, nullable=False)


class Ulasan(db.Model):
    __tablename__ = 'ulasan'
    __table_args__ = (CheckConstraint('rating BETWEEN 1 AND 5', name='ck_ulasan_rating'),
                      UniqueConstraint('produk_id', 'user_id', name='uq_ulasan_produk_id_user_id'), MYSQL_OPSI)
    id = db.Column(db.Integer, primary_key=True)
    produk_id = db.Column(db.Integer, _fk('produk.id'), nullable=False)
    user_id = db.Column(db.Integer, _fk('pengguna.id'), nullable=False)
    rating = db.Column(TinyInt, nullable=False)
    teks = db.Column(db.String(300), nullable=False)
    balasan_teks = db.Column(db.String(300))
    balasan_dibuat = db.Column(BigInt)
    dibuat = db.Column(BigInt, nullable=False)


class UlasanBalas(db.Model):
    __tablename__ = 'ulasan_balas'
    __table_args__ = (Index('idx_ulasan_balas', 'ulasan_id', 'id'), MYSQL_OPSI)
    id = db.Column(db.Integer, primary_key=True)
    ulasan_id = db.Column(db.Integer, _fk('ulasan.id'), nullable=False)
    dari = db.Column(db.String(8), nullable=False)
    user_id = db.Column(db.Integer, _fk('pengguna.id', 'SET NULL'))
    teks = db.Column(db.String(300), nullable=False)
    dibuat = db.Column(BigInt, nullable=False)


class PesanKontak(db.Model):
    __tablename__ = 'pesan_kontak'
    __table_args__ = (MYSQL_OPSI,)
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    jenis = db.Column(db.String(20), nullable=False)
    isi = db.Column(db.String(500), nullable=False)
    dibuat = db.Column(BigInt, nullable=False)


class LogAudit(db.Model):
    """Jejak audit; sengaja tanpa foreign key agar riwayat tetap ada walau akun/produk dihapus."""
    __tablename__ = 'log_audit'
    __table_args__ = (Index('idx_audit_waktu', 'waktu'), Index('idx_audit_user', 'user_id', 'waktu'),
                      Index('idx_audit_kategori', 'kategori', 'waktu'), MYSQL_OPSI)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    username = db.Column(db.String(30), nullable=False, default='', server_default='')
    peran = db.Column(db.String(10), nullable=False, default='', server_default='')
    aksi = db.Column(db.String(40), nullable=False)
    kategori = db.Column(db.String(20), nullable=False, default='', server_default='')
    target = db.Column(db.String(80), nullable=False, default='', server_default='')
    detail = db.Column(db.Text)
    ip = db.Column(db.String(60), nullable=False, default='', server_default='')
    perangkat = db.Column(db.String(200), nullable=False, default='', server_default='')
    waktu = db.Column(BigInt, nullable=False)


class Sesi(db.Model):
    """Sesi login; token disimpan sebagai SHA-256, bukan token asli."""
    __tablename__ = 'sesi'
    __table_args__ = (Index('idx_sesi_exp', 'kedaluwarsa'), MYSQL_OPSI)
    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, _fk('pengguna.id'), nullable=False)
    kedaluwarsa = db.Column(BigInt, nullable=False)


class GagalLogin(db.Model):
    __tablename__ = 'gagal_login'
    __table_args__ = (MYSQL_OPSI,)
    kunci = db.Column(db.String(100), primary_key=True)
    n = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    blokir_hingga = db.Column(BigInt, nullable=False, default=0, server_default='0')


class OtpDaftar(db.Model):
    __tablename__ = 'otp_daftar'
    __table_args__ = (MYSQL_OPSI,)
    email = db.Column(db.String(100), primary_key=True)
    username = db.Column(db.String(20), nullable=False)
    hash = db.Column(db.String(255), nullable=False)
    kode_hash = db.Column(db.String(64), nullable=False)
    garam = db.Column(db.String(32), nullable=False)
    kedaluwarsa = db.Column(BigInt, nullable=False)
    salah = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    kirim_n = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    kirim_terakhir = db.Column(BigInt, nullable=False)
    dibuat = db.Column(BigInt, nullable=False)


class OtpEmail(db.Model):
    __tablename__ = 'otp_email'
    __table_args__ = (MYSQL_OPSI,)
    user_id = db.Column(db.Integer, _fk('pengguna.id'), primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    kode_hash = db.Column(db.String(64), nullable=False)
    garam = db.Column(db.String(32), nullable=False)
    kedaluwarsa = db.Column(BigInt, nullable=False)
    salah = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    kirim_n = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    kirim_terakhir = db.Column(BigInt, nullable=False)


class OtpReset(db.Model):
    __tablename__ = 'otp_reset'
    __table_args__ = (MYSQL_OPSI,)
    email = db.Column(db.String(100), primary_key=True)
    kode_hash = db.Column(db.String(64), nullable=False)
    garam = db.Column(db.String(32), nullable=False)
    kedaluwarsa = db.Column(BigInt, nullable=False)
    salah = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    kirim_n = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    kirim_terakhir = db.Column(BigInt, nullable=False)


class ChatPesan(db.Model):
    __tablename__ = 'chat_pesan'
    __table_args__ = (Index('idx_chat_user', 'user_id', 'id'), Index('idx_chat_belum', 'dari', 'dibaca', 'user_id'), MYSQL_OPSI)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, _fk('pengguna.id'), nullable=False)
    dari = db.Column(db.String(8), nullable=False)
    admin_id = db.Column(db.Integer, _fk('pengguna.id', 'SET NULL'))
    isi = db.Column(db.String(1000), nullable=False)
    dibuat = db.Column(BigInt, nullable=False)
    dibaca = db.Column(TinyInt, nullable=False, default=0, server_default='0')


class Media(db.Model):
    """Gambar unggahan (foto produk, bukti bayar, foto profil) disimpan di database."""
    __tablename__ = 'media'
    __table_args__ = (MYSQL_OPSI,)
    folder = db.Column(db.String(10), primary_key=True)
    nama = db.Column(db.String(40), primary_key=True)
    data = db.Column(LongBlob, nullable=False)
    dibuat = db.Column(BigInt, nullable=False)
