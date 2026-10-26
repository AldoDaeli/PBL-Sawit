"""Uji alur bisnis end-to-end. Memakai SQLite dengan schema.sql yang sama (tanpa opsi khusus MariaDB).
Jalankan: python -m unittest discover -s tests -v"""
import base64, gzip as _gzip, io, json as _json, os, re, shutil, sqlite3, tempfile, unittest
from PIL import Image

os.environ.setdefault('DB_PASSWORD', 'x')
from app import create_app, db as dbmod, seed, otp, config, midtrans
from app.db import Db

ROOT = os.path.dirname(os.path.dirname(__file__))


# ---- klien tes: pembungkus tipis di atas test_client Flask dengan antarmuka ala `requests` (status_code, headers, content, text, json()) ----
class _Balasan:
    def __init__(self, r): self.r, self.status_code, self.headers = r, r.status_code, r.headers

    @property
    def content(self):          # isi sudah didekompresi bila server memakai gzip (seperti klien HTTP biasa)
        d = self.r.get_data()
        return _gzip.decompress(d) if self.r.headers.get('Content-Encoding') == 'gzip' else d

    @property
    def text(self): return self.content.decode('utf-8')

    def json(self): return _json.loads(self.content)


class TestClient:
    __test__ = False            # bukan kelas tes bagi unittest/pytest

    def __init__(self, app, base_url='http://localhost', **_): self.c, self.base = app.test_client(), base_url

    def request(self, metode, url, json=None, data=None, headers=None, **_):
        h = {'Accept-Encoding': 'gzip, deflate', **(headers or {})}
        kw = {} if json is None else {'json': json}
        if data is not None: kw['data'] = data
        return _Balasan(self.c.open(url, method=metode, headers=h, base_url=self.base, **kw))

    def get(self, url, **kw): return self.request('GET', url, **kw)
    def post(self, url, **kw): return self.request('POST', url, **kw)
TMP = tempfile.mkdtemp()
TEMPLATE = os.path.join(TMP, 'template.db')


# ---- adapter SQLite: meniru antarmuka PyMySQL (%s -> ?, FOR UPDATE dibuang, baris = dict) ----
class _Cur:
    def __init__(self, c): self.c = c
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, args=()):
        self.c.execute(re.sub(r'\s+FOR UPDATE', '', sql).replace('%s', '?'), tuple(args)); return self
    def fetchall(self): return [dict(r) for r in self.c.fetchall()]
    @property
    def lastrowid(self): return self.c.lastrowid
    @property
    def rowcount(self): return self.c.rowcount

class _Conn:
    def __init__(self, path):
        self.c = sqlite3.connect(path, check_same_thread=False); self.c.row_factory = sqlite3.Row
        self.c.execute('PRAGMA foreign_keys=ON')
    def cursor(self): return _Cur(self.c.cursor())
    def commit(self): self.c.commit()
    def rollback(self): self.c.rollback()
    def close(self): self.c.close()

def sqlite_db(path): return Db(_Conn(path))

def _schema():
    with open(os.path.join(ROOT, 'schema.sql'), encoding='utf-8') as f: t = f.read()
    t = '\n'.join(l for l in t.splitlines() if not l.strip().startswith('--'))
    t = re.sub(r'\)\s*ENGINE=[^;]*;', ');', t)
    t = re.sub(r'INT NOT NULL AUTO_INCREMENT PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT', t)
    return t

def setUpModule():
    d = sqlite_db(TEMPLATE)
    for s in _schema().split(';'):
        if s.strip(): d.run(s)
    d.commit(); seed.jalankan(d, riwayat=False, pesanan=True); d.close()

def tearDownModule(): shutil.rmtree(TMP, ignore_errors=True)


RESI = {'kurir': 'JNE', 'resi': 'JN1234567890'}
ALAMAT = {'metode': 'qris', 'penerima': 'Budi Santoso', 'telepon': '081234567801', 'alamat': 'Jl. Merdeka No. 12, RT 03/RW 05', 'kota': 'Kota Bandung', 'kodePos': '40162'}

def png_url(w=40, h=30, fmt='PNG'):
    b = io.BytesIO(); Image.new('RGB', (w, h), 'green').save(b, fmt)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(b.getvalue()).decode()


class Dasar(unittest.TestCase):
    def setUp(self):
        self.dbfile = os.path.join(TMP, self.id() + '.db'); shutil.copy(TEMPLATE, self.dbfile)
        self.up = os.path.join(TMP, 'up_' + self.id())
        self.app = create_app({'TESTING': True, 'JWT_SECRET': 'r' * 40, 'MIDTRANS_SERVER_KEY': 'SB-Mid-server-xyz', 'UPLOAD_DIR': self.up, 'SWEEP_INTERVAL_MS': 0, 'CORS_ORIGINS': ['http://front.test']})
        self._orig = dbmod.connect
        dbmod.connect = lambda: sqlite_db(self.dbfile)
        self.c = TestClient(self.app, raise_server_exceptions=False, follow_redirects=False)
        self.mid, self.mid_status, self._panggil = [], 'pending', midtrans._panggil
        midtrans._panggil = self._midtrans_palsu
        self.kode = {}                                  # email -> kode OTP terakhir (email asli tidak dikirim saat tes)
        self._kirim = otp.kirim_kode
        otp.kirim_kode = lambda email, username, kode, **k: self.kode.__setitem__(email, kode)
        self._reset = otp.kirim_reset; self._info = otp.kirim_info_password_diubah; self.info = []
        otp.kirim_reset = lambda email, username, kode: self.kode.__setitem__('reset:' + email, kode)
        otp.kirim_info_password_diubah = lambda email, username: self.info.append(email)

    def _midtrans_palsu(self, url, payload=None):
        """Midtrans palsu: mencatat panggilan dan membalas seperti Core API sandbox."""
        self.mid.append((url, payload))
        if payload is None: return {'transaction_status': self.mid_status, 'status_code': '200', 'gross_amount': str(self.mid_total) + '.00'}
        if url.endswith('/cancel'): return {'status_code': '200'}
        oid = payload['transaction_details']['order_id']; self.mid_total = payload['transaction_details']['gross_amount']
        d = {'status_code': '201', 'transaction_id': 'trx-' + oid, 'transaction_status': 'pending'}
        jenis = payload['payment_type']
        if jenis == 'qris': d.update(actions=[{'name': 'generate-qr-code', 'url': f'https://api.sandbox.midtrans.com/v2/qris/{oid}/qr-code'}], qr_string='000201QRIS' + oid)
        elif jenis == 'echannel': d.update(biller_code='70012', bill_key='888123456789')
        else: d.update(va_numbers=[{'bank': payload['bank_transfer']['bank'], 'va_number': '81234567890'}])
        return d

    def tagihan(self, oid, tok, metode=None):
        return self.req('POST', f'/pesanan/{oid}/pembayaran', {'metode': metode} if metode else {}, tok)

    def bukti(self, oid, body, tok):
        """Buat tagihan Midtrans (bila belum) lalu unggah bukti; kembalikan hasil unggah bukti."""
        self.tagihan(oid, tok)
        return self.req('POST', f'/pesanan/{oid}/bukti', body, tok)

    def tearDown(self):
        midtrans._panggil = self._panggil
        dbmod.connect = self._orig; otp.kirim_kode = self._kirim; otp.kirim_reset = self._reset; otp.kirim_info_password_diubah = self._info

    def daftar_penuh(self, username, email, pw):
        """Daftar + verifikasi OTP; kembalikan status verifikasi."""
        s, j = self.req('POST', '/auth/daftar', {'username': username, 'email': email, 'password': pw}); self.assertEqual(s, 200, j)
        return self.req('POST', '/auth/daftar/verifikasi', {'email': email.lower(), 'kode': self.kode[email.lower()]})[0]

    def req(self, m, path, json=None, tok=None, **kw):
        h = {'Authorization': f'Bearer {tok}'} if tok else {}
        r = self.c.request(m, '/api' + path, json=json, headers=h, **kw)
        try: return r.status_code, r.json()
        except ValueError: return r.status_code, None

    def login(self, u, pw):
        s, j = self.req('POST', '/auth/masuk', {'username': u, 'password': pw}); self.assertEqual(s, 200, j); return j['data']['token']

    def sql(self, q, a=()):
        d = sqlite_db(self.dbfile); r = d.all(q, a) if q.strip().upper().startswith('SELECT') else d.run(q, a); d.commit(); d.close(); return r

    def media(self, path):
        """Isi gambar unggahan (BytesIO) dari tabel media, atau None bila tidak ada."""
        folder, nama = path[len('/media/'):].split('/')
        r = self.sql('SELECT data FROM media WHERE folder=%s AND nama=%s', (folder, nama))
        return io.BytesIO(bytes(r[0]['data'])) if r else None

    def stok(self, pid): return self.sql('SELECT stok FROM produk WHERE id=%s', (pid,))[0]['stok']

    def beli(self, tok, pid=3, qty=2):
        self.assertEqual(self.req('POST', '/keranjang', {'produkId': pid, 'qty': qty}, tok)[0], 201)
        s, j = self.req('POST', '/checkout', ALAMAT, tok); self.assertEqual(s, 201, j); return j['data']


