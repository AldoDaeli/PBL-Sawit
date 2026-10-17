# SawitKu — Toko Online (Frontend + Backend Flask + MariaDB)

Satu proyek, satu server: Flask melayani **REST API** (`/api/...`), **gambar unggahan** (`/media/...`), dan **frontend statis** (folder `frontend/`).
Karena semuanya satu origin, tidak perlu CORS.

```
sawitku/
├── app/            backend Flask (routes, keamanan, upload, seed, CLI)
├── frontend/       landing/ produk/ login/ register/ customer/ admin/ shared/   (HTML + JS + CSS)
├── tests/          uji end-to-end (SQLite, tanpa MariaDB) — 76 tes
├── schema.sql      skema database (dibaca oleh perintah init-db)
├── wsgi.py  requirements.txt  .env.example  uploads/
```

## Daftar isi
1. [Fitur](#fitur)
2. [Instalasi dari nol](#instalasi-dari-nol)
3. [Cara database terhubung ke backend](#cara-database-terhubung-ke-backend)
4. [Menjalankan & memakai](#menjalankan--memakai)
5. [Komponen yang diganti / ditambah](#komponen-yang-diganti--ditambah)
6. [Upgrade dari versi lama (database sudah ada)](#upgrade-dari-versi-lama-database-sudah-ada)
7. [Mengganti isi toko](#mengganti-isi-toko)
8. [Peta API](#peta-api)
9. [Aturan bisnis & keamanan](#aturan-bisnis--keamanan)
10. [Catatan produksi](#catatan-produksi)

---

## Fitur

**Pengunjung (tanpa login)**
- Landing page dengan slider, katalog, filter kategori, pencarian, dan produk terlaris.
- Halaman detail produk: spesifikasi, rating, ulasan pembeli, dan produk serupa.
- Daftar akun dengan **verifikasi OTP email** (kode 6 angka), login, dan formulir kontak (pesan masuk ke admin).
- Nomor telepon di landing membuka **WhatsApp** (`wa.me`), alamat email membuka aplikasi email (`mailto:`).
- **Chat pelanggan ↔ admin**: pelanggan yang login chat dengan admin dari bagian Kontak di landing atau menu *Pesan Admin* di dashboard; admin membalas dari *Pesan Masuk* (daftar percakapan + lencana belum dibaca). Pengunjung yang belum login tetap memakai formulir kontak (muncul di tab *Pesan Tamu*, dibalas lewat email).
- **URL pendek**: `/masuk`, `/daftar`, `/dashboard`, `/admin`, `/produk/3` (lihat [Menjalankan & memakai](#menjalankan--memakai)).

**Customer**
- Keranjang (stok divalidasi), favorit, dan checkout.
- **Alamat pengiriman**: form alamat saat checkout (nama penerima, nomor HP, alamat lengkap, kota, kode pos), terisi otomatis dari profil, dan bisa disimpan sebagai alamat utama.
- Pembayaran QRIS (simulasi) dengan unggah bukti bayar; pesanan kedaluwarsa otomatis dibatalkan setelah 24 jam.
- Riwayat pesanan dengan status, alamat tujuan, tombol batalkan, dan "Barang Diterima".
- Ulasan produk (hanya untuk barang yang sudah diterima), statistik belanja, dan profil + foto.

**Admin**
- Ringkasan dan grafik pendapatan.
- Kelola produk (tambah, ubah, hapus, unggah foto atau URL).
- Verifikasi pembayaran (setujui/tolak + alasan), lalu tandai dikirim; **alamat dan nomor HP penerima tampil di kartu pesanan**.
- Kelola pengguna (nonaktifkan akun, sesi langsung putus), balas ulasan, dan baca pesan kontak.

**Keamanan**: lihat [Aturan bisnis & keamanan](#aturan-bisnis--keamanan).

---

## Instalasi dari nol

### 1. Prasyarat
| Perangkat lunak | Versi | Catatan |
|---|---|---|
| Python | 3.10+ | Windows: centang **Add python.exe to PATH** saat instalasi |
| MariaDB | 10.5+ | Atau MySQL 8 |
| Browser | terbaru | Butuh internet (Tailwind CDN, font Google, dan foto produk contoh dari loremflickr) |

### 2. Pasang MariaDB
- **Windows:** unduh installer dari mariadb.org, jalankan, dan **catat password `root`** yang kamu isi. Biarkan opsi "Install as service" aktif supaya MariaDB jalan otomatis.
- **Ubuntu/Debian:** `sudo apt install mariadb-server`, lalu `sudo systemctl enable --now mariadb`.
- **macOS:** `brew install mariadb && brew services start mariadb`.

Pastikan servisnya jalan. Di Windows: `Win + R` → `services.msc` → cari **MariaDB** → status *Running*.

### 3. Pasang proyek
Buka terminal di folder proyek (yang berisi `wsgi.py`):

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\activate
python.exe -m pip install --upgrade pip #bila pip nya masih verisi 26.0.1
pip install -r requirements.txt
copy .env.example .env
```

```bash
# Linux / macOS
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

> Windows: bila `activate` ditolak ("running scripts is disabled"), jalankan sekali
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, lalu ulangi.

### 4. Buat database dan user
Masuk ke MariaDB sebagai root:

- **Windows:** buka **MariaDB Command Prompt** dari Start Menu (sudah mengenal perintah `mysql`), atau pakai HeidiSQL.
  Dari PowerShell biasa, `mysql` biasanya "tidak dikenali"; pakai path lengkap:
  `& "C:\Program Files\MariaDB 11.4\bin\mysql.exe" -u root -p` (sesuaikan nomor versi; di versi baru bisa `mariadb.exe`).
- **Linux/macOS:** `sudo mysql` (atau `mysql -u root -p`).

Jalankan SQL berikut. **Ganti `GantiPasswordIni1`** dengan password pilihanmu (huruf dan angka, hindari tanda `#`). Setiap perintah harus diakhiri `;`.

```sql
CREATE DATABASE sawitku CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'sawitku'@'localhost' IDENTIFIED BY 'GantiPasswordIni1';
GRANT ALL PRIVILEGES ON sawitku.* TO 'sawitku'@'localhost';
EXIT;
```

Nama database dan user bebas, asalkan sama dengan isi `.env` (langkah berikutnya).

### 5. Isi `.env`
Buka `.env` dan samakan dengan langkah 4:

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=sawitku
DB_PASSWORD=GantiPasswordIni1
DB_NAME=sawitku
```

Untuk **OTP register**, isi juga blok `SMTP_*` (lihat [OTP pendaftaran](#otp-pendaftaran-email)). Dibiarkan kosong, kode OTP hanya dicetak di terminal Flask (mode pengembangan). Biarkan variabel lain bernilai bawaan. Isi `PROXY_HOPS=1` **hanya** bila nanti di belakang Nginx. `.env` sudah ada di `.gitignore`; jangan di-commit dan jangan disalin ke `.env.example`.

### 6. Buat tabel dan akun
```bash
flask --app wsgi init-db          # membuat semua tabel dari schema.sql (aman diulang). Harus keluar: "Tabel siap."
```

Lalu pilih **salah satu**:

```bash
# A. Mulai kosong, isi produk sendiri lewat panel admin (disarankan untuk toko sungguhan)
flask --app wsgi buat-admin NAMAADMIN email@kamu.com        # password ditanya interaktif

# B. Isi data contoh: 12 produk, 3 akun demo, pesanan & ulasan (cocok untuk demo/presentasi)
flask --app wsgi seed
```

Perintah `seed` membuat akun demo `admin`, `budi_santoso`, dan `siti_aulia` dengan **password acak** yang hanya ditampilkan sekali di terminal saat `seed` dijalankan (catat saat itu juga). Tidak ada kredensial tetap di README atau halaman login. **Hapus akun demo sebelum dipakai sungguhan.**
Jangan menjalankan `buat-admin admin ...` setelah `seed`, karena username `admin` sudah dipakai.

### 7. Jalankan
```bash
flask --app wsgi run
```
Buka **http://localhost:5000** (otomatis ke landing). **Jangan** membuka file `index.html` langsung atau lewat Live Server, karena frontend memanggil `/api` di origin yang sama.

### 8. Tes (opsional, tidak butuh MariaDB)
```bash
python -m unittest discover -s tests -v       # harus: Ran 76 tests ... OK
```

### Bila ada error
| Pesan di terminal Flask (baris terakhir traceback) | Penyebab | Solusi |
|---|---|---|
| Browser: *"Terjadi kesalahan pada server"* | Detailnya ada di terminal tempat `flask run` berjalan | Baca baris terakhir traceback, lalu cocokkan di bawah |
| `'NoneType' object has no attribute 'connect'` | PyMySQL belum terpasang / venv belum aktif | Aktifkan venv, `pip install -r requirements.txt` |
| `Can't connect to MySQL server` | MariaDB belum jalan / port salah | Start servis MariaDB; cek `DB_HOST`/`DB_PORT` |
| `Access denied for user` | User atau password di `.env` berbeda dengan langkah 4 | Samakan; atau `ALTER USER 'sawitku'@'localhost' IDENTIFIED BY '...';` |
| `Unknown database` | Database belum dibuat | Ulangi langkah 4 |
| `Table '...' doesn't exist` | Tabel belum dibuat | `flask --app wsgi init-db` |
| `Unknown column 'telepon'` / `'alamat'` | Database dibuat dari skema lama | Lihat [Upgrade](#upgrade-dari-versi-lama-database-sudah-ada) |
| `mysql` tidak dikenali (PowerShell) | Folder `bin` MariaDB tidak ada di PATH | Pakai MariaDB Command Prompt atau path lengkap (langkah 4) |
| Halaman tampil tapi katalog kosong | Belum ada produk | Jalankan `seed`, atau tambah lewat panel admin |

---

## Cara database terhubung ke backend

```
.env  ──►  app/config.py  ──►  app/db.py  ──►  MariaDB
(DB_HOST, DB_PORT,         (membaca env,        (PyMySQL: satu koneksi per request;
 DB_USER, DB_PASSWORD,      memberi nilai        commit otomatis bila sukses,
 DB_NAME)                   bawaan)              rollback bila ada galat)
```

1. `app/config.py` memuat `.env` (python-dotenv) ke `Config`. Tanpa `.env`, nilai bawaannya `127.0.0.1:3306`, user `sawitku`, database `sawitku`.
2. `app/db.py` membuat koneksi PyMySQL **lazy**, hanya saat sebuah request butuh database, dan menutupnya di akhir request.
3. Semua query memakai parameter (`%s`), tidak ada penggabungan string, sehingga aman dari SQL injection.
4. **Cek koneksi:** buka `http://localhost:5000/api/kesehatan`. Jika `{"data":{"status":"ok"}}`, backend dan database terhubung. Jika `{"error":"Terjadi kesalahan pada server."}`, lihat terminal Flask.
5. Tabel dibuat dari `schema.sql` oleh `flask --app wsgi init-db`. Perintah ini memakai `CREATE TABLE IF NOT EXISTS`, jadi tidak menghapus data.
6. Tes memakai SQLite dengan `schema.sql` yang sama, sehingga bisa dijalankan tanpa MariaDB.

---

## Menjalankan & memakai

| Halaman | Alamat |
|---|---|
| Landing / katalog | `http://localhost:5000/` |
| Login | `http://localhost:5000/masuk` |
| Daftar (dengan OTP email) | `http://localhost:5000/daftar` |
| Detail produk | `http://localhost:5000/produk/3` (angka = id produk; `/produk` mengarah ke katalog) |
| Dashboard customer | `/dashboard` (otomatis setelah login customer) |
| Dashboard admin | `/admin` (otomatis setelah login admin) |

Alamat lama seperti `/login/index.html` atau `/produk/index.html?id=3` otomatis dialihkan (301) ke URL pendek. Hanya halaman di atas yang bisa dibuka sebagai HTML; berkas `*.js`/`*.css` tetap di `/shared/...` dan `/<halaman>/...` karena dibutuhkan halaman.

### Chat pelanggan ↔ admin
Satu percakapan per pelanggan. Pelanggan melihat percakapannya sendiri; admin melihat dan membalas semua percakapan pelanggan, tetapi **tidak bisa memulai** chat (hanya membalas). Pesan baru muncul otomatis lewat *polling* ringan (hanya meminta pesan yang lebih baru; 4 dtk saat aktif, melambat sampai 15 dtk saat sepi, berhenti saat tab tersembunyi). Ada tanda centang ✓ terkirim / ✓✓ dibaca dan lencana jumlah pesan belum dibaca di menu.

Keamanan chat: wajib login; id pemilik percakapan selalu diambil dari sesi (bukan dari input) sehingga pelanggan tidak bisa membaca chat orang lain; endpoint admin menolak pelanggan (403); isi pesan dibatasi 1–1000 karakter, karakter kontrol/penyamar arah teks dibuang; ditampilkan hanya dengan `textContent` (kebal XSS); batas kirim `LAJU_CHAT` (20/menit per akun, 3× itu per IP), batas pesan beruntun tanpa balasan `CHAT_MAKS_BERUNTUN` (30), balasan admin tercatat di log audit; pesan ikut terhapus bila akun dihapus. Tabel baru `chat_pesan`: jalankan `flask --app wsgi init-db` sekali (aman diulang).

### OTP pendaftaran (email)
Alur: **Daftar** (username, email, password) → server menyimpan pendaftaran *tertunda* (password sudah di-hash, kode OTP disimpan sebagai hash + garam) dan mengirim kode 6 angka ke email → pengguna memasukkan kode → baru akun dibuat. Selama kode belum benar, akun **belum ada** dan tidak bisa login.

| Aturan | Nilai bawaan (`.env`) |
|---|---|
| Masa berlaku kode | 10 menit (`OTP_MENIT`) |
| Salah memasukkan kode | maks 5 kali, lalu harus kirim ulang (`OTP_MAKS_SALAH`) |
| Jeda kirim ulang ke email yang sama | 60 detik (`OTP_JEDA_DETIK`) |
| Maks pengiriman per pendaftaran | 5 (`OTP_MAKS_KIRIM`) |
| Batas verifikasi/kirim ulang per IP | 30 per 10 menit (`LAJU_OTP`) |

Kirim ulang membuat kode baru; kode lama langsung tidak berlaku. **Mengirim email sungguhan** butuh akun SMTP. Contoh Gmail: aktifkan verifikasi 2 langkah, buat *App Password*, lalu isi `.env`:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_MODE=starttls
SMTP_USER=alamatmu@gmail.com
SMTP_PASSWORD=<app password 16 karakter>
```
Tanpa `SMTP_HOST`, pendaftaran dan ganti email **ditolak** (503, "Layanan email belum dikonfigurasi"), supaya produksi tidak diam-diam gagal dan kode tidak bocor ke log. Untuk uji lokal tanpa SMTP, isi `OTP_CETAK_KODE=1` di `.env` (atau jalankan dengan `--debug`): kode dicetak sebagai peringatan `[MODE PENGEMBANGAN ...]` di terminal Flask dan email tidak dikirim. Jangan aktifkan di produksi.

**Ganti email** (menu Profil → tombol *Ganti*): wajib memasukkan password saat ini, lalu kode OTP yang dikirim ke **email baru**. Email lama tetap berlaku sampai kode benar, lalu email lama diberi pemberitahuan. `PUT /api/profil` tidak lagi bisa mengubah email.

**Menambah produk (admin):** login admin → menu **Produk** → **Tambah Produk** → isi nama, kategori, harga (min. Rp1.000), stok, deskripsi, spesifikasi (satu per baris, format `Tinggi: 40 cm`), dan foto (unggah JPG/PNG/WEBP maksimal 2 MB, atau URL `https://`) → simpan.

**Alur pesanan:**
`menunggu_bayar` → (customer unggah bukti) `menunggu_verifikasi` → (admin setujui) `diproses` → (admin kirim) `dikirim` → (customer terima) `selesai`.
Ditolak admin / dibatalkan customer / lewat 24 jam → `dibatalkan` dan stok kembali.

**Checkout:** keranjang → **Checkout** → isi/konfirmasi alamat → **Buat Pesanan** → jendela pembayaran QRIS terbuka.

**Mengganti nama folder proyek:** folder `.venv` menyimpan path absolut, jadi setelah folder diganti namanya, hapus `.venv` dan buat ulang (`python -m venv .venv`, aktifkan, `pip install -r requirements.txt`). Isi `.env` dan database tidak terpengaruh.

---

## Komponen yang diganti / ditambah

Dibandingkan proyek awal (`tanaman-shop` / "Rimba Hijau"):

### A. Rebrand → SawitKu
| Komponen | Perubahan |
|---|---|
| Folder & zip | `tanaman-shop` → `sawitku` |
| `frontend/**` | Semua "Rimba Hijau" → **SawitKu** (judul tab, logo dua warna *Sawit*+*Ku*, footer, teks halaman awal, email kontak `halo@sawitku.id`) |
| `app/config.py`, `.env.example` | Nama database dan user bawaan: `tanaman_shop`/`tanaman` → `sawitku`/`sawitku` |
| `app/seed.py` | Email admin demo → `admin@sawitku.id` |

Isi toko (kategori, 12 produk contoh, teks seperti "Garansi Hidup 7 Hari") **belum diubah** dan masih bertema tanaman. Lihat [Mengganti isi toko](#mengganti-isi-toko).

### B. Fitur baru: alamat pengiriman
| Komponen | Perubahan |
|---|---|
| `schema.sql` | `pengguna` + `telepon`, `alamat`, `kota`, `kode_pos`. `pesanan` + `penerima`, `telepon`, `alamat`, `kota`, `kode_pos` (salinan saat checkout) |
| `app/validators.py` | `baca_alamat()`: nomor HP seluler Indonesia (dinormalkan), kode pos 5 angka, panjang alamat/kota/penerima, karakter kontrol dibuang |
| `POST /api/checkout` | Sekarang **wajib** body alamat; `simpan: true` menyimpannya ke profil |
| `PUT /api/profil` | Menerima `telepon`, `alamat`, `kota`, `kodePos` (semua kosong = hapus) |
| `app/serializers.py` | `user_out` memuat alamat profil; `pesanan_out` memuat `pengiriman` |
| `frontend/customer` | Form alamat di checkout, kolom alamat di profil, "Dikirim ke" di riwayat pesanan |
| `frontend/admin` | Kartu pesanan menampilkan penerima, HP, dan alamat |
| `app/seed.py` | Akun dan pesanan demo punya alamat contoh |

### C. Perbaikan keamanan & bug (hasil audit)
| # | Masalah | Perbaikan |
|---|---|---|
| 1 | Pelanggan bisa memicu penghapusan foto produk / berkas orang lain lewat path `/media/...` | Path media hanya diterima bila milik baris itu sendiri (`uploads.resolve_gambar`) |
| 2 | Menghapus/mengganti gambar produk merusak gambar di riwayat pesanan | Berkas yang masih dirujuk tidak dihapus; penghapusan setelah commit |
| 3 | Pendaftaran & kontak tanpa batas laju (spam) | Batas per IP: `LAJU_DAFTAR`, `LAJU_KONTAK` (10 menit) |
| 4 | Login hanya dibatasi per username | Ditambah batas per IP (4× `MAKS_GAGAL`) |
| 5 | Satu akun bisa menimbun stok tanpa membayar | Maks `MAKS_PESANAN_TERTUNDA` (5) pesanan belum dibayar per akun |
| 6 | Foto profil dari URL eksternal (pelacakan IP admin, kolom 255 karakter) | Foto profil hanya dari unggahan |
| 7 | URL gambar produk boleh berisi tanda kutip / `<>` | Regex URL diperketat |
| 8 | Dimensi gambar raksasa; orientasi EXIF diabaikan | Cek piksel sebelum decode; EXIF dihormati |
| 9 | Pengurangan stok saat checkout tidak dicek hasilnya | Cek jumlah baris terubah; galat → rollback |
| 10 | Header keamanan minim; path file statis | `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `frame-ancestors`; `safe_join`; cache bukti bayar `private` |

### D. Konfigurasi baru di `.env`
`PROXY_HOPS` (jumlah proxy tepercaya; **isi 1 di belakang Nginx**), `LAJU_DAFTAR`, `LAJU_KONTAK`, `LAJU_CHAT`, `CHAT_MAKS_BERUNTUN`, `LAMBAT_MS`, `MAKS_PESANAN_TERTUNDA`. Semuanya punya nilai bawaan.

### E. Tes
27 tes bawaan, ditambah 9 tes keamanan (`Keamanan`) dan 6 tes alamat (`TestAlamat`) = **42 tes**. Tes keamanan diverifikasi gagal pada kode lama.

---

## Performa dan cara mencari penyebab lag

Diukur di sisi server: tiap endpoint hanya 1–6 query dan selesai dalam hitungan milidetik, jadi lag yang terasa di lokal hampir pasti bukan dari kode Python. Penyebab yang paling sering, urut dari yang paling berpengaruh:

1. **Tailwind CDN** (`cdn.tailwindcss.com`): ratusan KB JavaScript yang meng-compile CSS di browser pada *setiap* halaman dimuat. Solusinya build sekali jadi satu berkas CSS statis (lihat di bawah).
2. **Foto produk dari internet** (data `seed` memakai loremflickr yang lambat) dan **Google Fonts**. Unggah foto produk sendiri lewat Admin; foto unggahan otomatis dikecilkan dan di-cache browser 1 tahun.
3. **Folder proyek di OneDrive**: OneDrive menyinkronkan `.venv` (ribuan berkas) dan `uploads`, dan pemuat ulang `flask run --debug` ikut memantaunya. Pindahkan proyek ke luar OneDrive (mis. `C:\Projects\SawitKU`) atau jalankan tanpa `--debug`.
4. **`DB_HOST=localhost` di Windows** kadang menambah jeda ±1 dtk (mencoba IPv6 dulu). Pakai `DB_HOST=127.0.0.1`.

**Menemukan sumbernya:** buka DevTools (F12) → tab *Network*; kolom *Time* menunjukkan berkas yang lambat, dan tab *Timing* sebuah permintaan `/api/...` menampilkan `Server-Timing: app;dur=...` (waktu proses server). Request server yang lebih lama dari `LAMBAT_MS` (300 ms) otomatis dicatat di terminal sebagai `LAMBAT GET /api/...`.

**Yang sudah dioptimalkan di kode:** sesi tidak lagi menulis ke database di setiap request (hanya bila sisa masa < separuh); aset JS/CSS diberi versi otomatis (`?v=`) sehingga di-cache browser 1 tahun namun langsung segar saat berkas berubah; foto unggahan di-cache 1 tahun; respons JSON/HTML/JS/CSS dikompres gzip (core.js 27,8 KB → 10,8 KB), hasil kompresi berkas statis disimpan di memori; chat memakai polling minimal dan berhenti saat tab tersembunyi.

### Build Tailwind (disarankan sebelum deploy; butuh Node.js di komputer Anda)
```
npm install
npm run css          # menghasilkan frontend/shared/app.css
```
Setelah `frontend/shared/app.css` ada, server **otomatis** mengganti Tailwind CDN dengan berkas itu di semua halaman dan membuang `'unsafe-eval'` dari CSP. Tanpa berkas itu, halaman tetap memakai CDN. Jalankan ulang `npm run css` setiap kali menambah/mengubah kelas Tailwind di HTML/JS (atau `npm run css:watch` saat mengembangkan). Bila tampilan ada yang berantakan setelah build, hapus `app.css` untuk kembali ke CDN. Untuk deploy, jalankan `npm run css` di server/CI sebelum Gunicorn dinyalakan.

### Contoh Nginx (deploy)
```nginx
gzip on; gzip_types text/css application/javascript application/json image/svg+xml;
location /media/produk/ { alias /var/www/sawitku/uploads/produk/; expires 1y; add_header Cache-Control "public, immutable"; }   # foto produk: lewati Python
location /media/foto/   { alias /var/www/sawitku/uploads/foto/;   expires 1y; add_header Cache-Control "public, immutable"; }   # foto profil
location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr;
             proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;   # lalu pasang `limit_req zone=api burst=30;` pada location /api/
```
Sengaja hanya `produk` dan `foto` yang dilayani langsung oleh Nginx; `/media/bukti/` (bukti pembayaran) dibiarkan lewat Flask.

## Revisi terbaru (logo, resi, upload ulang, Midtrans, balasan ulasan)

**Cara upgrade (database sudah ada), urut:**
```bash
pip install -r requirements.txt
flask --app wsgi init-db        # membuat tabel baru (media, ulasan_balas) + menambah kolom baru di tabel pesanan
flask --app wsgi impor-media    # SEKALI: pindahkan foto lama di folder uploads/ ke database
python -m unittest discover -s tests    # harus: Ran 76 tests ... OK
```

| Revisi | Isi |
|---|---|
| Foto profil & bukti bayar tidak tampil setelah deploy | Gambar kini disimpan di **tabel `media` (database)**, bukan di disk server. Hosting yang menghapus file lokal saat restart/redeploy (mis. Render/Railway tanpa volume) tidak lagi membuat gambar hilang. `/media/...` tetap URL yang sama. |
| Logo | Semua ikon daun diganti `frontend/shared/logo.png` (landing, login, daftar, produk, dashboard customer & admin, footer). Favicon tab browser: `favicon.ico`, `favicon-32.png`, `apple-touch-icon.png` di `frontend/shared/`. |
| Tracking paket | Dashboard customer dan admin: menu **Lacak Paket** (cari nomor pesanan `12`/`#12`/`SK-12` atau nomor resi) dengan linimasa status. Admin wajib mengisi **kurir + resi** saat menandai dikirim (resi unik). Customer hanya bisa melacak pesanannya sendiri. |
| Pembayaran ditolak | Pesanan **tidak dibatalkan** lagi: kembali ke *Menunggu Pembayaran*, pembeli melihat alasan + teks "Silakan upload ulang bukti bayar" dan tombol **Upload Ulang Bukti**. Batas bayar diperpanjang sebesar `BATAS_BAYAR_JAM`. |
| Midtrans (Virtual Account) | Tombol **Virtual Account** di Pesanan Saya mengarahkan ke halaman bayar Midtrans (BCA/BNI/BRI/Permata/CIMB/lainnya). Status otomatis `diproses` lewat webhook `POST /api/midtrans/notifikasi` (tanda tangan SHA-512 diverifikasi) dan sinkron saat pembeli kembali ke dashboard. Isi `MIDTRANS_SERVER_KEY` di `.env` (sandbox: `SB-Mid-server-...`) dan set *Payment Notification URL* di dashboard Midtrans ke `https://DOMAINMU/api/midtrans/notifikasi`. Webhook butuh URL publik HTTPS (di localhost pakai ngrok/cloudflared). Kosong = tombol memberi pesan "belum diaktifkan"; QRIS manual tetap jalan. |
| Navigasi landing | Footer berisi navigasi (Jelajahi, Akun, Lacak Paket) + tombol **Kembali ke atas** yang muncul saat menggulir. |
| Lupa password | Link **Lupa password?** di halaman masuk menuju `/lupa-password`: masukkan email, terima kode OTP 6 angka (berlaku 10 menit, maks 5 salah, jeda kirim ulang 60 dtk), lalu buat password baru. Respons selalu sama untuk email terdaftar maupun tidak (tidak bisa dipakai menebak akun). Setelah berhasil, semua sesi login lama dikeluarkan, blokir login dibuka, dan email pemberitahuan dikirim. Butuh `SMTP_*` terisi seperti OTP register. Tabel baru `otp_reset` dibuat oleh `init-db`. |
| Balasan ulasan | Admin membalas, **pemilik ulasan bisa membalas balik** dari halaman produk, bergantian (maks 5 balasan pelanggan per ulasan). Masih versi sederhana. |

Catatan Midtrans: bila pembeli sudah membayar VA tetapi pesanan sempat dibatalkan otomatis (lewat 24 jam), sistem **tidak** mengaktifkannya lagi dan mencatat peringatan di log untuk penanganan manual.

## Upgrade dari versi lama (database sudah ada)

**Fitur OTP dan chat** menambah tabel `otp_daftar`, `otp_email`, dan `chat_pesan`. Jalankan sekali `flask --app wsgi init-db` (aman diulang, tidak menghapus data); tanpa ini pendaftaran akan galat `Table 'otp_daftar' doesn't exist` (atau `otp_email`).

`init-db` hanya membuat tabel yang belum ada; ia **tidak menambah kolom** ke tabel lama. Bila database kamu dibuat dari skema sebelum fitur alamat, jalankan sekali di MariaDB (`USE sawitku;` dulu):

```sql
ALTER TABLE pengguna
  ADD COLUMN telepon VARCHAR(20) NULL, ADD COLUMN alamat VARCHAR(255) NULL,
  ADD COLUMN kota VARCHAR(60) NULL,    ADD COLUMN kode_pos VARCHAR(10) NULL;
ALTER TABLE pesanan
  ADD COLUMN penerima VARCHAR(80) NOT NULL DEFAULT '', ADD COLUMN telepon VARCHAR(20) NOT NULL DEFAULT '',
  ADD COLUMN alamat VARCHAR(255) NOT NULL DEFAULT '',  ADD COLUMN kota VARCHAR(60) NOT NULL DEFAULT '',
  ADD COLUMN kode_pos VARCHAR(10) NOT NULL DEFAULT '';
```

Pesanan lama tetap tampil (tanpa alamat). Bila database masih kosong, cukup hapus lalu buat ulang (`DROP DATABASE sawitku;` lalu langkah 4 dan `init-db`).

---

## Mengganti isi toko

Merek sudah SawitKu, tetapi isi bawaan masih tanaman. Yang perlu disesuaikan:

| Yang diganti | Lokasi |
|---|---|
| **Daftar kategori** | **Dua tempat yang harus sama persis**: `KATEGORI` di `app/config.py` dan `KATEGORI` di `frontend/shared/core.js`. Jika berbeda, admin tidak bisa menyimpan produk. |
| Produk contoh | `app/seed_produk.json` (hanya dipakai `seed`) atau tambah lewat panel admin |
| Teks promosi (garansi, fitur) | `frontend/landing/index.html` |
| Slider dan kartu samping landing | otomatis dari data produk (`pilihBeranda()` di `frontend/landing/script.js`): slider = produk terlaris/rating tertinggi dengan nama, deskripsi, dan foto dari database; kartu samping = produk terbaru ("Baru Masuk") dan produk termurah ("Harga Termurah"). Ubah foto/deskripsi lewat Admin → Produk. |
| Kontak toko (WhatsApp, email, jam) | objek `KONTAK` di bagian atas `frontend/landing/script.js` (nomor WhatsApp format `62812...`, tanpa `+`/`0`); `href` cadangan di `index.html` |
| Warna merek | `frontend/shared/tailwind.js` (palet `brand` dan `sun`) |

Cari teks cepat di VS Code dengan **Ctrl+Shift+F**.

---

## Peta API

Semua respons sukses: `{"data": ...}`; galat: `{"error": "pesan"}` (kode 400/401/403/404/409/429). Autentikasi: header `Authorization: Bearer <token>`.

| Fungsi `Api` | Endpoint | Akses |
|---|---|---|
| `masuk` | `POST /api/auth/masuk` → `{token, user}` | publik |
| `daftar` | `POST /api/auth/daftar {username,email,password}` → kirim OTP ke email, `{email,berlaku,jeda}` (akun belum dibuat) | publik (dibatasi per IP) |
| `verifikasiOtp` | `POST /api/auth/daftar/verifikasi {email,kode}` → akun dibuat (201) | publik (dibatasi per IP & per kode) |
| `kirimUlangOtp` | `POST /api/auth/daftar/kirim-ulang {email}` → kode baru | publik (jeda 60 dtk) |
| logout / sesi aktif | `POST /api/auth/keluar` · `GET /api/auth/saya` | login |
| `produk` / `produkById` | `GET /api/produk` · `GET /api/produk/<id>` | publik |
| `ulasanTampil` | `GET /api/produk/<id>/ulasan` | publik |
| `KATEGORI` | `GET /api/kategori` | publik |
| `kirimPesan` | `POST /api/kontak` | publik (dibatasi per IP) |
| `favorit` / `favToggle` | `GET /api/favorit` · `POST /api/favorit/<id>/toggle` | login / customer |
| `keranjang` | `GET /api/keranjang` | customer |
| `kerAdd` / `kerSet` / `kerHapus` | `POST /api/keranjang {produkId,qty}` · `PUT`/`DELETE /api/keranjang/<id>` | customer |
| `checkout` | `POST /api/checkout {penerima,telepon,alamat,kota,kodePos,simpan?}` | customer |
| `pesananSaya` | `GET /api/pesanan/saya` | customer |
| `bayar` / `batal` / `terima` | `POST /api/pesanan/<id>/bayar {bukti}` · `/batal` · `/terima` | customer |
| `kirimUlasan` / `sudahUlas` | `POST /api/ulasan {produkId,rating,teks}` · `GET /api/ulasan/sudah/<id>` | customer / login |
| `profil` | `PUT /api/profil {username,email,foto?,telepon?,alamat?,kota?,kodePos?}` | login |
| `adminPesanan` | `GET /api/admin/pesanan` | admin |
| `verifikasi` / `kirimPesanan` | `POST /api/admin/pesanan/<id>/verifikasi {setuju,alasan}` · `/kirim` | admin |
| `produkSimpan` / `produkHapus` | `POST /api/admin/produk` · `PUT`/`DELETE /api/admin/produk/<id>` | admin |
| `penggunaAll` / `penggunaToggle` | `GET /api/admin/pengguna` · `POST /api/admin/pengguna/<id>/toggle` | admin |
| `ulasanAll` / `ulasanBalas` | `GET /api/admin/ulasan` · `POST /api/admin/ulasan/<id>/balas {teks}` | admin |
| `pesanKontak` | `GET /api/admin/kontak` | admin |

Tambahan: `GET /api/kesehatan` (cek hidup + koneksi DB) dan `GET /media/<folder>/<file>.jpg` (gambar unggahan).

---

## Aturan bisnis & keamanan

- **Harga & stok dihitung dari database** saat checkout (nilai dari klien diabaikan), dalam satu transaksi dengan `SELECT … FOR UPDATE` agar stok tidak minus saat dua pembeli bersamaan.
- **Alamat** divalidasi di server dan disimpan sebagai **salinan di tiap pesanan**; mengganti alamat profil tidak mengubah pesanan lama.
- **Alur status** dijaga di server; pesanan yang lewat `BATAS_BAYAR_JAM` dibatalkan otomatis (disapu ±tiap 10 detik saat katalog/pesanan diakses).
- **Ulasan** hanya untuk produk yang sudah diterima, satu per produk per pengguna; rating produk dihitung ulang dari ulasan.
- **Autentikasi**: password di-hash scrypt (salt acak); token sesi acak disimpan sebagai SHA-256 di tabel `sesi` dengan masa aktif bergeser `SESI_MENIT`; pesan galat login seragam; RBAC di setiap endpoint; menonaktifkan akun langsung memutus sesinya.
- **Pembatas laju**: login per username dan per IP; daftar dan kontak per IP; maksimal pesanan belum dibayar per akun.
- **Gambar** (produk, bukti bayar, foto profil): tipe, ukuran, dimensi, dan magic bytes dicek, lalu digambar ulang dengan Pillow (metadata terbuang, EXIF dihormati) dan disimpan dengan nama acak. Path `/media/...` hanya bisa merujuk berkas milik baris itu sendiri.
- **Frontend**: semua data pengguna di-escape (`K.esc`) sebelum masuk HTML; token di `sessionStorage`; CSP per halaman; header keamanan dari server.

---

## Catatan produksi

- Jalankan di belakang HTTPS (Nginx + Gunicorn): `gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app`. **Jangan** pakai `flask run --debug` di server.
- **Isi `PROXY_HOPS=1` bila di belakang Nginx**, kalau tidak, semua pengguna terlihat berasal dari satu IP dan batas per IP bisa memblokir semua orang sekaligus.
- `PUBLIC_BASE_URL` harus `https://…` bila diisi. Jangan pakai `CORS_ORIGINS=*`.
- Batas laju disimpan di memori tiap worker (dengan 4 worker, batas efektifnya ±4×). Untuk batas ketat tambahkan `limit_req` di Nginx.
- Batas login per username berarti pihak lain bisa sengaja mengunci akun orang selama `BLOKIR_MENIT`. Ini kompromi yang disengaja demi melawan tebak password terdistribusi.
- Halaman memakai Tailwind CDN yang membutuhkan `'unsafe-eval'` di CSP. Untuk produksi yang lebih ketat, build Tailwind sendiri lalu hapus `'unsafe-eval'` dan `https://cdn.tailwindcss.com` dari CSP.
- URL bukti pembayaran acak 128-bit tetapi publik bagi yang punya tautannya; bila perlu privasi lebih ketat, sajikan lewat endpoint ber-autentikasi.
- **Ganti/hapus akun demo** dari `seed` sebelum produksi.
- **Log**: aplikasi mencatat `LOGIN GAGAL`/`LOGIN OK`, `OTP ... SALAH`, dan `AUDIT admin=... METHOD /path` untuk setiap aksi admin yang mengubah data (nama pengguna sengaja tidak dicatat saat login gagal). Arahkan log Gunicorn ke file dan batasi aksesnya.
- **HTTPS**: header HSTS dikirim otomatis bila permintaan HTTPS. Di belakang Nginx, teruskan `proxy_set_header X-Forwarded-Proto $scheme;` dan set `PROXY_HOPS=1`.
- **Versi dependensi**: di venv produksi jalankan `pip freeze > requirements.lock` lalu pasang dari file itu, dan jalankan `pip install pip-audit && pip-audit` secara berkala.
- **Isi `SMTP_*`** agar OTP benar-benar terkirim; periksa juga SPF/DKIM domain pengirim agar email tidak masuk spam.
- Satu koneksi database per request (cukup untuk toko kecil); untuk trafik tinggi tambahkan pool koneksi.
- Cadangkan database dan folder `uploads/` secara berkala.
