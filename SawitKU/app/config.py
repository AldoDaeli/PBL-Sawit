import os
from dotenv import load_dotenv

load_dotenv()

def _int(k, d): return int(os.getenv(k, d))

KATEGORI = ['Tanaman Hias Daun', 'Tanaman Berbunga', 'Sukulen & Kaktus', 'Tanaman Gantung', 'Pot & Media Tanam', 'Perawatan']

class Config:
    DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
    DB_PORT = _int('DB_PORT', 3306)
    DB_USER = os.getenv('DB_USER', 'sawitku')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME = os.getenv('DB_NAME', 'sawitku')
    CORS_ORIGINS = [o.strip() for o in os.getenv('CORS_ORIGINS', '').split(',') if o.strip()]
    # Kosong = URL gambar relatif (/media/...), cocok karena frontend & API satu origin. Isi hanya bila gambar harus diakses dari domain lain.
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    FRONTEND_DIR = os.path.abspath(os.getenv('FRONTEND_DIR', os.path.join(os.path.dirname(__file__), '..', 'frontend')))
    UPLOAD_DIR = os.path.abspath(os.getenv('UPLOAD_DIR', 'uploads'))
    # Sama dengan objek CFG di frontend
    SESI_MENIT = _int('SESI_MENIT', 20)
    MAKS_GAGAL = _int('MAKS_GAGAL', 5)
    BLOKIR_MENIT = _int('BLOKIR_MENIT', 5)
    BATAS_BAYAR_JAM = _int('BATAS_BAYAR_JAM', 24)
    MAKS_MB = _int('MAKS_MB', 2)
    # Jumlah proxy tepercaya di depan aplikasi (mis. 1 untuk Nginx) agar IP klien benar. 0 = langsung tanpa proxy.
    PROXY_HOPS = _int('PROXY_HOPS', 0)
    LAJU_DAFTAR = _int('LAJU_DAFTAR', 10)     # maks pendaftaran per IP per 10 menit
    LAJU_KONTAK = _int('LAJU_KONTAK', 5)      # maks pesan kontak per IP per 10 menit
    MAKS_PESANAN_TERTUNDA = _int('MAKS_PESANAN_TERTUNDA', 5)   # pesanan 'menunggu_bayar' per pengguna (cegah penimbunan stok)
    # Chat pelanggan <-> admin
    LAJU_CHAT = _int('LAJU_CHAT', 20)                    # maks pesan terkirim per pengguna per menit
    CHAT_MAKS_BERUNTUN = _int('CHAT_MAKS_BERUNTUN', 30)  # maks pesan pelanggan berturut-turut tanpa balasan admin
    LAMBAT_MS = _int('LAMBAT_MS', 300)                   # request lebih lama dari ini dicatat sebagai LAMBAT di log
    # OTP pendaftaran (kode 6 angka dikirim ke email)
    OTP_MENIT = _int('OTP_MENIT', 10)             # masa berlaku kode
    OTP_MAKS_SALAH = _int('OTP_MAKS_SALAH', 5)    # salah memasukkan kode sebelum harus minta kode baru
    OTP_JEDA_DETIK = _int('OTP_JEDA_DETIK', 60)   # jarak minimal antar pengiriman ke email yang sama
    OTP_MAKS_KIRIM = _int('OTP_MAKS_KIRIM', 5)    # maks pengiriman kode per pendaftaran (termasuk kirim ulang)
    LAJU_OTP = _int('LAJU_OTP', 30)               # maks verifikasi/kirim ulang per IP per 10 menit
    # SMTP untuk mengirim email OTP. Tanpa SMTP_HOST, OTP ditolak (503) kecuali OTP_CETAK_KODE=1 (khusus pengembangan lokal:
    # kode dicetak di terminal Flask dan email TIDAK dikirim). Jangan aktifkan OTP_CETAK_KODE di produksi.
    OTP_CETAK_KODE = os.getenv('OTP_CETAK_KODE', '0').strip() == '1'
    SMTP_HOST = os.getenv('SMTP_HOST', '').strip()
    SMTP_PORT = _int('SMTP_PORT', 587)
    SMTP_USER = os.getenv('SMTP_USER', '').strip()
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_FROM = os.getenv('SMTP_FROM', '').strip() or os.getenv('SMTP_USER', '').strip()
    SMTP_MODE = os.getenv('SMTP_MODE', 'starttls').strip().lower()   # starttls (587) | ssl (465) | none
    # Midtrans (virtual account). Kosong = tombol "Bayar via Virtual Account" dinonaktifkan; QRIS manual tetap jalan.
    MIDTRANS_SERVER_KEY = os.getenv('MIDTRANS_SERVER_KEY', '').strip()
    MIDTRANS_PRODUKSI = os.getenv('MIDTRANS_PRODUKSI', '0').strip() == '1'      # 0 = sandbox, 1 = produksi
    SWEEP_INTERVAL_MS = 10_000
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024
