"""Konfigurasi aplikasi. Nilai dibaca dari .env (python-dotenv); tanpa .env dipakai nilai bawaan.
`cfg` adalah dict tunggal yang dipakai seluruh aplikasi; `muat()` mengisinya ulang (dipakai `create_app` dan tes)."""
import os
from dotenv import load_dotenv

load_dotenv()

AKAR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
KATEGORI = ['Tanaman Hias Daun', 'Tanaman Berbunga', 'Sukulen & Kaktus', 'Tanaman Gantung', 'Pot & Media Tanam', 'Perawatan']


def _int(k, d): return int(os.getenv(k, d))
def _bool(k): return os.getenv(k, '0').strip() == '1'
def _teks(k, d=''): return os.getenv(k, d).strip()


def _dasar():
    return {
        # ---- Database (MariaDB) ----
        'DB_HOST': os.getenv('DB_HOST', '127.0.0.1'), 'DB_PORT': _int('DB_PORT', 3306), 'DB_USER': os.getenv('DB_USER', 'sawitku'),
        'DB_PASSWORD': os.getenv('DB_PASSWORD', ''), 'DB_NAME': os.getenv('DB_NAME', 'sawitku'),
        # ---- Web ----
        'CORS_ORIGINS': [o.strip() for o in os.getenv('CORS_ORIGINS', '').split(',') if o.strip()],
        # Kosong = URL gambar relatif (/media/...), cocok karena frontend & API satu origin.
        'PUBLIC_BASE_URL': os.getenv('PUBLIC_BASE_URL', '').rstrip('/'),
        'FRONTEND_DIR': os.path.abspath(os.getenv('FRONTEND_DIR', os.path.join(AKAR, 'frontend'))),
        'UPLOAD_DIR': os.path.abspath(os.getenv('UPLOAD_DIR', os.path.join(AKAR, 'uploads'))),
        'MAKS_BODY_MB': 6,
        # Jumlah proxy tepercaya di depan aplikasi (mis. 1 untuk Nginx) agar IP klien benar. 0 = langsung tanpa proxy.
        'PROXY_HOPS': _int('PROXY_HOPS', 0),
        'DEBUG': _bool('DEBUG'),
        # ---- Sesi & JWT ----
        # Kosong = dibuat otomatis lalu disimpan di berkas .jwt_secret (lihat security.rahasia_jwt).
        'JWT_SECRET': _teks('JWT_SECRET'),
        'SESI_MENIT': _int('SESI_MENIT', 20),            # masa berlaku token; diperpanjang selama pengguna aktif
        'MAKS_GAGAL': _int('MAKS_GAGAL', 5), 'BLOKIR_MENIT': _int('BLOKIR_MENIT', 5),
        # ---- Pesanan ----
        'BATAS_BAYAR_JAM': _int('BATAS_BAYAR_JAM', 24),
        'AUTO_TERIMA_JAM': _int('AUTO_TERIMA_JAM', 24),   # pesanan 'dikirim' yang sudah ditandai tiba otomatis selesai setelah ini
        'MAKS_MB': _int('MAKS_MB', 2),
        'MAKS_PESANAN_TERTUNDA': _int('MAKS_PESANAN_TERTUNDA', 5),   # pesanan 'menunggu_bayar' per pengguna (cegah penimbunan stok)
        'SWEEP_INTERVAL_MS': 10_000,
        # ---- Pembatas laju & chat ----
        'LAJU_DAFTAR': _int('LAJU_DAFTAR', 10), 'LAJU_KONTAK': _int('LAJU_KONTAK', 5),   # per IP per 10 menit
        'LAJU_CHAT': _int('LAJU_CHAT', 20), 'CHAT_MAKS_BERUNTUN': _int('CHAT_MAKS_BERUNTUN', 30),
        'LAMBAT_MS': _int('LAMBAT_MS', 300),             # request lebih lama dari ini dicatat sebagai LAMBAT di log
        # ---- OTP email ----
        'OTP_MENIT': _int('OTP_MENIT', 10), 'OTP_MAKS_SALAH': _int('OTP_MAKS_SALAH', 5), 'OTP_JEDA_DETIK': _int('OTP_JEDA_DETIK', 60),
        'OTP_MAKS_KIRIM': _int('OTP_MAKS_KIRIM', 5), 'LAJU_OTP': _int('LAJU_OTP', 30),
        # Tanpa SMTP_HOST, OTP ditolak (503) kecuali OTP_CETAK_KODE=1 (khusus pengembangan lokal: kode dicetak di terminal).
        'OTP_CETAK_KODE': _bool('OTP_CETAK_KODE'),
        'SMTP_HOST': _teks('SMTP_HOST'), 'SMTP_PORT': _int('SMTP_PORT', 587), 'SMTP_USER': _teks('SMTP_USER'),
        'SMTP_PASSWORD': os.getenv('SMTP_PASSWORD', ''), 'SMTP_FROM': _teks('SMTP_FROM') or _teks('SMTP_USER'),
        'SMTP_MODE': _teks('SMTP_MODE', 'starttls').lower(),     # starttls (587) | ssl (465) | none
        # ---- Midtrans (Core API: QRIS + Virtual Account) ----
        'MIDTRANS_SERVER_KEY': _teks('MIDTRANS_SERVER_KEY'),
        'MIDTRANS_PRODUKSI': _bool('MIDTRANS_PRODUKSI'),          # 0 = sandbox, 1 = produksi
    }


cfg = _dasar()


def muat(overrides=None):
    """Isi ulang `cfg` dari .env lalu timpa dengan `overrides`. Objek `cfg` yang sama dipertahankan (dict diubah di tempat)."""
    cfg.clear(); cfg.update(_dasar())
    if overrides: cfg.update(overrides)
    return cfg