class TestAuth(Dasar):
    def test_lupa_password(self):
        tok_lama = self.login('budi_santoso', 'Budi12345')
        s1, j1 = self.req('POST', '/auth/lupa', {'email': 'budi@mail.com'}); s2, j2 = self.req('POST', '/auth/lupa', {'email': 'tidak.ada@mail.com'})
        self.assertEqual((s1, s2, j1, j2), (200, 200, j1, j1))                                   # respons identik: email tidak bisa ditebak
        self.assertNotIn('reset:tidak.ada@mail.com', self.kode)
        self.assertEqual(self.req('POST', '/auth/lupa', {'email': 'bukan-email'})[0], 400)
        kode = self.kode['reset:budi@mail.com']
        R = lambda **k: self.req('POST', '/auth/lupa/reset', {'email': 'budi@mail.com', 'kode': kode, 'password': 'BaruAman123', **k})
        self.assertEqual(R(kode='000000' if kode != '000000' else '111111')[0], 400)             # kode salah
        self.assertEqual(R(password='pendek')[0], 400)                                           # password lemah
        self.assertEqual(self.req('POST', '/auth/lupa/reset', {'email': 'siti@mail.com', 'kode': kode, 'password': 'BaruAman123'})[0], 400)   # kode milik email lain
        self.assertEqual(R()[0], 200)
        self.assertEqual(self.info, ['budi@mail.com'])
        self.assertEqual(R()[0], 400)                                                            # kode sekali pakai
        self.assertEqual(self.req('POST', '/auth/masuk', {'username': 'budi_santoso', 'password': 'Budi12345'})[0], 401)
        self.assertEqual(self.req('POST', '/auth/masuk', {'username': 'budi_santoso', 'password': 'BaruAman123'})[0], 200)
        self.assertEqual(self.req('GET', '/auth/saya', tok=tok_lama)[0], 401)                    # sesi lama keluar

    def test_lupa_password_batas_salah_dan_kedaluwarsa(self):
        self.req('POST', '/auth/lupa', {'email': 'budi@mail.com'}); kode = self.kode['reset:budi@mail.com']; salah = '000000' if kode != '000000' else '111111'
        for _ in range(5): self.req('POST', '/auth/lupa/reset', {'email': 'budi@mail.com', 'kode': salah, 'password': 'BaruAman123'})
        self.assertEqual(self.req('POST', '/auth/lupa/reset', {'email': 'budi@mail.com', 'kode': kode, 'password': 'BaruAman123'})[0], 400)   # terkunci walau kode benar
        self.sql('UPDATE otp_reset SET salah=0, kedaluwarsa=1')
        self.assertEqual(self.req('POST', '/auth/lupa/reset', {'email': 'budi@mail.com', 'kode': kode, 'password': 'BaruAman123'})[0], 400)   # kedaluwarsa
        self.sql('UPDATE pengguna SET aktif=0 WHERE username=%s', ('budi_santoso',)); self.kode.clear()
        self.assertEqual(self.req('POST', '/auth/lupa', {'email': 'budi@mail.com'})[0], 200); self.assertEqual(self.kode, {})        # akun nonaktif: tidak ada email

    def test_kesehatan_dan_katalog(self):
        self.assertEqual(self.req('GET', '/kesehatan')[0], 200)
        s, j = self.req('GET', '/produk'); self.assertEqual(len(j['data']), 12)
        p = j['data'][0]; self.assertEqual(p['nama'], 'Monstera Deliciosa'); self.assertIs(p['bestSeller'], True)
        self.assertEqual(p['spesifikasi']['Pot'], 'Plastik 20 cm'); self.assertIsInstance(p['rating'], float)
        self.assertEqual(self.req('GET', '/produk/999')[0], 404)

    def test_daftar_validasi_dan_duplikat(self):
        base = {'username': 'tono_1', 'email': 'tono@mail.com', 'password': 'Rahasia123'}
        for k, v in (('username', 'a b'), ('email', 'bukan-email'), ('password', 'pendekk')):
            s, j = self.req('POST', '/auth/daftar', {**base, k: v}); self.assertEqual(s, 400, k)
        self.assertEqual(self.daftar_penuh('tono_1', 'tono@mail.com', 'Rahasia123'), 201)
        self.assertEqual(self.req('POST', '/auth/daftar', {**base, 'email': 'lain@mail.com', 'username': 'TONO_1'})[0], 409)
        self.assertEqual(self.req('POST', '/auth/daftar', {**base, 'username': 'tono_2'})[0], 409)
        self.login('tono_1', 'Rahasia123')
        h = self.sql('SELECT hash FROM pengguna WHERE username=%s', ('tono_1',))[0]['hash']
        self.assertNotIn('Rahasia123', h); self.assertTrue(h.startswith(('scrypt:', 'pbkdf2:')))

    def test_otp_akun_belum_dibuat_sebelum_verifikasi(self):
        s, j = self.req('POST', '/auth/daftar', {'username': 'tono_1', 'email': 'Tono@Mail.com', 'password': 'Rahasia123'})
        self.assertEqual((s, j['data']['email']), (200, 'tono@mail.com'))
        self.assertRegex(self.kode['tono@mail.com'], r'^\d{6}$')
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM pengguna WHERE username=%s', ('tono_1',))[0]['n'], 0)
        self.assertEqual(self.req('POST', '/auth/masuk', {'username': 'tono_1', 'password': 'Rahasia123'})[0], 401)
        row = self.sql('SELECT * FROM otp_daftar WHERE email=%s', ('tono@mail.com',))[0]
        self.assertNotIn(self.kode['tono@mail.com'], str(row)); self.assertNotIn('Rahasia123', str(row))   # kode & password tidak tersimpan polos
        self.assertEqual(self.req('POST', '/auth/daftar/verifikasi', {'email': 'tono@mail.com', 'kode': self.kode['tono@mail.com']})[0], 201)
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM otp_daftar')[0]['n'], 0)       # pendaftaran tertunda dibersihkan
        self.login('tono_1', 'Rahasia123')
        self.assertEqual(self.sql('SELECT peran FROM pengguna WHERE username=%s', ('tono_1',))[0]['peran'], 'customer')

    def test_otp_salah_kedaluwarsa_dan_batas_percobaan(self):
        self.req('POST', '/auth/daftar', {'username': 'tono_1', 'email': 'tono@mail.com', 'password': 'Rahasia123'})
        benar = self.kode['tono@mail.com']; salah = '000000' if benar != '000000' else '111111'
        v = lambda k: self.req('POST', '/auth/daftar/verifikasi', {'email': 'tono@mail.com', 'kode': k})
        self.assertEqual(v('12ab')[0], 400)                                   # format
        s, j = v(salah); self.assertEqual(s, 400); self.assertIn('Sisa percobaan: 4', j['error'])
        for _ in range(4): v(salah)
        self.assertEqual(v(benar)[0], 429)                                    # 5 salah -> kode benar pun ditolak sampai kirim ulang
        self.sql('UPDATE otp_daftar SET salah=0, kedaluwarsa=1')              # kedaluwarsa
        s, j = v(benar); self.assertEqual(s, 400); self.assertIn('kedaluwarsa', j['error'])
        self.assertEqual(self.req('POST', '/auth/daftar/verifikasi', {'email': 'tidak@ada.com', 'kode': benar})[0], 404)

    def test_otp_kirim_ulang_jeda_dan_kode_lama_hangus(self):
        self.req('POST', '/auth/daftar', {'username': 'tono_1', 'email': 'tono@mail.com', 'password': 'Rahasia123'})
        lama = self.kode['tono@mail.com']
        s, j = self.req('POST', '/auth/daftar/kirim-ulang', {'email': 'tono@mail.com'}); self.assertEqual(s, 429); self.assertIn('detik', j['error'])
        s, j = self.req('POST', '/auth/daftar', {'username': 'tono_1', 'email': 'tono@mail.com', 'password': 'Rahasia123'}); self.assertEqual(s, 429)
        self.sql('UPDATE otp_daftar SET kirim_terakhir=1')                    # lewati jeda
        self.assertEqual(self.req('POST', '/auth/daftar/kirim-ulang', {'email': 'tono@mail.com'})[0], 200)
        baru = self.kode['tono@mail.com']
        if baru != lama:                                                      # kode lama tidak berlaku lagi
            self.assertEqual(self.req('POST', '/auth/daftar/verifikasi', {'email': 'tono@mail.com', 'kode': lama})[0], 400)
        self.assertEqual(self.req('POST', '/auth/daftar/verifikasi', {'email': 'tono@mail.com', 'kode': baru})[0], 201)
        self.assertEqual(self.req('POST', '/auth/daftar/kirim-ulang', {'email': 'tono@mail.com'})[0], 404)   # sudah jadi akun
        config.cfg['OTP_MAKS_KIRIM'] = 2                                 # batas jumlah kirim per pendaftaran
        self.req('POST', '/auth/daftar', {'username': 'tini_1', 'email': 'tini@mail.com', 'password': 'Rahasia123'})
        self.sql('UPDATE otp_daftar SET kirim_terakhir=1'); self.assertEqual(self.req('POST', '/auth/daftar/kirim-ulang', {'email': 'tini@mail.com'})[0], 200)
        self.sql('UPDATE otp_daftar SET kirim_terakhir=1'); self.assertEqual(self.req('POST', '/auth/daftar/kirim-ulang', {'email': 'tini@mail.com'})[0], 429)

    def test_otp_gagal_kirim_email_tidak_menyimpan_pendaftaran(self):
        from app.errors import ApiError
        def gagal(*a): raise ApiError('Gagal mengirim email kode OTP.', 502)
        otp.kirim_kode = gagal
        self.assertEqual(self.req('POST', '/auth/daftar', {'username': 'tono_1', 'email': 'tono@mail.com', 'password': 'Rahasia123'})[0], 502)
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM otp_daftar')[0]['n'], 0)

    def test_login_salah_diblokir_setelah_5_kali(self):
        for _ in range(5):
            s, j = self.req('POST', '/auth/masuk', {'username': 'budi_santoso', 'password': 'salah123'}); self.assertEqual(s, 401)
        s, j = self.req('POST', '/auth/masuk', {'username': 'budi_santoso', 'password': 'Budi12345'})
        self.assertEqual(s, 429); self.assertIn('menit', j['error'])

    def test_pesan_galat_login_seragam(self):
        a = self.req('POST', '/auth/masuk', {'username': 'budi_santoso', 'password': 'x'})[1]['error']
        b = self.req('POST', '/auth/masuk', {'username': 'tidak_ada', 'password': 'x'})[1]['error']
        self.assertEqual(a, b)

    def test_rbac_dan_token(self):
        self.assertEqual(self.req('GET', '/keranjang')[0], 401)
        self.assertEqual(self.req('GET', '/keranjang', tok='ngawur')[0], 401)
        budi, adm = self.login('budi_santoso', 'Budi12345'), self.login('admin', 'Admin12345')
        self.assertEqual(self.req('GET', '/admin/pesanan', tok=budi)[0], 403)
        self.assertEqual(self.req('POST', '/admin/produk', {}, tok=budi)[0], 403)
        self.assertEqual(self.req('GET', '/keranjang', tok=adm)[0], 403)      # admin bukan customer
        self.assertEqual(self.req('GET', '/admin/pesanan', tok=adm)[0], 200)
        self.assertEqual(self.req('GET', '/auth/saya', tok=budi)[1]['data']['username'], 'budi_santoso')
        self.assertNotIn('hash', self.req('GET', '/auth/saya', tok=budi)[1]['data'])

    def test_logout_dan_sesi_kedaluwarsa(self):
        t = self.login('budi_santoso', 'Budi12345')
        self.assertEqual(self.req('POST', '/auth/keluar', tok=t)[0], 200)
        self.assertEqual(self.req('GET', '/auth/saya', tok=t)[0], 401)
        t2 = self.login('budi_santoso', 'Budi12345')
        self.sql('UPDATE sesi SET kedaluwarsa=1'); self.assertEqual(self.req('GET', '/auth/saya', tok=t2)[0], 401)

    def test_cors(self):
        r = self.c.get('/api/produk', headers={'Origin': 'http://front.test'})
        self.assertEqual(r.headers['Access-Control-Allow-Origin'], 'http://front.test')
        r = self.c.get('/api/produk', headers={'Origin': 'http://jahat.test'})
        self.assertNotIn('Access-Control-Allow-Origin', r.headers)


