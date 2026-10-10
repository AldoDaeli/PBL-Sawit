-- Skema MariaDB 10.5+ untuk SawitKu. Waktu disimpan sebagai epoch milidetik (BIGINT),
-- sama dengan format yang dipakai frontend. Jalankan: flask --app wsgi init-db

CREATE TABLE IF NOT EXISTS pengguna (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(20) NOT NULL,
  email VARCHAR(100) NOT NULL,
  hash VARCHAR(255) NOT NULL,
  peran VARCHAR(10) NOT NULL DEFAULT 'customer' CHECK (peran IN ('admin','customer')),
  aktif TINYINT NOT NULL DEFAULT 1,
  foto VARCHAR(255) NULL,
  -- Alamat pengiriman utama (opsional; mengisi otomatis form checkout)
  telepon VARCHAR(20) NULL,
  alamat VARCHAR(255) NULL,
  kota VARCHAR(60) NULL,
  kode_pos VARCHAR(10) NULL,
  dibuat BIGINT NOT NULL,
  UNIQUE (username),
  UNIQUE (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS produk (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  nama VARCHAR(80) NOT NULL,
  kategori VARCHAR(40) NOT NULL,
  harga INT NOT NULL CHECK (harga >= 0),
  stok INT NOT NULL DEFAULT 0 CHECK (stok >= 0),
  terjual INT NOT NULL DEFAULT 0,
  rating DECIMAL(2,1) NOT NULL DEFAULT 4.5,
  best_seller TINYINT NOT NULL DEFAULT 0,
  gambar VARCHAR(500) NOT NULL,
  deskripsi VARCHAR(400) NOT NULL DEFAULT '',
  spesifikasi TEXT NOT NULL,
  dibuat BIGINT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX IF NOT EXISTS idx_produk_kategori ON produk (kategori);

CREATE TABLE IF NOT EXISTS keranjang (
  user_id INT NOT NULL,
  produk_id INT NOT NULL,
  qty INT NOT NULL CHECK (qty > 0),
  PRIMARY KEY (user_id, produk_id),
  FOREIGN KEY (user_id) REFERENCES pengguna (id) ON DELETE CASCADE,
  FOREIGN KEY (produk_id) REFERENCES produk (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS favorit (
  user_id INT NOT NULL,
  produk_id INT NOT NULL,
  PRIMARY KEY (user_id, produk_id),
  FOREIGN KEY (user_id) REFERENCES pengguna (id) ON DELETE CASCADE,
  FOREIGN KEY (produk_id) REFERENCES produk (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pesanan (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  total BIGINT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'menunggu_bayar'
    CHECK (status IN ('menunggu_bayar','menunggu_verifikasi','diproses','dikirim','selesai','dibatalkan')),
  bukti VARCHAR(255) NULL,
  alasan VARCHAR(255) NOT NULL DEFAULT '',
  -- Salinan alamat tujuan saat checkout (tidak berubah walau pembeli mengganti alamat profilnya)
  penerima VARCHAR(80) NOT NULL DEFAULT '',
  telepon VARCHAR(20) NOT NULL DEFAULT '',
  alamat VARCHAR(255) NOT NULL DEFAULT '',
  kota VARCHAR(60) NOT NULL DEFAULT '',
  kode_pos VARCHAR(10) NOT NULL DEFAULT '',
  dibuat BIGINT NOT NULL,
  batas_bayar BIGINT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES pengguna (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX IF NOT EXISTS idx_pesanan_user ON pesanan (user_id, dibuat);
CREATE INDEX IF NOT EXISTS idx_pesanan_status ON pesanan (status, batas_bayar);

-- Item pesanan menyimpan salinan nama/harga/gambar saat checkout; produk boleh dihapus tanpa merusak riwayat.
CREATE TABLE IF NOT EXISTS pesanan_item (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  pesanan_id INT NOT NULL,
  produk_id INT NULL,
  nama VARCHAR(80) NOT NULL,
  gambar VARCHAR(500) NOT NULL,
  harga INT NOT NULL,
  qty INT NOT NULL CHECK (qty > 0),
  FOREIGN KEY (pesanan_id) REFERENCES pesanan (id) ON DELETE CASCADE,
  FOREIGN KEY (produk_id) REFERENCES produk (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX IF NOT EXISTS idx_item_pesanan ON pesanan_item (pesanan_id);

CREATE TABLE IF NOT EXISTS ulasan (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  produk_id INT NOT NULL,
  user_id INT NOT NULL,
  rating TINYINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  teks VARCHAR(300) NOT NULL,
  balasan_teks VARCHAR(300) NULL,
  balasan_dibuat BIGINT NULL,
  dibuat BIGINT NOT NULL,
  UNIQUE (produk_id, user_id),
  FOREIGN KEY (produk_id) REFERENCES produk (id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES pengguna (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pesan_kontak (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  nama VARCHAR(100) NOT NULL,
  email VARCHAR(100) NOT NULL,
  jenis VARCHAR(20) NOT NULL,
  isi VARCHAR(500) NOT NULL,
  dibuat BIGINT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sesi login (token disimpan sebagai SHA-256, bukan token asli)
CREATE TABLE IF NOT EXISTS sesi (
  token_hash CHAR(64) NOT NULL PRIMARY KEY,
  user_id INT NOT NULL,
  kedaluwarsa BIGINT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES pengguna (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX IF NOT EXISTS idx_sesi_exp ON sesi (kedaluwarsa);

-- Pembatas percobaan login gagal per username
CREATE TABLE IF NOT EXISTS gagal_login (
  kunci VARCHAR(100) NOT NULL PRIMARY KEY,
  n INT NOT NULL DEFAULT 0,
  blokir_hingga BIGINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pendaftaran yang menunggu verifikasi OTP email. Akun baru dibuat di tabel pengguna hanya setelah kode benar.
-- Password sudah di-hash; kode OTP disimpan sebagai SHA-256 + garam (bukan kode asli).
CREATE TABLE IF NOT EXISTS otp_daftar (
  email VARCHAR(100) NOT NULL PRIMARY KEY,
  username VARCHAR(20) NOT NULL,
  hash VARCHAR(255) NOT NULL,
  kode_hash CHAR(64) NOT NULL,
  garam CHAR(32) NOT NULL,
  kedaluwarsa BIGINT NOT NULL,
  salah INT NOT NULL DEFAULT 0,
  kirim_n INT NOT NULL DEFAULT 1,
  kirim_terakhir BIGINT NOT NULL,
  dibuat BIGINT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Permintaan ganti email yang menunggu verifikasi OTP (email lama tetap berlaku sampai kode benar).
CREATE TABLE IF NOT EXISTS otp_email (
  user_id INT NOT NULL PRIMARY KEY,
  email VARCHAR(100) NOT NULL,
  kode_hash CHAR(64) NOT NULL,
  garam CHAR(32) NOT NULL,
  kedaluwarsa BIGINT NOT NULL,
  salah INT NOT NULL DEFAULT 0,
  kirim_n INT NOT NULL DEFAULT 1,
  kirim_terakhir BIGINT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES pengguna (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Chat pelanggan <-> admin: satu percakapan per pelanggan (user_id). dari = 'customer' | 'admin'.
-- dibaca = sudah dibaca pihak lawan (untuk tanda centang dan penghitung pesan belum dibaca).
CREATE TABLE IF NOT EXISTS chat_pesan (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  dari VARCHAR(8) NOT NULL,
  admin_id INT NULL,
  isi VARCHAR(1000) NOT NULL,
  dibuat BIGINT NOT NULL,
  dibaca TINYINT NOT NULL DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES pengguna (id) ON DELETE CASCADE,
  FOREIGN KEY (admin_id) REFERENCES pengguna (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_pesan (user_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_belum ON chat_pesan (dari, dibaca, user_id);
