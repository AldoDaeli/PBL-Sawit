# SawitKu — Toko Online (Flask + MariaDB)

Frontend (HTML + JS + Tailwind) dan backend **Flask** berjalan dalam satu aplikasi, satu origin (tanpa CORS).
Database MariaDB lewat PyMySQL. Autentikasi **JWT**. Pembayaran **Midtrans** (QRIS dan Virtual Account) dengan **bukti bayar yang wajib diperiksa admin**.

## Daftar isi
1. [Yang berubah di revisi ini](#yang-berubah-di-revisi-ini)
2. [Instalasi dari nol](#instalasi-dari-nol)
3. [Halaman & akun contoh](#halaman--akun-contoh)
4. [JWT & sesi per peran](#jwt--sesi-per-peran)
5. [REST API & dokumentasi otomatis](#rest-api--dokumentasi-otomatis)
6. [Pembayaran Midtrans + bukti bayar](#pembayaran-midtrans--bukti-bayar)
7. [Barang sampai & konfirmasi 24 jam](#barang-sampai--konfirmasi-24-jam)
8. [Rating 1–5](#rating-15)
9. [Struktur kode](#struktur-kode)
10. [Tes](#tes)
11. [Upgrade dari versi lama](#upgrade-dari-versi-lama)
12. [Produksi](#produksi)

## Yang berubah di revisi ini
Backend dimigrasikan dari **FastAPI ke Flask**. Semua endpoint, format respons (`{"data": ...}` / `{"error": "..."}`), skema database, frontend, JWT,
OTP, Midtrans, dan perintah `manage.py` **tidak berubah**: database lama dan frontend lama langsung cocok, tanpa migrasi data.

| Bagian | FastAPI (sebelumnya) | Flask (sekarang) |
|---|---|---|
| Aplikasi | `FastAPI()` + `APIRouter` | application factory `create_app()` + `Blueprint` (`app/routes/`) |
| Server | `uvicorn main:app` | `flask --app main run` (dev), `gunicorn main:app` / `waitress` (produksi) |
| Login/peran (RBAC) | `Depends(wajib('admin'))` | dekorator `@wajib('admin')`; pengguna diteruskan sebagai argumen pertama fungsi |
| Body request | model pydantic | `badan(Kelas)` di `app/schemas.py` (JSON harus objek, selain itu 400 "Format data tidak valid.") |
| Middleware | middleware ASGI | hook Flask `before_request` / `after_request` / `teardown_request` + middleware WSGI untuk IP proxy (`app/middleware.py`) |
| Konteks request | `ContextVar` | `flask.g` |
| CORS, gzip | middleware Starlette | diimplementasikan sendiri di `app/middleware.py` (tanpa pustaka tambahan) |
| Dokumentasi API | Swagger UI otomatis | halaman `/api/docs` (daftar endpoint + hak akses) dan `/api/openapi.json` (OpenAPI 3, bisa diimpor ke Postman) |
| Tes | `starlette.testclient` + `httpx` | `test_client` bawaan Flask (tanpa dependensi tambahan); 105 tes |

Perbedaan kecil yang perlu diketahui: id non-angka di URL (`/api/produk/abc`) dijawab 404 JSON; tanpa token, endpoint terlindungi selalu menjawab 401 lebih dulu
(sebelumnya body JSON rusak menang atas 401); Swagger UI interaktif (tombol "Try it out") diganti halaman daftar endpoint.

## Instalasi dari nol
### 1. Prasyarat
Python 3.10+, MariaDB 10.5+ (atau MySQL 8), Node.js hanya bila ingin membuat CSS Tailwind statis (opsional).

### 2. Pasang proyek
```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Linux / macOS:         source .venv/bin/activate
pip install -r requirements.txt          # untuk menjalankan tes: pip install -r requirements-dev.txt
cp .env.example .env                     # Windows: copy .env.example .env
```

### 3. Buat database dan user
```sql
CREATE DATABASE sawitku CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'sawitku'@'localhost' IDENTIFIED BY 'GantiPasswordIni1';
GRANT ALL PRIVILEGES ON sawitku.* TO 'sawitku'@'localhost';
```
Samakan `DB_*` di `.env` dengan nilai di atas.

### 4. Buat tabel dan akun
```bash
python manage.py init-db                    # membuat tabel dari schema.sql (aman diulang)
# pilih salah satu:
python manage.py buat-admin NAMAADMIN email@kamu.com      # toko sungguhan: password ditanya interaktif
python manage.py seed                                     # data contoh: 12 produk, 3 akun, pesanan & ulasan
python manage.py impor-media                              # (opsional) unduh gambar produk contoh ke database
```

### 5. Jalankan
```bash
flask --app main run --debug --port 5000    # pengembangan (atau: python main.py)
```
Buka `http://localhost:5000`. Dokumentasi API: `http://localhost:5000/api/docs`.

### 6. Midtrans (sandbox)
1. Daftar di Midtrans, buka **Settings → Access Keys**, salin **Server Key** sandbox (`SB-Mid-server-...`).
2. Isi `MIDTRANS_SERVER_KEY` di `.env`, restart server.
3. Di dashboard Midtrans isi **Payment Notification URL** = `https://DOMAINMU/api/midtrans/notifikasi` (opsional, untuk status otomatis; butuh domain publik).
4. Uji bayar dengan simulator Midtrans (<https://simulator.sandbox.midtrans.com>) memakai QR/VA yang tampil di halaman bayar.

Tanpa `MIDTRANS_SERVER_KEY`, checkout tetap membuat pesanan tetapi halaman bayar menampilkan "Pembayaran Midtrans belum diaktifkan".

## Halaman & akun contoh
| Halaman | Alamat |
|---|---|
| Beranda / katalog | `/` |
| Masuk, Daftar (OTP email), Lupa password | `/masuk`, `/daftar`, `/lupa-password` |
| Detail produk | `/produk/<id>` |
| Bayar pesanan | `/bayar/<id pesanan>` |
| Dashboard customer / admin | `/dashboard`, `/admin` |

Perintah `python manage.py seed` mengacak password tiap akun demo dan mencetaknya satu kali di terminal; catat saat itu juga (hanya untuk demo, jangan dipakai di produksi).

## JWT & sesi per peran
- Login (`POST /api/auth/masuk`) mengembalikan token JWT (HS256; klaim `iss`, `sub`, `jti`, `role`, `iat`, `exp`).
- `jti` disimpan (di-hash) di tabel `sesi`, sehingga **keluar benar-benar mencabut token** di server. Peran selalu dibaca dari database, bukan dari klaim token.
- Selama pengguna aktif, server mengirim token baru lewat header `X-Token-Baru`; frontend menggantinya otomatis.
- Frontend menyimpan token di `localStorage` dalam **dua slot terpisah per peran** (`tp_sesi_admin`, `tp_sesi_customer`):
  - Tab baru atau salin link dashboard langsung masuk sesuai peran link itu (tanpa login ulang).
  - Admin dan customer boleh login bersamaan di tab berbeda; slotnya tidak saling menimpa.
  - Satu browser hanya punya **satu admin dan satu customer**. Login ulang pada peran yang sama menggantikan sesi lama (customer1 di tab 1 dan customer2 di tab 2 tidak diizinkan; pakai browser/profil lain).
  - Keluar di satu tab menghapus slot perannya sehingga semua tab peran itu ikut keluar; tab peran lain tidak terpengaruh.
  - Halaman publik (landing, produk) memakai sesi customer bila ada, jika tidak sesi admin. Halaman `/masuk` selalu menampilkan form.
- Batas diam (`SESI_MENIT`, bawaan 20) dihitung dari aktivitas terakhir pada peran itu. Masa berlaku ditentukan server (`exp` + tabel `sesi`), bukan jenis penyimpanan.
- Rahasia penanda tangan: `JWT_SECRET` di `.env`. Kosong = dibuat otomatis di `.jwt_secret` (jangan di-commit). Mengganti rahasia mengeluarkan semua pengguna.
- Catatan: `localStorage` terbaca oleh JavaScript di halaman yang sama, karena itu CSP ketat dipakai dan semua data pengguna di-escape.

## REST API & dokumentasi otomatis
Semua endpoint di bawah `/api`, format `{"data": ...}` atau `{"error": "..."}`. Daftar endpoint beserta hak aksesnya ada di **`/api/docs`**, dan skema OpenAPI 3 di `/api/openapi.json` (impor ke Postman/Insomnia/Swagger Editor untuk mencoba). Endpoint yang butuh login memakai header `Authorization: Bearer <token>`; token didapat dari `POST /api/auth/masuk`.

| Kelompok | Endpoint utama |
|---|---|
| Akun | `POST /auth/masuk`, `/auth/keluar`, `GET /auth/saya`, `POST /auth/daftar` (+`/verifikasi`, `/kirim-ulang`), `POST /auth/lupa` (+`/reset`), `PUT /profil` |
| Katalog | `GET /produk`, `/produk/{id}`, `/produk/{id}/ulasan`, `/kategori`, `/pembayaran/metode` |
| Belanja | `/keranjang`, `/favorit`, `POST /checkout` (wajib `metode`), `GET /pesanan/saya`, `POST /pesanan/{id}/batal` |
| Bayar | `POST /pesanan/{id}/pembayaran`, `/pembayaran/cek`, `POST /pesanan/{id}/bukti`, `POST /midtrans/notifikasi` |
| Terima | `POST /pesanan/{id}/terima` (foto opsional), `GET /lacak` |
| Ulasan | `POST /ulasan` (rating 1–5), `/ulasan/{id}/balas` |
| Admin | `/admin/produk`, `/admin/pesanan` (+`/verifikasi`, `/kirim`, `/sampai`, `/midtrans/cek`), `/admin/pengguna`, `/admin/ulasan`, `/admin/kontak`, `/admin/chat` |
| Chat | `/chat`, `/admin/chat/{uid}` |

## Pembayaran Midtrans + bukti bayar
```
Checkout (pilih metode) → pesanan "menunggu_bayar"
   → /bayar/<id>: backend memanggil Midtrans /v2/charge → tampil QR atau nomor VA
   → pembeli membayar → UNGGAH BUKTI (wajib) → status "menunggu_verifikasi"
   → admin memeriksa bukti + status Midtrans → Setujui (diproses) atau Tolak (pembeli unggah ulang)
```
- Kunci server hanya di backend. Gambar QR hanya diterima dari host Midtrans.
- Status Midtrans (`pending`, `settlement`, ...) hanya **dicatat** (webhook bertanda tangan SHA512 atau tombol "Cek status"). Admin melihatnya sebagai lencana, dan diberi peringatan bila menyetujui padahal Midtrans belum mencatat pembayaran.
- Ganti metode sebelum bukti diunggah: tagihan lama dibatalkan, tagihan baru dibuat.
- Pembatalan pesanan juga membatalkan tagihan Midtrans.

## Barang sampai & konfirmasi 24 jam
1. Admin menandai **dikirim** (kurir + resi), lalu **"Tandai sudah sampai"** saat barang diantar.
2. Pembeli melihat "Barang Tiba" dan batas waktu. Ia menekan **Barang diterima**, boleh melampirkan **foto barang** (opsional).
3. Tanpa konfirmasi dalam `AUTO_TERIMA_JAM` (24 jam) sejak ditandai sampai, pesanan **selesai otomatis** (`otomatis=1`) dan ulasan bisa ditulis.
Foto disimpan di database (folder media `terima`), dikecilkan dan digambar ulang di server.

## Rating 1–5
Rating produk dihitung dari rata-rata ulasan (1–5, satu desimal). Produk tanpa ulasan bernilai `0` dan tampil "Belum ada ulasan" (admin tidak lagi mengisi rating manual). Filter katalog: 1, 2, 3, 4, atau 5 ke atas.

## Struktur kode
```
main.py                  titik masuk WSGI: app = create_app()  →  flask --app main run / gunicorn main:app
manage.py                perintah: init-db, seed, buat-admin, impor-media
app/__init__.py          create_app: blueprint, hook request, penangan galat
app/config.py            konfigurasi dari .env (dict cfg)
app/db.py                koneksi PyMySQL + konteks per-request (flask.g)
app/security.py          JWT, sesi, peran, pembatas laju
app/schemas.py           badan(): pembaca body JSON + kelas Isi (aturan bisnis ada di route/validators)
app/services.py          logika bersama: sapu (batal/selesai otomatis), rating, muat pesanan
app/midtrans.py          klien Midtrans Core API
app/routes/              Blueprint: publik, customer, pesanan, pembayaran, admin, chat
app/web.py               halaman, aset statis, /media
app/docs.py              /api/docs dan /api/openapi.json
frontend/shared/         core.js (Api, Sesi JWT, binder T), base.css, icons.svg, chat.js
frontend/<halaman>/      index.html (markup + <template>) + script.js (data) + style.css
tests/test_api.py        105 tes
```

## Tes
```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v          # memakai SQLite, tidak butuh MariaDB
```

## Upgrade dari versi lama
Database yang sudah ada perlu kolom baru (aman diulang):
```bash
pip install -r requirements.txt
python manage.py init-db        # CREATE TABLE IF NOT EXISTS + ALTER kolom baru (midtrans_status, midtrans_data, t_sampai, foto_terima, otomatis)
```
Lalu hitung ulang rating produk dari ulasan (rating lama yang diisi manual diganti rata-rata ulasan):
```sql
UPDATE produk p SET rating = COALESCE((SELECT ROUND(AVG(rating),1) FROM ulasan u WHERE u.produk_id = p.id), 0);
```
Dari versi FastAPI: jalankan `pip install -r requirements.txt` (FastAPI, uvicorn, dan httpx tidak dipakai lagi; boleh di-`pip uninstall`), lalu ganti `uvicorn main:app` dengan `gunicorn main:app`. Skema database tidak berubah.
Pesanan lama bermetode `qris` manual tetap terbaca; pesanan "menunggu bayar" lama akan membuat tagihan Midtrans saat dibuka di `/bayar/<id>`.

## Produksi
- Jalankan: `pip install gunicorn` lalu `gunicorn -w 2 --threads 4 -b 127.0.0.1:5000 main:app` di belakang Nginx (HTTPS). Di Windows pakai `pip install waitress` lalu `waitress-serve --listen=127.0.0.1:5000 main:app`. Isi `PROXY_HOPS=1`. Jangan memakai `flask run`/`python main.py` di produksi (server pengembangan).
- Isi `JWT_SECRET` dengan nilai acak panjang, `MIDTRANS_SERVER_KEY` kunci produksi dengan `MIDTRANS_PRODUKSI=1`, dan SMTP untuk OTP. Ganti semua password akun contoh.
- Tailwind: halaman memakai Tailwind CDN. Untuk produksi, bangun CSS statis: `npm install && npm run css`. Berkas `frontend/shared/app.css` yang ada otomatis menggantikan CDN (dan `unsafe-eval` dihapus dari CSP).
- Cadangkan database dan folder `uploads/`. Bukti bayar dan foto barang bersifat privat (cache `private`).