class TestPesanan(Dasar):
    def test_keranjang_dan_stok(self):
        t = self.login('budi_santoso', 'Budi12345')
        self.assertEqual(self.req('POST', '/keranjang', {'produkId': 3, 'qty': 41}, t)[0], 409)     # stok 40
        self.assertEqual(self.req('POST', '/keranjang', {'produkId': 3, 'qty': 0}, t)[0], 400)
        self.assertEqual(self.req('POST', '/keranjang', {'produkId': 999, 'qty': 1}, t)[0], 400)
        self.assertEqual(self.req('POST', '/keranjang', {'produkId': 3, 'qty': 30}, t)[0], 201)
        self.assertEqual(self.req('POST', '/keranjang', {'produkId': 3, 'qty': 11}, t)[0], 409)     # 30+11 > 40
        self.assertEqual(self.req('PUT', '/keranjang/3', {'qty': 5}, t)[0], 200)
        k = self.req('GET', '/keranjang', tok=t)[1]['data']; self.assertEqual((k[0]['qty'], k[0]['p']['nama']), (5, 'Kaktus Mini Set 3'))
        self.assertEqual(self.req('DELETE', '/keranjang/3', tok=t)[0], 200)
        self.assertEqual(self.req('GET', '/keranjang', tok=t)[1]['data'], [])
        self.assertEqual(self.req('POST', '/checkout', ALAMAT, t)[0], 400)                              # keranjang kosong

    def test_checkout_hitung_server_kurangi_stok_kosongkan_keranjang(self):
        t = self.login('budi_santoso', 'Budi12345'); sebelum = self.stok(3)
        self.req('POST', '/keranjang', {'produkId': 3, 'qty': 2}, t); self.req('POST', '/keranjang', {'produkId': 12, 'qty': 1}, t)
        s, j = self.req('POST', '/checkout', {**ALAMAT, 'total': 1, 'harga': 1}, t)                            # nilai dari klien diabaikan
        o = j['data']; self.assertEqual((s, o['total'], o['status']), (201, 2 * 60000 + 30000, 'menunggu_bayar'))
        self.assertEqual(len(o['items']), 2); self.assertEqual(self.stok(3), sebelum - 2)
        self.assertEqual(self.req('GET', '/keranjang', tok=t)[1]['data'], [])
        self.assertGreater(o['batasBayar'], o['dibuat'])

    def test_pesanan_hanya_milik_sendiri(self):
        budi, siti = self.login('budi_santoso', 'Budi12345'), self.login('siti_aulia', 'Siti12345')
        o = self.beli(budi)
        self.assertEqual(self.req('POST', f"/pesanan/{o['id']}/batal", tok=siti)[0], 404)
        self.assertEqual(self.bukti(o['id'], {'bukti': png_url()}, siti)[0], 404)
        ids = [x['id'] for x in self.req('GET', '/pesanan/saya', tok=siti)[1]['data']]; self.assertNotIn(o['id'], ids)

    def test_batal_kembalikan_stok(self):
        t = self.login('budi_santoso', 'Budi12345'); awal = self.stok(3)
        o = self.beli(t); self.assertEqual(self.stok(3), awal - 2)
        self.assertEqual(self.req('POST', f"/pesanan/{o['id']}/batal", tok=t)[0], 200)
        self.assertEqual(self.stok(3), awal)
        self.assertEqual(self.req('POST', f"/pesanan/{o['id']}/batal", tok=t)[0], 409)               # tidak bisa dua kali

    def test_bukti_bayar_validasi_dan_penyimpanan(self):
        t = self.login('budi_santoso', 'Budi12345'); o = self.beli(t); self.tagihan(o['id'], t); url = f"/pesanan/{o['id']}/bukti"
        palsu = 'data:image/png;base64,' + base64.b64encode(b'<?php echo 1; ?>' * 50).decode()
        self.assertEqual(self.req('POST', url, {'bukti': palsu}, t)[0], 400)                         # magic bytes salah
        self.assertEqual(self.req('POST', url, {'bukti': 'data:text/html;base64,PGI+'}, t)[0], 400)
        self.assertEqual(self.req('POST', url, {'bukti': 'https://x.com/a.png'}, t)[0], 400)         # bukti wajib unggahan
        besar = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'0' * 3_000_000).decode()
        self.assertEqual(self.req('POST', url, {'bukti': besar}, t)[0], 400)
        self.assertEqual(self.req('POST', url, {'bukti': png_url(fmt='WEBP')}, t)[0], 200)
        o2 = [x for x in self.req('GET', '/pesanan/saya', tok=t)[1]['data'] if x['id'] == o['id']][0]
        self.assertEqual(o2['status'], 'menunggu_verifikasi')
        self.assertRegex(o2['bukti'], r'^/media/bukti/[0-9a-f]{32}\.jpg$')
        with Image.open(self.media(o2['bukti'])) as im: self.assertEqual(im.format, 'JPEG')                                          # digambar ulang -> JPEG bersih
        r = self.c.get(o2['bukti']); self.assertEqual(r.status_code, 200); 
        self.assertEqual(self.req('POST', url, {'bukti': png_url()}, t)[0], 409)                     # sudah dibayar

    def test_media_tolak_path_traversal(self):
        self.assertEqual(self.c.get('/media/bukti/..%2F..%2Fetc%2Fpasswd').status_code, 404)
        self.assertEqual(self.c.get('/media/produk/abc.jpg').status_code, 404)

    def test_alur_penuh_verifikasi_kirim_terima_ulasan(self):
        budi, adm = self.login('budi_santoso', 'Budi12345'), self.login('admin', 'Admin12345')
        terjual = self.sql('SELECT terjual FROM produk WHERE id=3')[0]['terjual']
        o = self.beli(budi); oid = o['id']
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/verifikasi', {'setuju': True}, adm)[0], 409)   # belum bayar
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 3, 'rating': 5, 'teks': 'Bagus sekali!'}, budi)[0], 403)  # belum diterima
        self.bukti(oid, {'bukti': png_url()}, budi)
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/kirim', RESI, adm)[0], 409)
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/verifikasi', {'setuju': True}, adm)[0], 200)
        self.assertEqual(self.sql('SELECT terjual FROM produk WHERE id=3')[0]['terjual'], terjual + 2)
        self.assertEqual(self.req('POST', f'/pesanan/{oid}/terima', tok=budi)[0], 409)                         # belum dikirim
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/kirim', RESI, adm)[0], 200)
        self.assertEqual(self.req('POST', f'/pesanan/{oid}/terima', tok=budi)[0], 200)
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 3, 'rating': 4, 'teks': 'Bagus sekali!'}, budi)[0], 201)  # kini boleh
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 3, 'rating': 4, 'teks': 'Bagus sekali!'}, budi)[0], 409)
        adm_list = self.req('GET', '/admin/pesanan', tok=adm)[1]['data']
        self.assertEqual([x for x in adm_list if x['id'] == oid][0]['pembeli'], 'budi_santoso')

    def test_ulasan_aturan(self):
        siti, adm = self.login('siti_aulia', 'Siti12345'), self.login('admin', 'Admin12345')
        # siti belum pernah menerima produk 9 -> ditolak
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 9, 'rating': 5, 'teks': 'Bagus sekali!'}, siti)[0], 403)
        # siti sudah menerima produk 1? (pesanan 'dikirim' belum selesai) -> ditolak; produk 2 (selesai) sudah dibeli -> boleh
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 1, 'rating': 5, 'teks': 'Bagus sekali!'}, siti)[0], 403)
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 2, 'rating': 9, 'teks': 'Bagus sekali!'}, siti)[0], 400)
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 2, 'rating': 4, 'teks': 'ok'}, siti)[0], 400)
        s, j = self.req('POST', '/ulasan', {'produkId': 2, 'rating': 3, 'teks': 'Cukup bagus untuk pemula.'}, siti); self.assertEqual(s, 201, j)
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 2, 'rating': 3, 'teks': 'Cukup bagus untuk pemula.'}, siti)[0], 409)
        self.assertTrue(self.req('GET', '/ulasan/sudah/2', tok=siti)[1]['data']['sudah'])
        self.assertAlmostEqual(self.req('GET', '/produk/2')[1]['data']['rating'], 4.0)                       # rata-rata (5 dan 3)
        rid = [r for r in self.req('GET', '/produk/2/ulasan')[1]['data'] if r['nama'] == 'siti_aulia'][0]['id']
        self.assertEqual(self.req('POST', f'/admin/ulasan/{rid}/balas', {'teks': 'ab'}, adm)[0], 400)
        self.assertEqual(self.req('POST', f'/admin/ulasan/{rid}/balas', {'teks': 'Terima kasih!'}, adm)[0], 200)
        u = [r for r in self.req('GET', '/admin/ulasan', tok=adm)[1]['data'] if r['id'] == rid][0]
        self.assertEqual((u['balasan']['teks'], u['produk']), ('Terima kasih!', 'Sansevieria Trifasciata'))
        self.assertEqual(self.req('POST', f'/admin/ulasan/{rid}/balas', {'teks': 'Terima kasih!'}, siti)[0], 403)

    def test_verifikasi_tolak_kembalikan_stok(self):
        t, adm = self.login('budi_santoso', 'Budi12345'), self.login('admin', 'Admin12345'); awal = self.stok(3)
        o = self.beli(t); self.bukti(o['id'], {'bukti': png_url()}, t)
        s, _ = self.req('POST', f"/admin/pesanan/{o['id']}/verifikasi", {'setuju': False, 'alasan': 'Nominal kurang'}, adm); self.assertEqual(s, 200)
        x = [p for p in self.req('GET', '/pesanan/saya', tok=t)[1]['data'] if p['id'] == o['id']][0]
        # ditolak != dibatalkan: kembali menunggu bayar (stok tetap dipesan) supaya bukti bisa diunggah ulang
        self.assertEqual((x['status'], x['alasan'], x['ditolak'], x['bukti']), ('menunggu_bayar', 'Nominal kurang', 1, None)); self.assertEqual(self.stok(3), awal - 2)
        self.assertEqual(self.bukti(o['id'], {'bukti': png_url()}, t)[0], 200)              # unggah ulang
        x = [p for p in self.req('GET', '/pesanan/saya', tok=t)[1]['data'] if p['id'] == o['id']][0]
        self.assertEqual((x['status'], x['alasan']), ('menunggu_verifikasi', ''))
        self.req('POST', f"/admin/pesanan/{o['id']}/verifikasi", {'setuju': False}, adm)
        self.req('POST', f"/pesanan/{o['id']}/batal", tok=t); self.assertEqual(self.stok(3), awal)               # batal manual -> stok kembali

    def test_kirim_wajib_kurir_resi_dan_lacak(self):
        t, adm, siti = self.login('budi_santoso', 'Budi12345'), self.login('admin', 'Admin12345'), self.login('siti_aulia', 'Siti12345')
        o = self.beli(t); oid = o['id']
        self.bukti(oid, {'bukti': png_url()}, t); self.req('POST', f'/admin/pesanan/{oid}/verifikasi', {'setuju': True}, adm)
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/kirim', {'kurir': 'JNE'}, adm)[0], 400)             # resi wajib
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/kirim', {'kurir': 'JNE', 'resi': '??'}, adm)[0], 400)
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/kirim', {'kurir': 'JNE', 'resi': 'jn 123 456 7'}, adm)[0], 200)   # dinormalkan
        for kode in (str(oid), f'#{oid}', f'SK-{oid:06d}', 'jn1234567'):
            s, j = self.req('GET', '/lacak?kode=' + kode.replace('#', '%23'), tok=t); self.assertEqual(s, 200, kode)
            self.assertEqual((j['data']['pesanan']['id'], j['data']['pesanan']['resi'], j['data']['pesanan']['kurir']), (oid, 'JN1234567', 'JNE'))
        tl = j['data']['timeline']; self.assertEqual([x['selesai'] for x in tl], [True, True, True, True, False, False])
        self.assertEqual(self.req('GET', f'/lacak?kode={oid}', tok=siti)[0], 404)                                # bukan milik siti
        self.assertEqual(self.req('GET', f'/lacak?kode={oid}', tok=adm)[0], 200)                                 # admin boleh semua
        self.assertEqual(self.req('GET', '/lacak?kode=ZZZZ99', tok=t)[0], 404)
        self.req('POST', f'/pesanan/{oid}/terima', tok=t)
        self.assertEqual([x['selesai'] for x in self.req('GET', f'/lacak?kode={oid}', tok=t)[1]['data']['timeline']], [True] * 6)
        o2 = self.beli(t); self.bukti(o2['id'], {'bukti': png_url()}, t); self.req('POST', f"/admin/pesanan/{o2['id']}/verifikasi", {'setuju': True}, adm)
        self.assertEqual(self.req('POST', f"/admin/pesanan/{o2['id']}/kirim", {'kurir': 'JNE', 'resi': 'JN1234567'}, adm)[0], 409)   # resi unik

    def test_balas_ulasan_bergantian(self):
        adm, siti, budi = self.login('admin', 'Admin12345'), self.login('siti_aulia', 'Siti12345'), self.login('budi_santoso', 'Budi12345')
        rid, pid = self.sql("SELECT r.id, r.produk_id FROM ulasan r JOIN pengguna u ON u.id=r.user_id WHERE u.username='siti_aulia' LIMIT 1")[0].values()
        self.sql('UPDATE ulasan SET balasan_teks=NULL, balasan_dibuat=NULL WHERE id=%s', (rid,))
        self.assertEqual(self.req('POST', f'/ulasan/{rid}/balas', {'teks': 'halo admin'}, siti)[0], 409)          # admin belum membalas
        self.req('POST', f'/admin/ulasan/{rid}/balas', {'teks': 'Terima kasih ya!'}, adm)
        self.assertEqual(self.req('POST', f'/ulasan/{rid}/balas', {'teks': 'halo admin'}, budi)[0], 404)         # bukan pemilik
        self.assertEqual(self.req('POST', f'/ulasan/{rid}/balas', {'teks': 'ok'}, siti)[0], 400)
        self.assertEqual(self.req('POST', f'/ulasan/{rid}/balas', {'teks': 'Sama-sama kak'}, siti)[0], 201)
        self.assertEqual(self.req('POST', f'/ulasan/{rid}/balas', {'teks': 'dobel'}, siti)[0], 409)              # harus bergantian
        self.assertEqual(self.req('POST', f'/admin/ulasan/{rid}/balas', {'teks': 'Ditunggu pesanan berikutnya'}, adm)[0], 200)
        self.assertEqual(self.req('POST', f'/admin/ulasan/{rid}/balas', {'teks': 'dobel admin'}, adm)[0], 409)
        r = [x for x in self.req('GET', f'/produk/{pid}/ulasan')[1]['data'] if x['id'] == rid][0]
        self.assertEqual([(x['dari'], x['teks']) for x in r['lanjutan']], [('customer', 'Sama-sama kak'), ('admin', 'Ditunggu pesanan berikutnya')])
        self.assertEqual(self.req('POST', f'/admin/ulasan/{rid}/balas', {'teks': 'x'}, siti)[0], 403)

    def test_midtrans_pembayaran_qris_va_dan_tidak_pernah_auto_setuju(self):
        t, adm = self.login('budi_santoso', 'Budi12345'), self.login('admin', 'Admin12345'); o = self.beli(t); oid = o['id']
        s, j = self.tagihan(oid, t); self.assertEqual(s, 200, j)
        m = j['data']['midtrans']['data']; self.assertEqual((m['metode'], m['jenis']), ('qris', 'qris'))
        self.assertTrue(m['qrUrl'].startswith('https://api.sandbox.midtrans.com/')); self.assertTrue(m['qrString'])
        url, p = self.mid[0]; self.assertTrue(url.endswith('/v2/charge')); self.assertEqual(p['payment_type'], 'qris')
        self.assertEqual(p['transaction_details']['gross_amount'], o['total'])
        self.assertEqual(sum(i['price'] * i['quantity'] for i in p['item_details']), o['total'])
        mid = self.sql('SELECT midtrans_id FROM pesanan WHERE id=%s', (oid,))[0]['midtrans_id']; self.assertRegex(mid, rf'^SK{oid}-[0-9a-f]{{6}}$')
        n = len(self.mid); self.tagihan(oid, t); self.assertEqual(len(self.mid), n)                                # metode sama: tagihan yang sama
        s, j = self.tagihan(oid, t, 'bca'); self.assertEqual(s, 200, j)                                          # ganti metode: yang lama dibatalkan
        self.assertTrue(any(u.endswith(f'/{mid}/cancel') for u, _ in self.mid)); self.assertEqual(j['data']['midtrans']['data']['va'], '81234567890')
        self.assertEqual(self.tagihan(oid, t, 'tidak-ada')[0], 400)
        s, j = self.tagihan(oid, t, 'mandiri'); self.assertEqual((j['data']['midtrans']['data']['kodePerusahaan'], j['data']['midtrans']['data']['kodeBayar']), ('70012', '888123456789'))
        mid = self.sql('SELECT midtrans_id FROM pesanan WHERE id=%s', (oid,))[0]['midtrans_id']
        import hashlib
        def notif(status='settlement', total=None, kunci='SB-Mid-server-xyz', **k):
            d = {'order_id': mid, 'status_code': '200', 'gross_amount': f'{total or o["total"]}.00', 'transaction_status': status, **k}
            d['signature_key'] = hashlib.sha512((d['order_id'] + d['status_code'] + d['gross_amount'] + kunci).encode()).hexdigest(); return d
        row = lambda: self.sql('SELECT status, midtrans_status FROM pesanan WHERE id=%s', (oid,))[0]
        self.assertEqual(self.req('POST', '/midtrans/notifikasi', {**notif(), 'signature_key': 'palsu'})[0], 403)
        self.assertEqual(self.req('POST', '/midtrans/notifikasi', notif(kunci='kunci-lain'))[0], 403)
        self.req('POST', '/midtrans/notifikasi', notif(total=1000)); self.assertEqual(row()['midtrans_status'], 'pending')   # nominal tidak cocok
        terjual = self.sql('SELECT terjual FROM produk WHERE id=3')[0]['terjual']
        self.assertEqual(self.req('POST', '/midtrans/notifikasi', notif())[0], 200)
        self.assertEqual(dict(row()), {'status': 'menunggu_bayar', 'midtrans_status': 'settlement'})            # dicatat, TIDAK otomatis disetujui
        self.assertEqual(self.sql('SELECT terjual FROM produk WHERE id=3')[0]['terjual'], terjual)
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/verifikasi', {'setuju': True}, adm)[0], 409)    # tanpa bukti tak bisa disetujui
        self.assertEqual(self.req('POST', f'/pesanan/{oid}/bukti', {'bukti': png_url()}, t)[0], 200)
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/verifikasi', {'setuju': True}, adm)[0], 200)
        self.assertEqual(row()['status'], 'diproses')

    def test_midtrans_nonaktif_dan_bukti_wajib_tagihan(self):
        t = self.login('budi_santoso', 'Budi12345'); o = self.beli(t)
        self.assertEqual(self.req('POST', f"/pesanan/{o['id']}/bukti", {'bukti': png_url()}, t)[0], 409)         # belum ada tagihan
        config.cfg['MIDTRANS_SERVER_KEY'] = ''
        self.assertEqual(self.tagihan(o['id'], t)[0], 503)
        self.assertEqual(self.req('GET', '/pembayaran/metode')[0], 200)
        self.assertEqual(self.req('POST', '/pesanan/1/pembayaran', {})[0], 401)

    def test_cek_status_midtrans_hanya_mencatat(self):
        t, adm = self.login('budi_santoso', 'Budi12345'), self.login('admin', 'Admin12345'); o = self.beli(t); self.tagihan(o['id'], t)
        self.mid_status = 'settlement'
        s, j = self.req('POST', f"/pesanan/{o['id']}/pembayaran/cek", tok=t); self.assertEqual((s, j['data']['midtrans']['status'], j['data']['status']), (200, 'settlement', 'menunggu_bayar'))
        self.mid_status = 'expire'
        s, j = self.req('POST', f"/admin/pesanan/{o['id']}/midtrans/cek", tok=adm); self.assertEqual(j['data']['midtrans']['status'], 'expire')
        self.assertEqual(self.req('POST', f"/admin/pesanan/{o['id']}/midtrans/cek", tok=t)[0], 403)

    def test_pesanan_kedaluwarsa_dibatalkan_otomatis(self):
        t = self.login('budi_santoso', 'Budi12345'); awal = self.stok(3); o = self.beli(t)
        self.sql('UPDATE pesanan SET batas_bayar=1 WHERE id=%s', (o['id'],))
        self.req('GET', '/produk')                                                                    # sapu dipicu dari katalog
        x = [p for p in self.req('GET', '/pesanan/saya', tok=t)[1]['data'] if p['id'] == o['id']][0]
        self.assertEqual((x['status'], x['alasan']), ('dibatalkan', 'Melewati batas waktu pembayaran.')); self.assertEqual(self.stok(3), awal)

    def test_stok_habis_ditolak_saat_checkout_kedua(self):
        budi, siti = self.login('budi_santoso', 'Budi12345'), self.login('siti_aulia', 'Siti12345')
        self.sql('UPDATE produk SET stok=3 WHERE id=3')
        self.req('POST', '/keranjang', {'produkId': 3, 'qty': 3}, budi); self.req('POST', '/keranjang', {'produkId': 3, 'qty': 3}, siti)
        self.assertEqual(self.req('POST', '/checkout', ALAMAT, budi)[0], 201)
        s, j = self.req('POST', '/checkout', ALAMAT, siti); self.assertEqual(s, 409); self.assertIn('Stok', j['error'])
        self.assertEqual(self.stok(3), 0)


