"""Validasi & penyimpanan gambar. Semua gambar digambar ulang lewat Pillow: metadata dan muatan tersembunyi terbuang."""
import base64, io, os, re, secrets
from flask import current_app
from PIL import Image, ImageOps
from .errors import ApiError
from .db import get_db
from .security import now_ms

_HEADER = {'data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64'}
MEDIA_RE = re.compile(r'^/media/(produk|bukti|foto)/[0-9a-f]{32}\.jpg$')
MAKS_PIKSEL = 25_000_000
Image.MAX_IMAGE_PIXELS = MAKS_PIKSEL  # tolak "decompression bomb"
# URL https eksternal: tanpa kutip, kurung sudut, backtick, atau backslash (mencegah injeksi atribut HTML)
URL_HTTPS_RE = re.compile(r'^https://[^\s"\'<>`\\]{4,480}$')


def _magic_ok(b):
    return b[:3] == b'\xff\xd8\xff' or b[:8] == b'\x89PNG\r\n\x1a\n' or (b[:4] == b'RIFF' and b[8:12] == b'WEBP')


def simpan_data_url(data_url, folder, sisi=1200):
    """Simpan data-URL gambar -> '/media/<folder>/<acak>.jpg' (path relatif yang disimpan di DB)."""
    if not isinstance(data_url, str) or ',' not in data_url:
        raise ApiError('Gambar tidak valid.')
    head, _, b64 = data_url.partition(',')
    if head.lower() not in _HEADER:
        raise ApiError('Hanya file JPG, PNG, atau WEBP.')
    maks = current_app.config['MAKS_MB'] * 1048576
    if len(b64) > maks * 4 // 3 + 8:
        raise ApiError(f"Ukuran maksimal {current_app.config['MAKS_MB']} MB.")
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise ApiError('Gambar tidak valid.')
    if len(raw) > maks:
        raise ApiError(f"Ukuran maksimal {current_app.config['MAKS_MB']} MB.")
    if not _magic_ok(raw):
        raise ApiError('Isi file bukan gambar yang valid.')
    try:
        im = Image.open(io.BytesIO(raw))
        if im.width * im.height > MAKS_PIKSEL:      # cek dimensi sebelum decode penuh (Pillow hanya memperingatkan di batas ini)
            raise ApiError('Dimensi gambar terlalu besar.')
        im.load()
        im = ImageOps.exif_transpose(im)             # hormati orientasi EXIF (foto HP) sebelum metadata dibuang
    except ApiError:
        raise
    except Exception:                                # Pillow bisa melempar OSError/ValueError/SyntaxError/DecompressionBombError
        raise ApiError('Isi file bukan gambar yang valid.')
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA'); bg = Image.new('RGB', im.size, 'white'); bg.paste(im, mask=im.split()[3]); im = bg
    else:
        im = im.convert('RGB')
    im.thumbnail((sisi, sisi))
    nama = secrets.token_hex(16) + '.jpg'
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=85, optimize=True)
    # Disimpan di database (bukan disk): tetap ada walau server di-restart/redeploy atau berjalan lebih dari satu instance.
    get_db().run('INSERT INTO media (folder,nama,data,dibuat) VALUES (%s,%s,%s,%s)', (folder, nama, buf.getvalue(), now_ms()))
    return f'/media/{folder}/{nama}'


def baca_media(folder, nama):
    """Isi gambar (bytes) dari database; berkas lama di disk (sebelum pindah ke database) tetap terbaca."""
    r = get_db().one('SELECT data FROM media WHERE folder=%s AND nama=%s', (folder, nama))
    if r: return bytes(r['data'])
    p = os.path.join(current_app.config['UPLOAD_DIR'], folder, nama)
    if os.path.isfile(p):
        with open(p, 'rb') as f: return f.read()
    return None


def media_dipakai(db, path):
    """True bila path masih dirujuk tabel lain (salinan gambar di riwayat pesanan, foto, bukti)."""
    for tabel, kolom in (('produk', 'gambar'), ('pesanan_item', 'gambar'), ('pengguna', 'foto'), ('pesanan', 'bukti')):
        if db.one(f'SELECT 1 AS x FROM {tabel} WHERE {kolom}=%s LIMIT 1', (path,)): return True
    return False


def hapus_media(path, db=None):
    """Hapus gambar unggahan. Bila `db` diberikan, gambar yang masih dirujuk (mis. riwayat pesanan) dibiarkan."""
    if isinstance(path, str) and MEDIA_RE.match(path) and not (db is not None and media_dipakai(db, path)):
        folder, nama = path[len('/media/'):].split('/')
        (db or get_db()).run('DELETE FROM media WHERE folder=%s AND nama=%s', (folder, nama))
        try: os.remove(os.path.join(current_app.config['UPLOAD_DIR'], folder, nama))     # sisa berkas lama di disk (bila ada)
        except OSError: pass


def url_keluar(v):
    """Path media relatif -> URL absolut; URL https eksternal dibiarkan."""
    if v and MEDIA_RE.match(v):
        return current_app.config['PUBLIC_BASE_URL'] + v
    return v


def resolve_gambar(nilai, folder, saat_ini=None, boleh_url=True):
    """Untuk foto produk/profil: terima data-URL (disimpan), media milik kita, atau URL https.
    Path media HANYA diterima bila sama dengan nilai yang sedang tersimpan (`saat_ini`). Tanpa aturan ini pengguna
    bisa menunjuk berkas milik orang lain (foto produk, bukti bayar) lalu memicu penghapusannya lewat hapus_media()."""
    if not isinstance(nilai, str) or not nilai:
        raise ApiError('Gambar wajib diisi.')
    if nilai.startswith('data:'):
        return simpan_data_url(nilai, folder)
    base = current_app.config['PUBLIC_BASE_URL']
    rel = nilai[len(base):] if base and nilai.startswith(base + '/media/') else nilai
    if MEDIA_RE.match(rel):
        if saat_ini and rel == saat_ini and rel.startswith(f'/media/{folder}/'):
            return rel
        raise ApiError('Gambar tidak valid (unggah ulang gambarnya).')
    if boleh_url and URL_HTTPS_RE.match(nilai):
        return nilai
    raise ApiError('Gambar tidak valid (gunakan URL https atau unggah gambar).' if boleh_url else 'Gambar tidak valid (unggah file JPG, PNG, atau WEBP).')
