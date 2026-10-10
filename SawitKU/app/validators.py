import re
from .errors import ApiError

_USERNAME = re.compile(r'^[a-zA-Z0-9_]{4,20}$')
_EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$')

def username_ok(u): return isinstance(u, str) and bool(_USERNAME.match(u))
def email_ok(e): return isinstance(e, str) and bool(_EMAIL.match(e)) and len(e) <= 100
def password_ok(p): return isinstance(p, str) and 8 <= len(p) <= 64 and bool(re.search('[a-zA-Z]', p)) and bool(re.search(r'\d', p))

def to_int(v, pesan):
    """Ubah ke bilangan bulat; tolak bool, NaN, dan teks non-angka."""
    if isinstance(v, bool): raise ApiError(pesan)
    try: f = float(v)
    except (TypeError, ValueError): raise ApiError(pesan)
    if f != f or f in (float('inf'), float('-inf')): raise ApiError(pesan)
    return int(f)


# ---- Alamat pengiriman ----
_TELEPON = re.compile(r'^(?:\+62|62|0)8\d{7,12}$')     # nomor seluler Indonesia
_KODE_POS = re.compile(r'^\d{5}$')
_KONTROL = re.compile(r'[\x00-\x1f\x7f]')

def _teks(v, nama, lo, hi):
    t = _KONTROL.sub(' ', str(v or '')).strip()
    t = re.sub(r'\s{2,}', ' ', t)
    if not lo <= len(t) <= hi: raise ApiError(f'{nama} {lo}–{hi} karakter.')
    return t

def baca_alamat(b, perlu_penerima=True):
    """Validasi & normalisasi alamat dari body JSON. Kembalikan dict kolom DB; lempar ApiError bila tidak valid."""
    telepon = re.sub(r'[\s\-.()]', '', str(b.get('telepon') or ''))
    if not _TELEPON.match(telepon): raise ApiError('Nomor HP tidak valid (contoh: 081234567890).')
    kode_pos = str(b.get('kodePos') or '').strip()
    if not _KODE_POS.match(kode_pos): raise ApiError('Kode pos harus 5 angka.')
    d = dict(telepon=telepon, alamat=_teks(b.get('alamat'), 'Alamat', 10, 200),
             kota=_teks(b.get('kota'), 'Kota/Kabupaten', 2, 60), kode_pos=kode_pos)
    if perlu_penerima: d['penerima'] = _teks(b.get('penerima'), 'Nama penerima', 3, 80)
    return d


# Karakter kontrol + karakter arah teks (bidi override) dibuang: dipakai untuk menyamarkan/memalsukan tampilan pesan.
_KONTROL = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]')

def bersihkan_chat(v, maks=1000):
    """Normalkan isi chat: harus teks, tanpa karakter kontrol, maks 2 baris kosong berurutan, 1..maks karakter."""
    if not isinstance(v, str): raise ApiError('Pesan tidak valid.')
    s = _KONTROL.sub('', v.replace('\r\n', '\n').replace('\r', '\n'))
    s = re.sub(r'\n{3,}', '\n\n', s).strip()
    if not s: raise ApiError('Pesan tidak boleh kosong.')
    if len(s) > maks: raise ApiError(f'Pesan maksimal {maks} karakter.')
    return s