class TestAdmin(Dasar):
    def prod(self, **k):
        return {'nama': 'Ficus Lyrata', 'kategori': 'Tanaman Hias Daun', 'harga': 150000, 'stok': 10,
                'gambar': 'https://loremflickr.com/640/640/ficus?lock=1', 'deskripsi': 'Daun besar.',
                'spek': 'Tinggi: 50 cm\nCahaya = Terang\n\n', 'bestSeller': True, **k}

    def test_crud_produk_dan_validasi(self):
        adm = self.login('admin', 'Admin12345')
        for k, v in (('nama', 'ab'), ('kategori', 'Ngawur'), ('harga', 5), ('harga', 'abc'), ('stok', -1), ('gambar', 'http://x.com/a.png'), ('gambar', 'javascript:alert(1)')):
            self.assertEqual(self.req('POST', '/admin/produk', self.prod(**{k: v}), adm)[0], 400, (k, v))
        s, j = self.req('POST', '/admin/produk', self.prod(), adm); p = j['data']
        self.assertEqual((s, p['spesifikasi'], p['terjual'], p['rating']), (201, {'Tinggi': '50 cm', 'Cahaya': 'Terang'}, 0, 0.0))
        s, j = self.req('PUT', f"/admin/produk/{p['id']}", self.prod(harga=175000, stok=7, gambar=p['gambar']), adm)
        self.assertEqual((s, j['data']['harga'], j['data']['stok']), (200, 175000, 7))
        self.assertEqual(self.req('PUT', '/admin/produk/999', self.prod(), adm)[0], 404)
        for salah in ('Tinggi 40 cm', 'Tinggi:', ': 40', 'A: 1\nbaris tanpa titik dua'):          # spesifikasi salah format ditolak dengan pesan, bukan dibuang diam-diam
            s, j = self.req('POST', '/admin/produk', self.prod(spek=salah), adm); self.assertEqual(s, 400, salah); self.assertIn('Spesifikasi baris', j['error'])
        self.assertEqual(self.req('POST', '/admin/produk', self.prod(spek='\n'.join(f'K{i}: v' for i in range(13))), adm)[0], 400)
        self.assertEqual(self.req('DELETE', f"/admin/produk/{p['id']}", tok=adm)[0], 200)
        self.assertEqual(self.req('GET', f"/produk/{p['id']}")[0], 404)

    def test_unggah_foto_produk_dan_hapus_berkas_lama(self):
        adm = self.login('admin', 'Admin12345')
        s, j = self.req('POST', '/admin/produk', self.prod(gambar=png_url(2000, 1500)), adm); p = j['data']; self.assertEqual(s, 201)
        f = p['gambar']; self.assertTrue(self.media(f) is not None)
        with Image.open(self.media(f)) as im: self.assertLessEqual(max(im.size), 1200)                                          # diperkecil
        s, j = self.req('PUT', f"/admin/produk/{p['id']}", self.prod(gambar=p['gambar']), adm)        # URL milik sendiri dipertahankan
        self.assertEqual(j['data']['gambar'], p['gambar']); self.assertTrue(self.media(f) is not None)
        self.req('PUT', f"/admin/produk/{p['id']}", self.prod(gambar=png_url()), adm)                 # ganti -> berkas lama terhapus
        self.assertFalse(self.media(f) is not None)

    def test_hapus_produk_tidak_merusak_riwayat_pesanan(self):
        adm, t = self.login('admin', 'Admin12345'), self.login('budi_santoso', 'Budi12345'); o = self.beli(t)
        self.assertEqual(self.req('DELETE', '/admin/produk/3', tok=adm)[0], 200)
        x = [p for p in self.req('GET', '/pesanan/saya', tok=t)[1]['data'] if p['id'] == o['id']][0]
        self.assertEqual((x['items'][0]['nama'], x['items'][0]['produkId']), ('Kaktus Mini Set 3', None))

    def test_nonaktifkan_pengguna(self):
        adm, t = self.login('admin', 'Admin12345'), self.login('budi_santoso', 'Budi12345')
        users = self.req('GET', '/admin/pengguna', tok=adm)[1]['data']; self.assertEqual({u['peran'] for u in users}, {'customer'})
        self.assertEqual(self.req('POST', '/admin/pengguna/1/toggle', tok=adm)[0], 404)              # admin tak bisa diubah
        self.assertEqual(self.req('POST', '/admin/pengguna/2/toggle', tok=adm)[1]['data'], {'aktif': False})
        self.assertEqual(self.req('GET', '/auth/saya', tok=t)[0], 401)                               # sesi langsung putus
        s, j = self.req('POST', '/auth/masuk', {'username': 'budi_santoso', 'password': 'Budi12345'}); self.assertEqual((s, j['error']), (403, 'Akun dinonaktifkan. Hubungi admin.'))
        self.req('POST', '/admin/pengguna/2/toggle', tok=adm); self.login('budi_santoso', 'Budi12345')

    def test_kontak_dan_favorit_dan_profil(self):
        adm, t = self.login('admin', 'Admin12345'), self.login('budi_santoso', 'Budi12345')
        m = {'nama': 'Tono', 'email': 'tono@mail.com', 'jenis': 'Pertanyaan', 'isi': 'Apakah ada pengiriman luar kota?'}
        self.assertEqual(self.req('POST', '/kontak', {**m, 'jenis': 'Spam'})[0], 400)
        self.assertEqual(self.req('POST', '/kontak', {**m, 'isi': 'pendek'})[0], 400)
        self.assertEqual(self.req('POST', '/kontak', m)[0], 201)
        self.assertEqual(self.req('GET', '/admin/kontak', tok=t)[0], 403)
        self.assertEqual(self.req('GET', '/admin/kontak', tok=adm)[1]['data'][0]['nama'], 'Tono')
        self.assertEqual(self.req('POST', '/favorit/5/toggle', tok=t)[1]['data'], {'aktif': True})
        self.assertEqual(self.req('GET', '/favorit', tok=t)[1]['data'], [5])
        self.assertEqual(self.req('POST', '/favorit/5/toggle', tok=t)[1]['data'], {'aktif': False})
        self.assertEqual(self.req('PUT', '/profil', {'username': 'siti_aulia', 'email': 'budi@mail.com'}, t)[0], 409)
        s, j = self.req('PUT', '/profil', {'username': 'budi_baru', 'email': 'budi@mail.com', 'foto': png_url()}, t)
        self.assertEqual((s, j['data']['username']), (200, 'budi_baru')); self.assertRegex(j['data']['foto'], r'/media/foto/[0-9a-f]{32}\.jpg$')
        s, j2 = self.req('PUT', '/profil', {'username': 'budi_baru', 'email': 'budi@mail.com', 'foto': j['data']['foto']}, t)
        self.assertEqual(j2['data']['foto'], j['data']['foto'])

    def test_galat_json_dan_body_rusak(self):
        adm = self.login('admin', 'Admin12345')
        r = self.c.post('/api/admin/produk', data='bukan json', headers={'Authorization': f'Bearer {adm}', 'Content-Type': 'application/json'})
        self.assertEqual((r.status_code, r.json()['error']), (400, 'Format data tidak valid.'))
        self.assertEqual(self.c.get('/api/tidak-ada').json(), {'error': 'Data tidak ditemukan.'})


