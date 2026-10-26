"""Bentuk body request. Flask tidak memvalidasi body otomatis, jadi `badan()` membaca JSON, memastikannya objek, lalu membungkusnya
dalam kelas `Isi` agar kolom bisa diakses sebagai atribut (`b.username`). Kolom yang tidak dikirim bernilai None (atau nilai bawaan),
kolom tambahan dari klien diterima lalu diabaikan. Validasi isi dan pesan galat berbahasa Indonesia dikerjakan oleh
app/validators.py dan route, sehingga pesan ke pengguna tetap seragam."""
from flask import request

from .config import cfg
from .errors import ApiError

PESAN_BODY = 'Format data tidak valid.'


class Isi:
    kolom = ()          # kolom yang dikenal (dokumentasi; ikut muncul di data() dengan nilai None bila tidak dikirim)
    bawaan = {}         # nilai bawaan kolom tertentu

    def __init__(self, d=None): object.__setattr__(self, '_d', dict(d or {}))

    def __getattr__(self, nama):
        if nama.startswith('_'): raise AttributeError(nama)
        return self._d.get(nama, self.bawaan.get(nama))

    def data(self):
        """Isi body sebagai dict biasa (kolom tambahan ikut)."""
        return {**dict.fromkeys(self.kolom), **self.bawaan, **self._d}

    def ada(self, kunci):
        """Apakah klien mengirim kolom ini (walau nilainya kosong)."""
        return kunci in self._d


def badan(kelas=Isi, wajib=True):
    """Baca body JSON request sebagai `kelas`. Body kosong / bukan JSON / bukan objek -> 400 (bila `wajib`); body kosong atau `null` -> None bila tidak wajib."""
    mentah = request.get_data(cache=True)              # Content-Length melewati MAX_CONTENT_LENGTH -> 413 oleh Werkzeug
    batas = cfg['MAKS_BODY_MB'] * 1048576
    # Body chunked (tanpa Content-Length) dipotong DIAM-DIAM oleh Werkzeug tepat di batas, bukan ditolak: panjang >= batas berarti terpotong.
    if len(mentah) > batas or (request.content_length is None and len(mentah) >= (request.max_content_length or batas + 1)):
        raise ApiError('Ukuran data terlalu besar.', 413)
    mentah = mentah.strip()
    if not mentah or mentah == b'null':
        if wajib: raise ApiError(PESAN_BODY)
        return None
    d = request.get_json(force=True, silent=True)
    if not isinstance(d, dict): raise ApiError(PESAN_BODY)
    return kelas(d)


# ---- Akun ----
class MasukIn(Isi): kolom = ('username', 'password')
class DaftarIn(Isi): kolom = ('username', 'email', 'password')
class EmailIn(Isi): kolom = ('email',)
class KodeIn(Isi): kolom = ('email', 'kode')
class LupaResetIn(Isi): kolom = ('email', 'kode', 'password')
class KontakIn(Isi): kolom = ('nama', 'email', 'jenis', 'isi')
class ProfilIn(Isi): kolom = ('username', 'email', 'foto', 'telepon', 'alamat', 'kota', 'kodePos')
class EmailMintaIn(Isi): kolom = ('email', 'password')
class KodeSajaIn(Isi): kolom = ('kode',)

# ---- Belanja ----
class KeranjangIn(Isi): kolom = ('produkId', 'qty'); bawaan = {'qty': 1}
class QtyIn(Isi): kolom = ('qty',)
class CheckoutIn(Isi): kolom = ('penerima', 'telepon', 'alamat', 'kota', 'kodePos', 'simpan', 'metode')
class UlasanIn(Isi): kolom = ('produkId', 'rating', 'teks')
class TeksIn(Isi): kolom = ('teks',)

# ---- Pembayaran & pengiriman ----
class MetodeIn(Isi): kolom = ('metode',)
class BuktiIn(Isi): kolom = ('bukti',)
class TerimaIn(Isi): kolom = ('foto',)
class VerifikasiIn(Isi): kolom = ('setuju', 'alasan')
class KirimIn(Isi): kolom = ('kurir', 'resi')

# ---- Admin ----
class ProdukIn(Isi):
    kolom = ('nama', 'kategori', 'harga', 'stok', 'gambar', 'deskripsi', 'spek', 'spesifikasi', 'bestSeller')

# ---- Chat ----
class ChatIn(Isi): kolom = ('isi',)
