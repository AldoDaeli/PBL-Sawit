"""Jejak audit: siapa mengerjakan apa, kapan, dari mana. Mencakup login/logout, semua aksi admin (produk, akun, pesanan, pembayaran, chat,
ulasan), semua aksi customer (favorit, keranjang, profil, email, pesanan, bayar, terima, ulasan, chat) dan aksi tamu (daftar, lupa password,
formulir kontak), serta kejadian otomatis sistem (webhook Midtrans, pembatalan/penyelesaian otomatis pesanan).

Tiap baris: waktu, pelaku (user_id, username, peran: admin | customer | tamu | sistem), aksi (`kategori.kejadian`, mis. `produk.ubah`),
target (mis. `produk#12`, `pesanan#7`), detail (JSON: apa yang berubah), IP, dan perangkat (User-Agent).

Disimpan di dua tempat:
  1. tabel `log_audit` (admin membacanya lewat GET /api/admin/log; dihapus otomatis setelah LOG_HARI hari);
  2. berkas `logs/aktivitas.log` (berputar otomatis 1 MB x 5), berguna untuk dibaca langsung di server.

Aturan privasi: password, token, kode OTP, dan isi gambar TIDAK pernah dicatat. Teks panjang (ulasan, pesan) dipotong; isi chat customer
tidak dicatat (hanya panjangnya), sedangkan balasan admin dicatat potongan awalnya agar tindakan admin bisa dipertanggungjawabkan.
Pencatatan tidak boleh menggagalkan aksi aslinya: galat apa pun hanya jadi peringatan.
Semua endpoint yang mengubah data (POST/PUT/DELETE) tetap tercatat walau belum diberi pencatat khusus: `routes.transaksi` menambahkan
baris umum `lain.<endpoint>` sebagai jaring pengaman."""
import json, logging, os
from logging.handlers import RotatingFileHandler

from flask import has_request_context, request

from .config import cfg, AKAR

log = logging.getLogger('sawitku')
berkas = logging.getLogger('sawitku.aktivitas')
berkas.propagate = False                      # hanya ke berkas, agar konsol tidak ganda dengan log 'sawitku'
RAHASIA = {'password', 'password_lama', 'password_baru', 'pw', 'token', 'kode', 'otp', 'hash', 'bukti', 'secret', 'data_url'}


def siapkan():
    """Pasang penulis berkas log (sekali). LOG_DIR kosong atau mode TESTING = tanpa berkas."""
    folder = (cfg.get('LOG_DIR') or '').strip()
    if cfg.get('TESTING') or not folder: return
    if not os.path.isabs(folder): folder = os.path.join(AKAR, folder)
    jalur = os.path.join(folder, 'aktivitas.log')
    if any(getattr(h, 'baseFilename', None) == jalur for h in berkas.handlers): return
    try:
        os.makedirs(folder, exist_ok=True)
        h = RotatingFileHandler(jalur, maxBytes=1_000_000, backupCount=5, encoding='utf-8')
        h.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        berkas.addHandler(h); berkas.setLevel(logging.INFO)
    except OSError:
        log.warning('Folder log %s tidak bisa ditulis: log aktivitas hanya masuk ke database.', folder)


def ringkas(teks, n=100):
    """Potongan awal teks untuk detail log."""
    t = ' '.join(str(teks or '').split())
    return t if len(t) <= n else t[:n - 1] + '…'


def _bersih(v, dalam=0):
    """Buang kolom rahasia, potong teks panjang, batasi kedalaman dan jumlah item."""
    if isinstance(v, dict):
        return {str(k)[:40]: _bersih(x, dalam + 1) for k, x in list(v.items())[:30] if str(k).lower() not in RAHASIA} if dalam < 4 else '…'
    if isinstance(v, (list, tuple)): return [_bersih(x, dalam + 1) for x in v[:20]] if dalam < 4 else '…'
    if isinstance(v, str): return v if len(v) <= 150 else v[:149] + '…'
    return v


def catat(db, aksi, u=None, target='', detail=None, peran=None):
    """Catat satu kejadian. `u` = baris pengguna pelaku (None = tamu, atau sistem bila peran='sistem').
    `peran` menimpa peran bawaan. Kejadian peran 'sistem' tidak menandai request sebagai "sudah tercatat" (lihat catat_umum)."""
    from .security import now_ms, ip_klien
    from .db import konteks
    try:
        peran = peran or (u['peran'] if u else 'tamu')
        if peran != 'sistem': konteks().tercatat = True
        ip = ip_klien(); ua = (request.headers.get('User-Agent') or '')[:200] if has_request_context() else ''     # sapu terjadwal berjalan tanpa request
        uid, nama = (u['id'], u['username']) if u else (None, '')
        d = json.dumps(_bersih(detail), ensure_ascii=False, default=str) if detail else ''
        if len(d) > 2000: d = json.dumps({'terpotong': True})
        db.run('INSERT INTO log_audit (user_id,username,peran,aksi,kategori,target,detail,ip,perangkat,waktu) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
               (uid, nama, peran, aksi, aksi.split('.')[0], str(target)[:80], d, ip, ua, now_ms()))
        berkas.info('%s peran=%s user_id=%s username=%s target=%s ip=%s detail=%s perangkat="%s"',
                    aksi, peran, uid or '-', nama or '-', target or '-', ip, d or '-', ua)
    except Exception:
        log.warning('Gagal mencatat log aktivitas (%s)', aksi, exc_info=True)


def catat_umum(db):
    """Jaring pengaman: request yang mengubah data tetapi belum punya pencatat khusus tetap meninggalkan jejak."""
    from .db import konteks
    k = konteks(); rute = request.url_rule.rule if request.url_rule else request.path
    catat(db, 'lain.' + (request.endpoint or '?').split('.')[-1], k.pengguna, request.path, {'metode': request.method, 'rute': rute})