class TestKeamananTambahan(Dasar):
    """Ganti email wajib OTP, OTP gagal tertutup tanpa SMTP, password seed acak, HSTS."""
    def test_ganti_email_wajib_password_dan_otp(self):
        tok = self.login('budi_santoso', 'Budi12345'); R = lambda m, p, j=None: self.req(m, p, j, tok=tok)
        asli = self.sql('SELECT email FROM pengguna WHERE username=%s', ('budi_santoso',))[0]['email']
        self.assertEqual(R('PUT', '/profil', {'username': 'budi_santoso', 'email': 'baru@mail.com'})[0], 400)       # tidak bisa lewat profil
        self.assertEqual(R('PUT', '/profil', {'username': 'budi_santoso', 'email': asli.upper()})[0], 200)          # email sama (beda huruf) tetap boleh
        s, j = R('POST', '/profil/email/minta', {'email': 'baru@mail.com', 'password': 'salahsalah1'}); self.assertEqual(s, 403)
        self.assertEqual(R('POST', '/profil/email/minta', {'email': 'siti@mail.com', 'password': 'Budi12345'})[0], 409)   # dipakai orang lain
        self.assertEqual(R('POST', '/profil/email/minta', {'email': 'bukan-email', 'password': 'Budi12345'})[0], 400)
        s, j = R('POST', '/profil/email/minta', {'email': 'Baru@Mail.com', 'password': 'Budi12345'}); self.assertEqual((s, j['data']['email']), (200, 'baru@mail.com'))
        self.assertEqual(self.sql('SELECT email FROM pengguna WHERE username=%s', ('budi_santoso',))[0]['email'], asli)      # belum berubah sebelum kode benar
        kode = self.kode['baru@mail.com']; salah = '000000' if kode != '000000' else '111111'
        s, j = R('POST', '/profil/email/verifikasi', {'kode': salah}); self.assertEqual(s, 400); self.assertIn('Sisa percobaan: 4', j['error'])
        s, j = R('POST', '/profil/email/verifikasi', {'kode': kode}); self.assertEqual((s, j['data']['email']), (200, 'baru@mail.com'))
        self.assertEqual(R('POST', '/profil/email/verifikasi', {'kode': kode})[0], 404)       # satu kali pakai

    def test_ganti_email_kedaluwarsa_dan_jeda(self):
        tok = self.login('budi_santoso', 'Budi12345'); R = lambda m, p, j=None: self.req(m, p, j, tok=tok)
        R('POST', '/profil/email/minta', {'email': 'baru@mail.com', 'password': 'Budi12345'})
        s, j = R('POST', '/profil/email/minta', {'email': 'baru@mail.com', 'password': 'Budi12345'}); self.assertEqual(s, 429)
        self.sql('UPDATE otp_email SET kedaluwarsa=1')
        s, j = R('POST', '/profil/email/verifikasi', {'kode': self.kode['baru@mail.com']}); self.assertEqual(s, 400); self.assertIn('kedaluwarsa', j['error'])

    def test_ganti_email_butuh_login(self):
        self.assertEqual(self.req('POST', '/profil/email/minta', {'email': 'a@b.com', 'password': 'x'})[0], 401)
        self.assertEqual(self.req('POST', '/profil/email/verifikasi', {'kode': '123456'})[0], 401)

    def test_otp_gagal_tertutup_tanpa_smtp(self):
        otp.kirim_kode = self._kirim                         # pakai fungsi asli
        config.cfg.update(SMTP_HOST='', OTP_CETAK_KODE=False)
        s, j = self.req('POST', '/auth/daftar', {'username': 'tono_1', 'email': 'tono@mail.com', 'password': 'Rahasia123'})
        self.assertEqual(s, 503); self.assertNotIn('kode', str(j).lower().replace('kode otp', ''))
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM otp_daftar')[0]['n'], 0)
        config.cfg['OTP_CETAK_KODE'] = True              # opt-in eksplisit untuk pengembangan lokal
        self.assertEqual(self.req('POST', '/auth/daftar', {'username': 'tono_1', 'email': 'tono@mail.com', 'password': 'Rahasia123'})[0], 200)

    def test_seed_perintah_cli_memakai_password_acak(self):
        baru = os.path.join(TMP, 'seed_acak.db'); d = sqlite_db(baru)          # database kosong baru, seperti `python manage.py init-db` lalu `seed`
        for s in _schema().split(';'):
            if s.strip(): d.run(s)
        d.commit(); kred = seed.jalankan(d, riwayat=False, acak=True, pesanan=True); d.close(); self.dbfile = baru
        sandi = dict(kred); self.assertEqual(set(sandi), {'admin', 'budi_santoso', 'siti_aulia'})
        self.assertTrue(all(len(v) >= 12 for v in sandi.values()) and len(set(sandi.values())) == 3)
        for lama in ('Admin12345', 'Budi12345', 'Siti12345'): self.assertNotIn(lama, sandi.values())
        self.assertEqual(self.req('POST', '/auth/masuk', {'username': 'admin', 'password': 'Admin12345'})[0], 401)
        self.assertEqual(self.req('POST', '/auth/masuk', {'username': 'admin', 'password': sandi['admin']})[0], 200)

    def test_produk_menyertakan_dibuat_dan_baru_masuk_adalah_tanaman(self):
        s, j = self.req('GET', '/produk'); self.assertEqual(s, 200)
        self.assertTrue(all(isinstance(p['dibuat'], int) for p in j['data']))
        terbaru = sorted(j['data'], key=lambda p: (-p['dibuat'], -p['id']))[:2]
        self.assertEqual([p['nama'] for p in terbaru], ['Calathea Orbifolia', 'Aglonema Red Sumatra'])      # bukan pupuk/media tanam

    def test_landing_slider_dari_data_produk_bukan_id_tetap(self):
        r = self.c.get('/landing/script.js'); js = r.content.decode(); 
        self.assertNotIn('SLIDE_ALL', js); self.assertNotIn('kartuSamping', js)
        self.assertIn('p.deskripsi', js); self.assertIn("'Baru masuk'", js); self.assertIn("'Harga termurah'", js)

    def test_hsts_hanya_lewat_https(self):
        self.assertNotIn('Strict-Transport-Security', self.c.get('/').headers)
        self.assertIn('max-age=', TestClient(self.app, base_url='https://localhost').get('/').headers['Strict-Transport-Security'])


class TestChat(Dasar):
    """Chat pelanggan <-> admin: isolasi data (IDOR), validasi, batas kirim, tanda dibaca."""
    def setUp(self):
        super().setUp()
        self.bud = self.login('budi_santoso', 'Budi12345'); self.sit = self.login('siti_aulia', 'Siti12345'); self.adm = self.login('admin', 'Admin12345')
        self.uid = lambda u: self.sql('SELECT id FROM pengguna WHERE username=%s', (u,))[0]['id']

    def test_alur_dasar_dan_isolasi_antar_pelanggan(self):
        s, j = self.req('POST', '/chat', {'isi': 'Halo, Anggrek Sari ready?'}, self.bud); self.assertEqual(s, 201); self.assertEqual(j['data']['dari'], 'customer')
        self.req('POST', '/chat', {'isi': 'Rahasia Budi'}, self.bud)
        self.assertEqual(len(self.req('GET', '/chat', tok=self.bud)[1]['data']['pesan']), 2)
        self.assertEqual(self.req('GET', '/chat', tok=self.sit)[1]['data']['pesan'], [])                       # Siti tidak melihat chat Budi
        self.assertEqual(self.req('GET', f"/admin/chat/{self.uid('budi_santoso')}", tok=self.sit)[0], 403)   # pelanggan tidak bisa pakai endpoint admin
        self.assertEqual(self.req('GET', '/admin/chat', tok=self.bud)[0], 403)
        self.assertEqual(self.req('POST', f"/admin/chat/{self.uid('budi_santoso')}", {'isi': 'x'}, self.bud)[0], 403)
        self.assertEqual(self.req('POST', '/chat', {'isi': 'x', 'user_id': self.uid('siti_aulia'), 'dari': 'admin'}, self.bud)[1]['data']['dari'], 'customer')  # id/peran dari input diabaikan
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM chat_pesan WHERE user_id=%s', (self.uid('siti_aulia'),))[0]['n'], 0)

    def test_butuh_login_dan_admin_tidak_memakai_endpoint_pelanggan(self):
        for m, p in (('GET', '/chat'), ('POST', '/chat'), ('GET', '/chat/belum'), ('GET', '/admin/chat'), ('GET', '/admin/chat/belum')):
            self.assertEqual(self.req(m, p, {'isi': 'x'} if m == 'POST' else None)[0], 401, p)
        self.assertEqual(self.req('POST', '/chat', {'isi': 'x'}, self.adm)[0], 403)                            # admin tidak punya percakapan sendiri

    def test_admin_membalas_dan_tanda_dibaca(self):
        b = self.uid('budi_santoso'); self.req('POST', '/chat', {'isi': 'Pertanyaan 1'}, self.bud)
        s, j = self.req('GET', '/admin/chat', tok=self.adm); self.assertEqual((j['data'][0]['username'], j['data'][0]['belum']), ('budi_santoso', 1))
        self.assertEqual(self.req('GET', '/admin/chat/belum', tok=self.adm)[1]['data']['belum'], 1)
        s, j = self.req('GET', f'/admin/chat/{b}', tok=self.adm); self.assertEqual(len(j['data']['pesan']), 1); self.assertEqual(j['data']['pelanggan']['username'], 'budi_santoso')
        self.assertEqual(self.req('GET', '/admin/chat/belum', tok=self.adm)[1]['data']['belum'], 0)             # dibuka admin = terbaca
        s, j = self.req('GET', '/chat', tok=self.bud); self.assertEqual(j['data']['dibacaSampai'], j['data']['pesan'][0]['id'])   # Budi tahu pesannya dibaca
        s, j = self.req('POST', f'/admin/chat/{b}', {'isi': 'Ready, stok 30.'}, self.adm); self.assertEqual((s, j['data']['dari']), (201, 'admin'))
        self.assertEqual(self.req('GET', '/chat/belum', tok=self.bud)[1]['data']['belum'], 1)
        self.assertEqual(self.sql('SELECT admin_id FROM chat_pesan WHERE dari=%s', ('admin',))[0]['admin_id'], self.uid('admin'))
        akhir = self.req('GET', '/chat', tok=self.bud)[1]['data']['pesan'][-1]['id']
        self.assertEqual(self.req('GET', f'/chat?sejak={akhir}', tok=self.bud)[1]['data']['pesan'], [])        # polling: tidak ada yang baru
        self.assertEqual(self.req('GET', '/chat/belum', tok=self.bud)[1]['data']['belum'], 0)

    def test_admin_hanya_membalas_tidak_memulai_dan_target_harus_pelanggan(self):
        self.assertEqual(self.req('POST', f"/admin/chat/{self.uid('siti_aulia')}", {'isi': 'Halo'}, self.adm)[0], 404)   # Siti belum pernah chat
        self.assertEqual(self.req('POST', f"/admin/chat/{self.uid('admin')}", {'isi': 'Halo'}, self.adm)[0], 404)        # target admin
        self.assertEqual(self.req('GET', '/admin/chat/99999', tok=self.adm)[0], 404)
        self.req('POST', '/chat', {'isi': 'Tes'}, self.sit); self.sql('UPDATE pengguna SET aktif=0 WHERE username=%s', ('siti_aulia',))
        self.assertEqual(self.req('POST', f"/admin/chat/{self.uid('siti_aulia')}", {'isi': 'Halo'}, self.adm)[0], 409)   # akun nonaktif

    def test_validasi_isi_pesan(self):
        for salah in ('', '   ', '\n\n', 'x' * 1001, 123, None, ['a'], {'a': 1}):
            self.assertEqual(self.req('POST', '/chat', {'isi': salah}, self.bud)[0], 400, repr(salah)[:30])
        self.assertEqual(self.req('POST', '/chat', {'isi': 'x' * 1000}, self.bud)[0], 201)
        s, j = self.req('POST', '/chat', {'isi': 'a\x00b\u202ec\u200bd\r\n\r\n\r\n\r\ne'}, self.bud)      # karakter kontrol & bidi dibuang, baris kosong dirapikan
        self.assertEqual(j['data']['isi'], 'abcd\n\ne')
        s, j = self.req('POST', '/chat', {'isi': '<script>alert(1)</script><img src=x onerror=alert(1)>'}, self.bud)
        self.assertEqual(j['data']['isi'], '<script>alert(1)</script><img src=x onerror=alert(1)>')            # disimpan apa adanya; keamanan di sisi tampilan (textContent)

    def test_batas_kirim_per_menit_dan_pesan_beruntun(self):
        config.cfg['LAJU_CHAT'] = 5
        kode = [self.req('POST', '/chat', {'isi': f'p{i}'}, self.bud)[0] for i in range(7)]
        self.assertEqual(kode, [201] * 5 + [429] * 2)
        self.assertEqual(self.req('POST', '/chat', {'isi': 'siti'}, self.sit)[0], 201)                         # batas per akun: Siti tidak ikut terblokir
        from app import security; security.reset_laju(); config.cfg.update(LAJU_CHAT=100, CHAT_MAKS_BERUNTUN=6)
        self.assertEqual(self.req('POST', '/chat', {'isi': 'ke-6'}, self.bud)[0], 201)                        # total tanpa balasan: 5 + 1 = 6
        s, j = self.req('POST', '/chat', {'isi': 'ke-7'}, self.bud); self.assertEqual(s, 429); self.assertIn('belum membalas', j['error'])
        self.req('POST', f"/admin/chat/{self.uid('budi_santoso')}", {'isi': 'Maaf baru balas'}, self.adm)
        self.assertEqual(self.req('POST', '/chat', {'isi': 'terima kasih'}, self.bud)[0], 201)                # admin membalas -> hitungan mulai ulang

    def test_halaman_lama_dan_parameter_aneh(self):
        for i in range(60): self.sql('INSERT INTO chat_pesan (user_id,dari,isi,dibuat,dibaca) VALUES (%s,%s,%s,%s,1)', (self.uid('budi_santoso'), 'customer', f'm{i}', 1000 + i))
        s, j = self.req('GET', '/chat', tok=self.bud); d = j['data']; self.assertEqual((len(d['pesan']), d['adaLagi'], d['pesan'][-1]['isi']), (50, True, 'm59'))
        s, j = self.req('GET', f"/chat?sebelum={d['pesan'][0]['id']}", tok=self.bud); self.assertEqual((len(j['data']['pesan']), j['data']['adaLagi']), (10, False))
        for aneh in ('abc', '-1', '1; DROP TABLE pengguna', '9' * 30, '1.5'): self.assertEqual(self.req('GET', f'/chat?sejak={aneh}', tok=self.bud)[0], 200, aneh)
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM pengguna')[0]['n'], 3)

    def test_pesan_ikut_terhapus_bersama_akun_dan_audit_admin(self):
        self.req('POST', '/chat', {'isi': 'Halo'}, self.bud); self.sql('DELETE FROM pengguna WHERE username=%s', ('budi_santoso',))
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM chat_pesan')[0]['n'], 0)

    def test_komponen_chat_tidak_memakai_innerhtml_untuk_isi_pesan(self):
        js = open(os.path.join(ROOT, 'frontend', 'shared', 'chat.js'), encoding='utf-8').read()
        bagian = [l for l in js.split('\n') if re.search(r'\.innerHTML\s*[+]?=', l)]
        self.assertEqual(len(bagian), 1); self.assertNotIn('${', bagian[0]); self.assertNotIn('m.isi', bagian[0])      # hanya kerangka statis
        self.assertNotIn('insertAdjacentHTML', js); self.assertNotIn('outerHTML', js)


class TestPerforma(Dasar):
    def test_gzip_hanya_bila_diminta_dan_sah(self):
        r = self.c.get('/api/produk', headers={'Accept-Encoding': 'identity'}); self.assertNotIn('Content-Encoding', r.headers)
        r = self.c.get('/api/produk', headers={'Accept-Encoding': 'gzip'}); self.assertEqual(r.headers.get('Content-Encoding'), 'gzip')
        import gzip, json; self.assertEqual(len(json.loads(r.content)['data']), 12); self.assertIn('Accept-Encoding', r.headers['Vary'])
        r = self.c.get('/shared/core.js', headers={'Accept-Encoding': 'gzip'}); self.assertEqual(r.headers.get('Content-Encoding'), 'gzip')
        self.assertIn('const Api', r.content.decode())
        r2 = self.c.get('/shared/core.js', headers={'Accept-Encoding': 'gzip'}); self.assertEqual(r.content, r2.content)     # versi kompresi di-cache memori
        r = self.c.get('/media/produk/' + 'a' * 32 + '.jpg', headers={'Accept-Encoding': 'gzip'}); self.assertEqual(r.status_code, 404)

    def test_aset_berversi_di_cache_selamanya_html_selalu_segar(self):
        h = self.c.get('/').text
        self.assertRegex(h, r'src="/shared/core\.js\?v=\d+"'); self.assertRegex(h, r'src="/landing/script\.js\?v=\d+"'); self.assertRegex(h, r'href="/landing/style\.css\?v=\d+"')
        self.assertEqual(self.c.get('/').headers['Cache-Control'], 'no-cache')
        self.assertIn('immutable', self.c.get('/shared/core.js?v=123').headers['Cache-Control'])
        self.assertEqual(self.c.get('/shared/core.js').headers['Cache-Control'], 'no-cache')
        self.assertEqual(self.c.get('/shared/chat.js?v=1').status_code, 200)

    def test_tailwind_build_otomatis_menggantikan_cdn(self):
        asal = config.cfg['FRONTEND_DIR']; tmp = os.path.join(TMP, 'fe_' + self.id()); shutil.copytree(asal, tmp)
        app2 = create_app({'TESTING': True, 'FRONTEND_DIR': tmp, 'UPLOAD_DIR': self.up}); c2 = TestClient(app2, follow_redirects=False)
        h = c2.get('/masuk').text; self.assertIn('cdn.tailwindcss.com', h); self.assertIn("'unsafe-eval'", h)    # belum di-build: pakai CDN
        open(os.path.join(tmp, 'shared', 'app.css'), 'w').write('.x{color:red}')
        for hal in ('/', '/masuk', '/daftar', '/dashboard', '/admin', '/produk/1'):
            h = c2.get(hal).text
            self.assertNotIn('cdn.tailwindcss.com', h, hal); self.assertNotIn('unsafe-eval', h, hal); self.assertNotIn('/shared/tailwind.js', h, hal)
            self.assertRegex(h, r'href="/shared/app\.css\?v=\d+"', hal)

    def test_header_waktu_dan_log_request_lambat(self):
        r = self.c.get('/api/kesehatan'); self.assertRegex(r.headers['Server-Timing'], r'^app;dur=\d+$')
        config.cfg['LAMBAT_MS'] = -1
        with self.assertLogs('sawitku', 'WARNING') as cm: self.c.get('/api/produk')
        self.assertTrue(any('LAMBAT GET /api/produk' in l for l in cm.output))

    def test_sesi_tidak_menulis_db_di_setiap_request(self):
        tok = self.login('budi_santoso', 'Budi12345'); exp = lambda: self.sql('SELECT kedaluwarsa FROM sesi')[0]['kedaluwarsa']
        sebelum = exp(); self.req('GET', '/auth/saya', tok=tok); self.assertEqual(exp(), sebelum)              # sisa masih > separuh: tidak diperpanjang
        self.sql('UPDATE sesi SET kedaluwarsa=%s', (int(__import__('time').time() * 1000) + 5 * 60000,))        # sisa 5 menit < separuh (10)
        self.req('GET', '/auth/saya', tok=tok); self.assertGreater(exp(), int(__import__('time').time() * 1000) + 15 * 60000)


class TestFrontend(Dasar):
    """Frontend statis dilayani Flask dari origin yang sama dengan API, lewat URL pendek."""
    def test_url_pendek_semua_halaman(self):
        for url in ('/', '/masuk', '/daftar', '/dashboard', '/admin', '/produk/3', '/bayar/1'):
            r = self.c.get(url); self.assertEqual(r.status_code, 200, url)
            self.assertIn(b'/shared/core.js', r.content); self.assertNotIn(b'../', r.content); self.assertNotIn(b'data.js', r.content); 
        self.assertEqual(self.c.get('/produk').headers['Location'], '/#katalog')
        for aset in ('/shared/core.js', '/login/script.js', '/shared/base.css', '/landing/script.js'):
            r = self.c.get(aset); self.assertEqual(r.status_code, 200, aset); 

    def test_alamat_lama_dialihkan_ke_url_pendek(self):
        for lama, baru in (('/landing/index.html', '/'), ('/landing/', '/'), ('/landing', '/'), ('/login/index.html', '/masuk'), ('/register/index.html', '/daftar'),
                           ('/customer/index.html', '/dashboard'), ('/admin/index.html', '/admin'), ('/produk/index.html?id=5', '/produk/5'), ('/login/index.html?next=customer', '/masuk?next=customer')):
            r = self.c.get(lama); self.assertEqual((r.status_code, r.headers['Location']), (301, baru), lama)

    def test_html_tidak_bisa_diakses_lewat_path_folder(self):
        for p in ('/login/style.css.map', '/shared/', '/shared', '/app/config.py', '/schema.sql'):
            self.assertEqual(self.c.get(p).status_code, 404, p)

    def test_login_tanpa_akun_demo_dan_kontak_langsung(self):
        r = self.c.get('/masuk'); self.assertNotIn(b'Akun demo', r.content); self.assertNotIn(b'Budi12345', r.content); self.assertNotIn(b'Admin12345', r.content); 
        r = self.c.get('/landing/script.js'); self.assertIn(b'https://wa.me/', r.content); self.assertIn(b'mailto:', r.content); 

    def test_data_dummy_hilang_dan_file_lain_tidak_bocor(self):
        self.assertEqual(self.c.get('/shared/data.js').status_code, 404)
        for p in ('/%2e%2e/app/config.py', '/shared/..%2f..%2fapp%2fconfig.py', '/../schema.sql'):
            self.assertEqual(self.c.get(p).status_code, 404, p)
        self.assertEqual(self.c.get('/api/').json(), {'error': 'Data tidak ditemukan.'})
        self.assertEqual(self.c.get('/media/x').status_code, 404)

    def test_alur_frontend_lewat_satu_origin(self):
        """Simulasi yang dilakukan core.js: masuk -> Bearer -> data; gambar unggahan berupa path relatif /media/."""
        t = self.login('budi_santoso', 'Budi12345')
        s, j = self.req('GET', '/keranjang', tok=t); self.assertEqual((s, j['data']), (200, []))
        o = self.beli(t); self.assertEqual(self.bukti(o['id'], {'bukti': png_url()}, t)[0], 200)
        u = self.req('GET', '/pesanan/saya', tok=t)[1]['data'][0]['bukti']; self.assertTrue(u.startswith('/media/bukti/'))


class Keamanan(Dasar):
    """Regresi untuk celah yang diperbaiki pada audit keamanan."""
    prod = TestAdmin.prod

    def test_tidak_bisa_hapus_berkas_milik_orang_lain_lewat_profil(self):
        adm, t = self.login('admin', 'Admin12345'), self.login('budi_santoso', 'Budi12345')
        s, j = self.req('POST', '/admin/produk', self.prod(gambar=png_url()), adm); p = j['data']
        f = p['gambar']
        # menunjuk foto produk sebagai foto profil harus ditolak ...
        s, j = self.req('PUT', '/profil', {'username': 'budi_santoso', 'email': 'budi@mail.com', 'foto': p['gambar']}, t)
        self.assertEqual(s, 400)
        # ... dan mengganti foto profil tidak boleh menyentuh berkas produk
        self.req('PUT', '/profil', {'username': 'budi_santoso', 'email': 'budi@mail.com', 'foto': png_url()}, t)
        self.assertTrue(self.media(f) is not None)

    def test_foto_profil_tolak_url_eksternal(self):
        t = self.login('budi_santoso', 'Budi12345')
        s, _ = self.req('PUT', '/profil', {'username': 'budi_santoso', 'email': 'budi@mail.com', 'foto': 'https://evil.example/x.png'}, t)
        self.assertEqual(s, 400)

    def test_url_gambar_produk_tolak_karakter_injeksi(self):
        adm = self.login('admin', 'Admin12345')
        for u in ('https://a.example/x"onerror="alert(1)', 'https://a.example/<b>', "https://a.example/x'y"):
            self.assertEqual(self.req('POST', '/admin/produk', self.prod(gambar=u), adm)[0], 400, u)
        self.assertEqual(self.req('POST', '/admin/produk', self.prod(gambar='https://a.example/ok.jpg'), adm)[0], 201)

    def test_gambar_riwayat_pesanan_tidak_terhapus_saat_produk_dihapus(self):
        adm, t = self.login('admin', 'Admin12345'), self.login('budi_santoso', 'Budi12345')
        s, j = self.req('POST', '/admin/produk', self.prod(gambar=png_url(), stok=5), adm); p = j['data']
        f = p['gambar']
        self.req('POST', '/keranjang', {'produkId': p['id'], 'qty': 1}, t); self.assertEqual(self.req('POST', '/checkout', ALAMAT, t)[0], 201)
        self.assertEqual(self.req('DELETE', f"/admin/produk/{p['id']}", tok=adm)[0], 200)
        self.assertTrue(self.media(f) is not None)        # masih dirujuk riwayat pesanan

    def test_gambar_dimensi_raksasa_ditolak_dan_exif_dihormati(self):
        t = self.login('budi_santoso', 'Budi12345'); o = self.beli(t)
        s, j = self.bukti(o['id'], {'bukti': png_url(6000, 5000)}, t)
        self.assertEqual((s, j['error']), (400, 'Dimensi gambar terlalu besar.'))
        b = io.BytesIO(); im = Image.new('RGB', (60, 20), 'red'); ex = Image.Exif(); ex[0x0112] = 6; im.save(b, 'JPEG', exif=ex)
        url = 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()
        s, j = self.req('PUT', '/profil', {'username': 'budi_santoso', 'email': 'budi@mail.com', 'foto': url}, t)
        with Image.open(self.media(j['data']['foto'])) as r: self.assertEqual(r.size, (20, 60))

    def test_batas_laju_kontak_dan_daftar(self):
        m = {'nama': 'Tono', 'email': 'tono@mail.com', 'jenis': 'Pertanyaan', 'isi': 'Apakah ada pengiriman luar kota?'}
        kode = [self.req('POST', '/kontak', m)[0] for _ in range(7)]
        self.assertEqual(kode, [201] * 5 + [429] * 2)
        kode = [self.req('POST', '/auth/daftar', {'username': f'user_{i}', 'email': f'u{i}@mail.com', 'password': 'Abcdef123'})[0] for i in range(12)]
        self.assertEqual(kode, [200] * 10 + [429] * 2)

    def test_pembatas_login_per_ip_dan_kunci_tak_bisa_ditabrak(self):
        for i in range(20):        # 20 username berbeda dari IP yang sama -> IP diblokir setelah 5*4 gagal
            self.req('POST', '/auth/masuk', {'username': f'orang_{i}', 'password': 'salah123'})
        s, j = self.req('POST', '/auth/masuk', {'username': 'budi_santoso', 'password': 'Budi12345'}); self.assertEqual(s, 429)

    def test_batas_pesanan_menunggu_bayar(self):
        t = self.login('budi_santoso', 'Budi12345')
        config.cfg['MAKS_PESANAN_TERTUNDA'] = 2
        for pid in (1, 2, 3):
            self.req('POST', '/keranjang', {'produkId': pid, 'qty': 1}, t)
            s, j = self.req('POST', '/checkout', ALAMAT, t)
        self.assertEqual(s, 409)

    def test_path_traversal_dan_header_keamanan(self):
        for u in ('/..%2f..%2fapp/config.py', '/%2e%2e/app/config.py', '/landing/../../app/config.py'):
            self.assertIn(self.c.get(u).status_code, (301, 308, 404), u)
        r = self.c.get('/')
        self.assertEqual(r.headers['X-Frame-Options'], 'DENY'); self.assertIn("frame-ancestors 'none'", r.headers['Content-Security-Policy'])
        


class TestAlamat(Dasar):
    """Fitur alamat pengiriman: validasi, salinan di pesanan, profil, dan tampilan admin."""

    def isi_keranjang(self, t, pid=3, qty=1): self.req('POST', '/keranjang', {'produkId': pid, 'qty': qty}, t)

    def test_checkout_tanpa_atau_dengan_alamat_tidak_valid_ditolak(self):
        t = self.login('budi_santoso', 'Budi12345'); self.isi_keranjang(t)
        n0 = self.sql('SELECT COUNT(*) AS n FROM pesanan WHERE user_id=2')[0]['n']
        self.assertEqual(self.req('POST', '/checkout', tok=t)[0], 400)                     # tanpa body
        for k, v in (('telepon', '12345'), ('telepon', '021555555'), ('kodePos', '4016'), ('kodePos', 'abcde'),
                     ('alamat', 'pendek'), ('kota', ''), ('penerima', 'Bu')):
            s, j = self.req('POST', '/checkout', {**ALAMAT, k: v}, t); self.assertEqual(s, 400, (k, v, j))
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM pesanan WHERE user_id=2')[0]['n'], n0)  # tak ada pesanan setengah jadi
        self.assertEqual(self.req('GET', '/keranjang', tok=t)[1]['data'][0]['qty'], 1)              # keranjang utuh

    def test_alamat_tersimpan_sebagai_salinan_dan_telepon_dinormalkan(self):
        t = self.login('budi_santoso', 'Budi12345'); self.isi_keranjang(t)
        s, j = self.req('POST', '/checkout', {**ALAMAT, 'telepon': '+62 812-3456-7801'}, t); self.assertEqual(s, 201, j)
        self.assertEqual(j['data']['pengiriman'], {'penerima': 'Budi Santoso', 'telepon': '+6281234567801', 'alamat': ALAMAT['alamat'], 'kota': 'Kota Bandung', 'kodePos': '40162'})
        # mengganti alamat profil tidak mengubah pesanan lama
        self.req('PUT', '/profil', {'username': 'budi_santoso', 'email': 'budi@mail.com', 'telepon': '081111111111', 'alamat': 'Jl. Baru No. 99 Medan', 'kota': 'Medan', 'kodePos': '20111'}, t)
        lama = [o for o in self.req('GET', '/pesanan/saya', tok=t)[1]['data'] if o['id'] == j['data']['id']][0]
        self.assertEqual(lama['pengiriman']['kota'], 'Kota Bandung')

    def test_simpan_sebagai_alamat_utama(self):
        t = self.login('siti_aulia', 'Siti12345'); self.req('DELETE', '/keranjang/3', tok=t)
        self.isi_keranjang(t, 4)
        self.req('POST', '/checkout', {**ALAMAT, 'penerima': 'Siti A', 'kota': 'Kota Medan', 'simpan': True}, t)
        u = self.req('GET', '/auth/saya', tok=t)[1]['data']
        self.assertEqual((u['kota'], u['kodePos'], u['telepon']), ('Kota Medan', '40162', '081234567801'))

    def test_profil_alamat_validasi_ubah_dan_hapus(self):
        t = self.login('budi_santoso', 'Budi12345'); dasar = {'username': 'budi_santoso', 'email': 'budi@mail.com'}
        a = {'telepon': '081234567899', 'alamat': 'Jl. Sawit Raya No. 5', 'kota': 'Pekanbaru', 'kodePos': '28111'}
        self.assertEqual(self.req('PUT', '/profil', {**dasar, **a, 'kodePos': '1'}, t)[0], 400)          # sebagian tidak valid -> ditolak utuh
        s, j = self.req('PUT', '/profil', {**dasar, **a}, t); self.assertEqual((s, j['data']['kota'], j['data']['kodePos']), (200, 'Pekanbaru', '28111'))
        s, j = self.req('PUT', '/profil', dasar, t); self.assertEqual(j['data']['kota'], 'Pekanbaru')    # tanpa kunci alamat = tidak berubah
        s, j = self.req('PUT', '/profil', {**dasar, 'telepon': '', 'alamat': '', 'kota': '', 'kodePos': ''}, t)
        self.assertEqual((j['data']['alamat'], j['data']['telepon']), ('', ''))                         # semua kosong = dihapus

    def test_admin_melihat_alamat_dan_pembeli_lain_tidak(self):
        adm, t, siti = self.login('admin', 'Admin12345'), self.login('budi_santoso', 'Budi12345'), self.login('siti_aulia', 'Siti12345')
        self.isi_keranjang(t); o = self.req('POST', '/checkout', ALAMAT, t)[1]['data']
        a = [x for x in self.req('GET', '/admin/pesanan', tok=adm)[1]['data'] if x['id'] == o['id']][0]
        self.assertEqual(a['pengiriman']['alamat'], ALAMAT['alamat'])
        self.assertNotIn(o['id'], [x['id'] for x in self.req('GET', '/pesanan/saya', tok=siti)[1]['data']])

    def test_alamat_berisi_html_disimpan_apa_adanya_dan_karakter_kontrol_dibuang(self):
        t = self.login('budi_santoso', 'Budi12345'); self.isi_keranjang(t)
        s, j = self.req('POST', '/checkout', {**ALAMAT, 'alamat': 'Jl. <b>Mawar</b> 12\x00\n\nBlok A'}, t); self.assertEqual(s, 201, j)
        self.assertEqual(j['data']['pengiriman']['alamat'], 'Jl. <b>Mawar</b> 12 Blok A')   # pelolosan HTML dilakukan frontend (K.esc)


class TestJwt(Dasar):
    """JWT: token bertanda tangan, dicabut di server saat keluar, dipakai bersama semua tab, diperpanjang saat aktif."""
    def test_token_berbentuk_jwt_dan_klaim(self):
        import jwt
        tok = self.login('budi_santoso', 'Budi12345'); k = jwt.decode(tok, 'r' * 40, algorithms=['HS256'], issuer='sawitku')
        self.assertEqual((k['role'], k['sub']), ('customer', '2')); self.assertTrue(k['jti']); self.assertGreater(k['exp'], k['iat'])
        self.assertEqual(self.req('GET', '/auth/saya', tok=tok)[1]['data']['username'], 'budi_santoso')

    def test_token_palsu_dimodifikasi_atau_alg_none_ditolak(self):
        import jwt, time
        tok = self.login('budi_santoso', 'Budi12345'); k = jwt.decode(tok, 'r' * 40, algorithms=['HS256'], issuer='sawitku')
        bag = tok.split('.')
        for palsu in (jwt.encode({**k, 'role': 'admin'}, 'kunci-lain', 'HS256'), jwt.encode(k, None, 'none'), bag[0] + '.' + bag[1] + '.xxxx', 'a.b.c', 'sampah',
                      jwt.encode({**k, 'exp': int(time.time()) - 10}, 'r' * 40, 'HS256'), jwt.encode({**k, 'iss': 'lain'}, 'r' * 40, 'HS256')):
            self.assertEqual(self.req('GET', '/auth/saya', tok=palsu)[0], 401, palsu[:30])
        # token sah secara tanda tangan tetapi jti tak terdaftar di server -> tolak
        self.assertEqual(self.req('GET', '/auth/saya', tok=jwt.encode({**k, 'jti': 'tidak-ada'}, 'r' * 40, 'HS256'))[0], 401)

    def test_peran_diambil_dari_database_bukan_dari_klaim(self):
        import jwt
        tok = self.login('budi_santoso', 'Budi12345'); k = jwt.decode(tok, 'r' * 40, algorithms=['HS256'], issuer='sawitku')
        sama_jti_admin = jwt.encode({**k, 'role': 'admin'}, 'r' * 40, 'HS256')               # penyerang yang tahu rahasia pun tak bisa naik peran
        self.assertEqual(self.req('GET', '/admin/pesanan', tok=sama_jti_admin)[0], 403)

    def test_keluar_mencabut_token_di_server_dan_dua_tab_memakai_token_sama(self):
        tok = self.login('budi_santoso', 'Budi12345')
        for _tab in range(2): self.assertEqual(self.req('GET', '/auth/saya', tok=tok)[0], 200)   # tab baru/duplikat: token yang sama, tetap masuk
        self.assertEqual(self.req('POST', '/auth/keluar', tok=tok)[0], 200)
        self.assertEqual(self.req('GET', '/auth/saya', tok=tok)[0], 401)                        # keluar dari satu tab = keluar di semua
        tok2 = self.login('budi_santoso', 'Budi12345'); self.assertNotEqual(tok, tok2)           # masuk lagi = sesi baru

    def test_token_diperpanjang_lewat_header_saat_hampir_habis(self):
        import time
        tok = self.login('budi_santoso', 'Budi12345')
        r = self.c.get('/api/auth/saya', headers={'Authorization': f'Bearer {tok}'}); self.assertNotIn('x-token-baru', r.headers)
        self.sql('UPDATE sesi SET kedaluwarsa=%s', (int(time.time() * 1000) + 5 * 60000,))
        r = self.c.get('/api/auth/saya', headers={'Authorization': f'Bearer {tok}'}); baru = r.headers.get('x-token-baru'); self.assertTrue(baru)
        self.assertEqual(self.req('GET', '/auth/saya', tok=baru)[0], 200)

    def test_dokumentasi_api_otomatis(self):
        r = self.c.get('/api/docs'); self.assertEqual(r.status_code, 200); self.assertIn('/api/auth/masuk', r.text)
        paths = self.c.get('/api/openapi.json').json()['paths']
        self.assertIn('/api/produk', paths); self.assertIn('/api/produk/{pid}', paths); self.assertIn('post', paths['/api/auth/masuk'])
        self.assertIn('security', paths['/api/admin/pesanan']['get']); self.assertNotIn('security', paths['/api/produk']['get'])


class TestTerimaBarang(Dasar):
    """Admin menandai barang sampai; pembeli konfirmasi (foto opsional) atau selesai otomatis setelah 24 jam."""
    def dikirim(self):
        t, adm = self.login('budi_santoso', 'Budi12345'), self.login('admin', 'Admin12345'); o = self.beli(t); oid = o['id']
        self.bukti(oid, {'bukti': png_url()}, t); self.req('POST', f'/admin/pesanan/{oid}/verifikasi', {'setuju': True}, adm)
        self.req('POST', f'/admin/pesanan/{oid}/kirim', RESI, adm); return t, adm, oid

    def ambil(self, t, oid): return [x for x in self.req('GET', '/pesanan/saya', tok=t)[1]['data'] if x['id'] == oid][0]

    def test_konfirmasi_dengan_foto_opsional(self):
        t, adm, oid = self.dikirim()
        self.assertEqual(self.req('POST', f'/pesanan/{oid}/terima', {'foto': 'https://x.com/a.png'}, t)[0], 400)    # foto harus unggahan
        self.assertEqual(self.req('POST', f'/pesanan/{oid}/terima', {'foto': 'data:text/html;base64,PGI+'}, t)[0], 400)
        self.assertEqual(self.ambil(t, oid)['status'], 'dikirim')
        self.assertEqual(self.req('POST', f'/pesanan/{oid}/terima', {'foto': png_url()}, t)[0], 200)
        o = self.ambil(t, oid); self.assertEqual(o['status'], 'selesai'); self.assertRegex(o['fotoTerima'], r'^/media/terima/[0-9a-f]{32}\.jpg$'); self.assertFalse(o['otomatis'])
        self.assertEqual(self.c.get(o['fotoTerima']).status_code, 200)

    def test_konfirmasi_tanpa_foto_dan_hanya_pemilik(self):
        t, adm, oid = self.dikirim(); siti = self.login('siti_aulia', 'Siti12345')
        self.assertEqual(self.req('POST', f'/pesanan/{oid}/terima', tok=siti)[0], 404)
        self.assertEqual(self.req('POST', f'/pesanan/{oid}/terima', tok=t)[0], 200)          # tanpa body & tanpa foto
        self.assertIsNone(self.ambil(t, oid)['fotoTerima']); self.assertEqual(self.req('POST', f'/pesanan/{oid}/terima', tok=t)[0], 409)

    def test_admin_tandai_sampai_dan_selesai_otomatis_setelah_24_jam(self):
        import time
        t, adm, oid = self.dikirim()
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/sampai', tok=t)[0], 403)
        self.assertIsNone(self.ambil(t, oid)['batasTerima'])
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/sampai', tok=adm)[0], 200)
        self.assertEqual(self.req('POST', f'/admin/pesanan/{oid}/sampai', tok=adm)[0], 409)  # tidak bisa dua kali
        o = self.ambil(t, oid); self.assertEqual(o['status'], 'dikirim'); self.assertTrue(o['batasTerima'])
        from app import services
        services.sapu(dbmod.connect(), paksa=True)
        self.assertEqual(self.ambil(t, oid)['status'], 'dikirim')                           # belum 24 jam
        self.sql('UPDATE pesanan SET t_sampai=%s WHERE id=%s', (int(time.time() * 1000) - 25 * 3600000, oid))
        d = sqlite_db(self.dbfile); services.sapu(d, paksa=True); d.close()
        o = self.ambil(t, oid); self.assertEqual((o['status'], bool(o['otomatis'])), ('selesai', True))
        self.assertEqual(self.req('POST', '/ulasan', {'produkId': 3, 'rating': 5, 'teks': 'Selesai otomatis, ulasan boleh.'}, t)[0], 201)

    def test_sampai_hanya_untuk_pesanan_dikirim(self):
        t, adm = self.login('budi_santoso', 'Budi12345'), self.login('admin', 'Admin12345'); o = self.beli(t)
        self.assertEqual(self.req('POST', f"/admin/pesanan/{o['id']}/sampai", tok=adm)[0], 409)
        self.assertEqual(self.req('POST', '/admin/pesanan/9999/sampai', tok=adm)[0], 409)


class TestRating(Dasar):
    def test_rating_dari_ulasan_1_sampai_5_dan_0_bila_belum_ada(self):
        adm = self.login('admin', 'Admin12345')
        s, j = self.req('POST', '/admin/produk', TestAdmin.prod(None), adm); pid = j['data']['id']
        p = self.req('GET', f'/produk/{pid}')[1]['data']; self.assertEqual((p['rating'], p['jumlahUlasan']), (0, 0))
        for r in (0, 6, -1, 'x', None): 
            self.assertEqual(self.req('POST', '/ulasan', {'produkId': 3, 'rating': r, 'teks': 'Rating tidak sah ini.'}, self.login('siti_aulia', 'Siti12345'))[0], 400, r)
        semua = [x for x in self.req('GET', '/produk')[1]['data']]; self.assertTrue(all(0 <= x['rating'] <= 5 for x in semua))
        self.assertTrue(any(x['jumlahUlasan'] for x in semua))
        n = self.sql('SELECT COUNT(*) AS n FROM ulasan')[0]['n']; self.assertEqual(n, 15)


class TestPembayaranMetode(Dasar):
    def test_daftar_metode_publik_dan_checkout_wajib_metode(self):
        j = self.req('GET', '/pembayaran/metode')[1]['data']; self.assertIn('qris', [m['kode'] for m in j['metode']] if isinstance(j, dict) else [m['kode'] for m in j])
        t = self.login('budi_santoso', 'Budi12345'); self.req('POST', '/keranjang', {'produkId': 3, 'qty': 1}, t)
        sa = {k: v for k, v in ALAMAT.items() if k != 'metode'}
        self.assertEqual(self.req('POST', '/checkout', sa, t)[0], 400)
        self.assertEqual(self.req('POST', '/checkout', {**sa, 'metode': 'bitcoin'}, t)[0], 400)
        s, j = self.req('POST', '/checkout', {**sa, 'metode': 'bca'}, t); self.assertEqual((s, j['data']['metode']), (201, 'bca'))

    def test_batal_membatalkan_tagihan_midtrans(self):
        t = self.login('budi_santoso', 'Budi12345'); o = self.beli(t); self.tagihan(o['id'], t)
        self.assertEqual(self.req('POST', f"/pesanan/{o['id']}/batal", tok=t)[0], 200)
        self.assertTrue(any(u.endswith('/cancel') for u, _ in self.mid))


class TestStrukturFrontend(Dasar):
    """HTML dan JS dipisah: markup hidup di <template> pada .html, JS hanya mengisi data."""
    HALAMAN = ('landing', 'produk', 'bayar', 'customer', 'admin')

    def baca(self, *p): return open(os.path.join(ROOT, 'frontend', *p), encoding='utf-8').read()

    def test_tiap_halaman_punya_template_dan_js_tidak_menyimpan_markup_besar(self):
        for h in self.HALAMAN:
            html, js = self.baca(h, 'index.html'), self.baca(h, 'script.js')
            self.assertIn('<template id="t-', html, h)
            self.assertLess(len(re.findall(r'<(?:div|article|section|button|tr|li)\b', js)), 4, h + ': markup masih bertebaran di JS')
            self.assertGreater(len(html), 2500, h)

    def test_template_yang_dipakai_js_ada_di_html(self):
        for h in self.HALAMAN + ('shared',):
            js = self.baca(h, 'script.js' if h != 'shared' else 'core.js')
            html = self.baca(h, 'index.html') if h != 'shared' else ''
            for tid in set(re.findall(r"""['"](t-[a-z\-]+)['"]""", js)):
                if h == 'shared': continue                      # id template di core.js dicek lewat halaman pemakainya
                self.assertIn(f'id="{tid}"', html, f'{h}: template {tid} tidak ada')

    def test_ikon_dari_sprite_dan_tanpa_qr_palsu(self):
        sprite = self.baca('shared', 'icons.svg')
        for ik in ('cart', 'star', 'copy', 'camera', 'qr', 'bank'): self.assertIn(f'id="{ik}"', sprite)
        core = self.baca('shared', 'core.js'); self.assertNotIn('const QR', core); self.assertNotIn('const PATH', core)
        self.assertEqual(self.c.get('/shared/icons.svg').status_code, 200)

    def test_sesi_jwt_dua_slot_per_peran_lewat_localstorage(self):
        """Token disimpan per peran (admin/customer) di localStorage: tab baru langsung masuk, satu admin + satu customer per browser."""
        core, login = self.baca('shared', 'core.js'), self.baca('login', 'script.js')
        self.assertIn('localStorage.getItem(k)', core); self.assertNotIn('sessionStorage', core)
        self.assertIn("'tp_sesi_' + peran", core); self.assertIn('X-Token-Baru', core)
        self.assertNotIn('Sesi.beranda', login)          # halaman masuk selalu menampilkan form (tidak dilempar ke dashboard)

    def test_filter_rating_1_sampai_5_dan_bintang_awal_kosong(self):
        html, ul = self.baca('landing', 'index.html'), self.baca('customer', 'script.js')
        for n in range(1, 6): self.assertIn(f'data-rating="{n}"', html)
        self.assertNotIn('4.5 ke atas', html); self.assertIn('let r = 0;', ul)

    def test_halaman_bayar_dilayani_dan_tak_ada_qris_manual(self):
        r = self.c.get('/bayar/7'); self.assertEqual(r.status_code, 200); self.assertIn(b'/bayar/script.js?v=', r.content)
        self.assertEqual(self.c.get('/bayar/script.js').status_code, 200)
        self.assertNotIn('QRIS toko', self.baca('customer', 'script.js') + self.baca('customer', 'index.html'))


class TestLapisanFlask(Dasar):
    """Perilaku lapisan Flask: galat selalu JSON, batas body, CORS preflight, IP di belakang proxy, rollback saat galat tak terduga."""
    def test_galat_http_selalu_json(self):
        r = self.c.request('POST', '/api/produk'); self.assertEqual((r.status_code, r.json()), (405, {'error': 'Metode tidak diizinkan.'}))
        self.assertIn('GET', r.headers['Allow'])
        self.assertEqual(self.c.get('/api/produk/abc').json(), {'error': 'Data tidak ditemukan.'})      # id bukan angka
        self.assertEqual(self.req('GET', '/produk/99999')[0], 404)

    def test_body_bukan_objek_json_ditolak(self):
        adm = self.login('admin', 'Admin12345'); h = {'Authorization': f'Bearer {adm}', 'Content-Type': 'application/json'}
        for isi in ('[1,2]', '"teks"', '123', '', 'null', '{rusak'):
            r = self.c.post('/api/admin/produk', data=isi, headers=h)
            self.assertEqual((r.status_code, r.json()['error']), (400, 'Format data tidak valid.'), isi)
        self.assertEqual(self.c.post('/api/admin/produk', data='{}').status_code, 401)           # tanpa token: 401 lebih dulu

    def test_body_terlalu_besar_413(self):
        config.cfg['MAKS_BODY_MB'] = 1
        r = self.c.post('/api/auth/masuk', data='{"username":"' + 'a' * 1_200_000 + '"}', headers={'Content-Type': 'application/json'})
        self.assertEqual((r.status_code, r.json()), (413, {'error': 'Ukuran data terlalu besar.'}))
        r = self.app.test_client().get('/api/kesehatan', environ_overrides={'CONTENT_LENGTH': '2000000'})      # Content-Length diumumkan besar
        self.assertEqual((r.status_code, r.get_json()), (413, {'error': 'Ukuran data terlalu besar.'}))

    def test_body_chunked_terlalu_besar_413(self):
        """Body tanpa Content-Length (chunked) dipotong Werkzeug di batas; harus tetap dijawab 413, bukan 400 'format salah'."""
        besar = b'{"username":"' + b'a' * (7 * 1048576) + b'"}'
        r = self.app.test_client().post('/api/auth/masuk', input_stream=io.BytesIO(besar), content_type='application/json',
                                        environ_overrides={'wsgi.input_terminated': True})
        self.assertEqual((r.status_code, r.get_json()), (413, {'error': 'Ukuran data terlalu besar.'}))
        kecil = self.app.test_client().post('/api/auth/masuk', input_stream=io.BytesIO(b'{"username":"x","password":"y"}'), content_type='application/json',
                                            environ_overrides={'wsgi.input_terminated': True})
        self.assertEqual(kecil.status_code, 401)          # chunked kecil tetap diproses normal

    def test_cors_preflight(self):
        h = {'Origin': 'http://front.test', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization, content-type'}
        r = self.c.request('OPTIONS', '/api/checkout', headers=h)
        self.assertEqual((r.status_code, r.headers['Access-Control-Allow-Origin']), (200, 'http://front.test'))
        self.assertIn('Authorization', r.headers['Access-Control-Allow-Headers']); self.assertEqual(r.headers['Access-Control-Max-Age'], '600')
        self.assertEqual(self.c.request('OPTIONS', '/api/checkout', headers={**h, 'Origin': 'http://jahat.test'}).status_code, 400)
        self.assertEqual(self.c.request('OPTIONS', '/api/checkout', headers={**h, 'Access-Control-Request-Headers': 'x-aneh'}).status_code, 400)
        r = self.c.get('/api/produk', headers={'Origin': 'http://front.test'}); self.assertEqual(r.headers['Access-Control-Expose-Headers'], 'X-Token-Baru')

    def test_ip_klien_di_belakang_proxy(self):
        app2 = create_app({'TESTING': True, 'JWT_SECRET': 'r' * 40, 'UPLOAD_DIR': self.up})
        app2.add_url_rule('/_ip', 'uji_ip', lambda: dbmod.konteks().ip + '|' + __import__('flask').request.scheme)       # didaftarkan sebelum request pertama
        c2 = TestClient(app2)
        def ip(xff, hops, **kw):
            config.cfg['PROXY_HOPS'] = hops
            return c2.get('/_ip', headers={'X-Forwarded-For': xff, **kw}).text
        self.assertEqual(ip('6.6.6.6', 0), '127.0.0.1|http')                                 # tanpa proxy: header palsu diabaikan
        self.assertEqual(ip('6.6.6.6, 10.0.0.9', 1), '10.0.0.9|http')                        # 1 proxy: entri terakhir (dari proxy)
        self.assertEqual(ip('6.6.6.6, 7.7.7.7, 10.0.0.9', 2), '7.7.7.7|http')                # 2 proxy: entri ke-2 dari kanan, entri palsu di kiri diabaikan
        self.assertEqual(ip('1.1.1.1', 2), '127.0.0.1|http')                                 # entri kurang dari jumlah proxy: pakai alamat koneksi
        self.assertEqual(ip('1.1.1.1', 1, **{'X-Forwarded-Proto': 'https'}), '1.1.1.1|https')

    def test_galat_tak_terduga_json_500_dan_rollback(self):
        import app.routes.customer as cm
        t = self.login('budi_santoso', 'Budi12345'); asli = cm.ok
        def rusak(*a, **k): raise RuntimeError('meledak')
        cm.ok = rusak                                       # `ker_add` sudah menjalankan INSERT keranjang saat ok() dipanggil
        try:
            with self.assertLogs('sawitku', 'ERROR'): s, j = self.req('POST', '/keranjang', {'produkId': 3, 'qty': 1}, t)
        finally: cm.ok = asli
        self.assertEqual((s, j), (500, {'error': 'Terjadi kesalahan pada server.'}))
        self.assertEqual(self.sql('SELECT COUNT(*) AS n FROM keranjang WHERE user_id=2 AND produk_id=3')[0]['n'], 0)     # INSERT ikut dibatalkan
        self.assertEqual(self.req('POST', '/keranjang', {'produkId': 3, 'qty': 1}, t)[0], 201)                           # dan aplikasi tetap sehat

    def test_head_dan_304_aset(self):
        r = self.c.get('/shared/core.js?v=1', headers={'Accept-Encoding': 'identity'}); etag = r.headers['ETag']
        self.assertEqual(self.c.get('/shared/core.js?v=1', headers={'If-None-Match': etag, 'Accept-Encoding': 'identity'}).status_code, 304)
        self.assertEqual(self.c.request('HEAD', '/api/kesehatan').status_code, 200)


if __name__ == '__main__':
    unittest.main()
