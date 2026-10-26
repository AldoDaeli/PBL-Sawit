'use strict';
/* ===== Inti bersama: konfigurasi, keamanan, sesi JWT, API (REST ke Flask), binder template HTML, UI, grafik, kerangka dashboard =====
   Pembagian tugas: HTML (struktur) ada di <template> tiap halaman, JS hanya mengisi data lewat T (lihat bagian "Binder template").
   Semua fungsi Api bersifat asinkron (return Promise): panggil dengan `await`. */
const ROOT = '/';   // semua tautan memakai URL pendek dari akar situs: /masuk, /daftar, /dashboard, /admin, /produk/<id>
const CFG = { SESI_MENIT: 20, MAKS_GAGAL: 5, BLOKIR_MENIT: 5, BATAS_BAYAR_JAM: 24, AUTO_TERIMA_JAM: 24, MAKS_MB: 2 };
const KATEGORI = ['Tanaman Hias Daun', 'Tanaman Berbunga', 'Sukulen & Kaktus', 'Tanaman Gantung', 'Pot & Media Tanam', 'Perawatan'];   // sama dengan backend (app/config.py)
const NEXT = { landing: '', customer: 'dashboard', admin: 'admin' };   // dipakai sebagai ROOT + NEXT[x]
const STATUS = {
  menunggu_bayar: ['Menunggu Pembayaran', 'proses', 'bg-amber-100 text-amber-800'],
  menunggu_verifikasi: ['Menunggu Verifikasi', 'proses', 'bg-sky-100 text-sky-800'],
  diproses: ['Sedang Dikemas', 'proses', 'bg-indigo-100 text-indigo-800'],
  dikirim: ['Dalam Pengiriman', 'proses', 'bg-violet-100 text-violet-800'],
  selesai: ['Selesai', 'selesai', 'bg-brand-100 text-brand-800'],
  dibatalkan: ['Dibatalkan', 'batal', 'bg-rose-100 text-rose-800'],
};
const namaStatus = o => o.status === 'dikirim' && o.waktu && o.waktu.sampai ? 'Barang Tiba' : STATUS[o.status][0];

/* ---------- Keamanan ---------- */
const K = {
  esc: t => String(t ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  url: u => /^(https:\/\/|\/media\/|data:image\/(jpeg|png|webp);base64,)/i.test(u || '') || String(u || '').startsWith(location.origin + '/media/') ? u : '',
  username: u => /^[a-zA-Z0-9_]{4,20}$/.test(u),
  email: e => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e) && e.length <= 100,
  password: p => p.length >= 8 && p.length <= 64 && /[a-zA-Z]/.test(p) && /\d/.test(p),
  skorPassword: p => [p.length >= 8, /[a-z]/.test(p) && /[A-Z]/.test(p), /\d/.test(p), /[^A-Za-z0-9]/.test(p)].filter(Boolean).length,
  // Validasi file: tipe MIME, ekstensi, ukuran, dan magic bytes (isi sebenarnya harus gambar)
  async cekGambar(f, maxMB = CFG.MAKS_MB) {
    if (!f) return 'Pilih file terlebih dahulu.';
    if (!/\.(jpe?g|png|webp)$/i.test(f.name) || !['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) return 'Hanya file JPG, PNG, atau WEBP.';
    if (f.size > maxMB * 1048576) return `Ukuran maksimal ${maxMB} MB.`;
    const h = [...new Uint8Array(await f.slice(0, 12).arrayBuffer())].map(x => x.toString(16).padStart(2, '0')).join('');
    return (h.startsWith('ffd8ff') || h.startsWith('89504e47') || (h.startsWith('52494646') && h.slice(16, 24) === '57454250')) ? null : 'Isi file bukan gambar yang valid.';
  },
  // Gambar digambar ulang lewat canvas: metadata & muatan tersembunyi ikut terbuang
  kecilkan(f, sisi = 800) {
    return new Promise((ok, no) => {
      const u = URL.createObjectURL(f), im = new Image();
      im.onload = () => { const r = Math.min(1, sisi / Math.max(im.width, im.height)), c = document.createElement('canvas');
        c.width = Math.round(im.width * r); c.height = Math.round(im.height * r); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
        URL.revokeObjectURL(u); ok(c.toDataURL('image/jpeg', .82)); };
      im.onerror = () => { URL.revokeObjectURL(u); no(new Error('Gambar tidak dapat dibaca.')); }; im.src = u;
    });
  },
  // Salin teks ke clipboard (dengan cadangan untuk konteks tanpa Clipboard API)
  async salin(teks) {
    try { await navigator.clipboard.writeText(teks); return true; } catch {}
    const t = document.createElement('textarea'); t.value = teks; t.style.cssText = 'position:fixed;opacity:0'; document.body.append(t); t.select();
    try { return document.execCommand('copy'); } catch { return false; } finally { t.remove(); }
  },
};

/* ---------- Sesi (JWT) & RBAC ----------
   Token JWT dari server disimpan di localStorage dalam DUA slot terpisah, satu per peran: `tp_sesi_admin` dan `tp_sesi_customer`.
   - Tab baru / salin link langsung masuk: halaman admin membaca slot admin, halaman customer membaca slot customer.
   - Admin dan customer boleh login bersamaan di tab berbeda (slotnya tidak saling menimpa). Satu browser hanya punya SATU admin dan SATU customer:
     login ulang pada peran yang sama menggantikan sesi lama (tidak ada customer1 di tab 1 dan customer2 di tab 2). Untuk itu pakai browser/profil lain.
   - Keluar di satu tab menghapus slot perannya, sehingga semua tab peran itu ikut keluar; tab peran lain tidak terpengaruh.
   - Halaman publik (landing, produk) memakai sesi customer bila ada, jika tidak sesi admin.
   Masa berlaku ditentukan server (JWT `exp` + tabel `sesi`, batas diam SESI_MENIT), bukan oleh jenis penyimpanan: token lama ditolak server lalu dibuang.
   `user` hanya cache tampilan; hak akses selalu diputuskan server. Server mencabut token saat keluar dan memperpanjang sesi
   lewat header X-Token-Baru selama pengguna aktif. */
const Sesi = {
  PERAN: ['customer', 'admin'], konteks: null, dijaga: null, _akhirCatat: 0, _tampil: null,
  _ls: { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} }, del(k) { try { localStorage.removeItem(k); } catch {} } },
  _kunci: peran => 'tp_sesi_' + peran, _kunciAktif: peran => 'tp_aktif_' + peran,
  _baca(peran) { try { const s = JSON.parse(this._ls.get(this._kunci(peran))); if (s && s.token && s.user && s.user.peran === peran) return s; } catch {} this._ls.del(this._kunci(peran)); return null; },
  // Slot yang dipakai halaman ini: halaman dashboard = perannya sendiri; halaman publik = customer dulu, lalu admin
  slot() { return this.konteks || this.PERAN.find(p => this._baca(p)) || null; },
  baca() { const p = this.slot(); return p ? this._baca(p) : null; },
  token() { const s = this.baca(); return s ? s.token : null; },
  user() { const s = this.baca(); return s ? s.user : null; },
  mulai(token, user) { this._ls.set(this._kunci(user.peran), JSON.stringify({ token, user })); this.catatAktif(true, user.peran); },
  simpanUser(user) { const s = this._baca(user.peran); if (s) { s.user = user; this._ls.set(this._kunci(user.peran), JSON.stringify(s)); } },
  tukarToken(token, lama) { for (const p of this.PERAN) { const s = this._baca(p); if (s && s.token === lama && token !== lama) { s.token = token; this._ls.set(this._kunci(p), JSON.stringify(s)); } } },
  hapus(peran = this.slot()) { if (!peran) return; this._ls.del(this._kunci(peran)); this._ls.del(this._kunciAktif(peran)); },
  catatAktif(paksa, peran = this.slot()) { const n = Date.now(); if (peran && (paksa || n - this._akhirCatat > 5000)) { this._akhirCatat = n; this._ls.set(this._kunciAktif(peran), String(n)); } },
  // Cocokkan cache dengan server; bila token sudah tidak berlaku, cache dibuang (tanpa pengalihan halaman)
  async segarkan() {
    if (!this.token()) return null;
    try { return await Api.saya(true); } catch (e) { if (e.status === 401 || e.status === 403) this.hapus(); return this.user(); }
  },
  async keluar(habis) {
    if (!habis) { try { await Api.keluar(); } catch {} }
    this.hapus(); location.href = ROOT + 'masuk' + (habis ? '?habis=1' : '');
  },
  beranda: p => ROOT + (p === 'admin' ? NEXT.admin : NEXT.customer),
  async wajib(peran) { // penjaga halaman: belum login / peran salah -> dialihkan
    this.konteks = peran; this._tampil = this.user()?.id ?? null;
    if (!this.user()) { location.replace(ROOT + 'masuk?next=' + peran); return null; }
    let u; try { u = await Api.saya(); } catch (e) { if (e.status !== 401) Toast.err(e.message); return null; }   // 401 -> Api sudah mengalihkan ke login
    if (u.peran !== peran) { location.replace(this.beranda(u.peran)); return null; }
    this.dijaga = u.id; this.catatAktif(true);
    let ping = Date.now();
    ['click', 'keydown', 'mousemove', 'touchstart'].forEach(e => addEventListener(e, () => {
      this.catatAktif();
      if (Date.now() - ping > 120000) { ping = Date.now(); Api.saya(true).catch(() => {}); }   // jaga sesi server tetap hidup selama pengguna aktif
    }, { passive: true }));
    // batas diam dihitung dari aktivitas terakhir pada peran ini (di tab mana pun)
    setInterval(() => { if (Date.now() - (+this._ls.get(this._kunciAktif(peran)) || Date.now()) > CFG.SESI_MENIT * 60000) this.keluar(true); }, 15000);
    return u;
  },
};
Sesi._tampil = Sesi.user()?.id ?? null;
// Sinkron antar tab: masuk/keluar pada satu peran langsung berlaku di tab lain yang memakai peran itu
addEventListener('storage', e => {
  if (!e.key || !e.key.startsWith('tp_sesi_')) return;
  const id = Sesi.user()?.id ?? null; if (id === Sesi._tampil) return;      // token diperpanjang saja: tidak ada yang perlu dilakukan
  Sesi._tampil = id;
  if (Sesi.dijaga !== null) {                       // halaman yang butuh login
    if (id === null) location.replace(ROOT + 'masuk?habis=1');   // keluar di tab lain
    else location.reload();                          // akun lain masuk di tab lain
    return;
  }
  document.dispatchEvent(new CustomEvent('sesi-berubah', { detail: Sesi.user() }));   // halaman publik: perbarui tombol masuk/keranjang
});

/* ---------- API (REST ke Flask; satu fungsi = satu endpoint) ---------- */
const API_BASE = '/api';   // frontend dilayani dari origin yang sama dengan API
const qs = p => { const q = new URLSearchParams(Object.entries(p || {}).filter(([, v]) => v)).toString(); return q ? '?' + q : ''; };
const Api = {
  async _req(method, path, body, { diam } = {}) {
    const h = { Accept: 'application/json' }, t = Sesi.token();
    if (t) h.Authorization = 'Bearer ' + t;
    if (body !== undefined) h['Content-Type'] = 'application/json';
    let r, j = null;
    try { r = await fetch(API_BASE + path, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) }); }
    catch { throw new Error('Tidak dapat terhubung ke server. Coba lagi nanti.'); }
    const baru = r.headers.get('X-Token-Baru'); if (baru && t) Sesi.tukarToken(baru, t);   // sesi diperpanjang server: ganti token di semua tab
    try { j = await r.json(); } catch {}
    if (!r.ok) {
      if (r.status === 401 && t && !diam) Sesi.keluar(true);   // sesi berakhir di server
      const e = new Error((j && j.error) || 'Terjadi kesalahan pada server.'); e.status = r.status; throw e;
    }
    return j ? j.data : null;
  },
  /* --- auth --- */
  async saya(diam) { const u = await this._req('GET', '/auth/saya', undefined, { diam }); Sesi.simpanUser(u); return u; },
  async masuk(username, pw) {
    const k = String(username || '').trim(), p = String(pw || '');
    if (!k || !p) throw new Error('Username dan password wajib diisi.');
    const d = await this._req('POST', '/auth/masuk', { username: k, password: p }, { diam: true });
    Sesi.mulai(d.token, d.user); return d.user;
  },
  /* pendaftaran 2 langkah: daftar -> kode OTP dikirim ke email -> verifikasiOtp membuat akun */
  daftar: ({ username, email, password }) => Api._req('POST', '/auth/daftar', { username, email, password }, { diam: true }),   // -> {email, berlaku, jeda}
  verifikasiOtp: (email, kode) => Api._req('POST', '/auth/daftar/verifikasi', { email, kode }, { diam: true }),
  lupaKirim: email => Api._req('POST', '/auth/lupa', { email }, { diam: true }),
  lupaReset: (email, kode, password) => Api._req('POST', '/auth/lupa/reset', { email, kode, password }, { diam: true }),
  kirimUlangOtp: email => Api._req('POST', '/auth/daftar/kirim-ulang', { email }, { diam: true }),
  /* chat pelanggan <-> admin (diam: galat polling tidak memicu keluar otomatis; komponen Chat yang menanganinya) */
  chat: p => Api._req('GET', '/chat' + qs(p), undefined, { diam: true }),
  chatKirim: isi => Api._req('POST', '/chat', { isi }, { diam: true }),
  chatBelum: () => Api._req('GET', '/chat/belum', undefined, { diam: true }),
  adminChatDaftar: () => Api._req('GET', '/admin/chat', undefined, { diam: true }),
  adminChat: (uid, p) => Api._req('GET', `/admin/chat/${uid}` + qs(p), undefined, { diam: true }),
  adminChatKirim: (uid, isi) => Api._req('POST', `/admin/chat/${uid}`, { isi }, { diam: true }),
  adminChatBelum: () => Api._req('GET', '/admin/chat/belum', undefined, { diam: true }),
  /* ganti email: password saat ini + email baru -> OTP ke email baru -> verifikasi */
  emailMinta: (email, password) => Api._req('POST', '/profil/email/minta', { email, password }),
  emailVerifikasi: kode => Api._req('POST', '/profil/email/verifikasi', { kode }),
  keluar: () => Api._req('POST', '/auth/keluar', undefined, { diam: true }),
  /* --- katalog --- */
  produk: () => Api._req('GET', '/produk'),
  async produkById(id) { try { return await this._req('GET', '/produk/' + Number(id)); } catch (e) { if (e.status === 404) return null; throw e; } },
  ulasanTampil: pid => Api._req('GET', `/produk/${Number(pid)}/ulasan`),
  kirimPesan: ({ nama, email, jenis, isi }) => Api._req('POST', '/kontak', { nama, email, jenis, isi }),
  /* --- favorit, keranjang, pesanan (customer) --- */
  async favorit() { return Sesi.user() ? this._req('GET', '/favorit') : []; },
  async favToggle(pid) { return (await this._req('POST', `/favorit/${pid}/toggle`)).aktif; },
  async keranjang() { const u = Sesi.user(); return u && u.peran === 'customer' ? this._req('GET', '/keranjang') : []; },
  async jumlahKeranjang() { return (await this.keranjang()).reduce((a, c) => a + c.qty, 0); },
  kerAdd: (pid, qty = 1) => Api._req('POST', '/keranjang', { produkId: pid, qty }),
  kerSet: (pid, qty) => Api._req('PUT', '/keranjang/' + pid, { qty }),
  kerHapus: pid => Api._req('DELETE', '/keranjang/' + pid),
  checkout: a => Api._req('POST', '/checkout', a),   // a = {metode, penerima, telepon, alamat, kota, kodePos, simpan}; harga & stok dihitung server
  pesananSaya: () => Api._req('GET', '/pesanan/saya'),
  pesananById: async id => (await Api.pesananSaya()).find(o => o.id === Number(id)) || null,
  batal: id => Api._req('POST', `/pesanan/${id}/batal`),
  terima: (id, foto) => Api._req('POST', `/pesanan/${id}/terima`, foto ? { foto } : {}),   // foto barang tiba bersifat opsional
  /* --- pembayaran Midtrans: QR / nomor VA ditampilkan di halaman sendiri, lalu wajib unggah bukti --- */
  metodeBayar: async () => (await Api._req('GET', '/pembayaran/metode')).metode,   // [{kode, label, jenis}]
  buatTagihan: (id, metode) => Api._req('POST', `/pesanan/${id}/pembayaran`, metode ? { metode } : {}),
  cekTagihan: id => Api._req('POST', `/pesanan/${id}/pembayaran/cek`),
  kirimBukti: (id, bukti) => Api._req('POST', `/pesanan/${id}/bukti`, { bukti }),
  kirimUlasan: (pid, rating, teks) => Api._req('POST', '/ulasan', { produkId: pid, rating, teks }),
  async sudahUlas(pid) { return Sesi.user() && pid != null ? (await this._req('GET', '/ulasan/sudah/' + pid)).sudah : false; },
  async profil({ username, email, foto, telepon, alamat, kota, kodePos }) {
    const b = { username, email, telepon, alamat, kota, kodePos }; if (foto) b.foto = foto;   // kunci yang undefined tidak terkirim
    const u = await this._req('PUT', '/profil', b); Sesi.simpanUser(u); return u;
  },
  /* --- admin --- */
  adminPesanan: () => Api._req('GET', '/admin/pesanan'),
  verifikasi: (id, setuju, alasan) => Api._req('POST', `/admin/pesanan/${id}/verifikasi`, { setuju: !!setuju, alasan }),
  kirimPesanan: (id, kurir, resi) => Api._req('POST', `/admin/pesanan/${id}/kirim`, { kurir, resi }),
  tandaiSampai: id => Api._req('POST', `/admin/pesanan/${id}/sampai`),
  adminCekMidtrans: id => Api._req('POST', `/admin/pesanan/${id}/midtrans/cek`),
  lacak: kode => Api._req('GET', '/lacak?kode=' + encodeURIComponent(kode)),
  balasUlasan: (id, teks) => Api._req('POST', `/ulasan/${id}/balas`, { teks }),
  produkSimpan(f) {
    const b = { nama: f.nama, kategori: f.kategori, harga: f.harga, stok: f.stok, gambar: f.gambar, deskripsi: f.deskripsi, spek: f.spek, bestSeller: !!f.bestSeller };
    return f.id ? this._req('PUT', '/admin/produk/' + f.id, b) : this._req('POST', '/admin/produk', b);
  },
  produkHapus: id => Api._req('DELETE', '/admin/produk/' + id),
  penggunaAll: () => Api._req('GET', '/admin/pengguna'),
  penggunaToggle: id => Api._req('POST', `/admin/pengguna/${id}/toggle`),
  ulasanAll: () => Api._req('GET', '/admin/ulasan'),
  ulasanBalas: (id, teks) => Api._req('POST', `/admin/ulasan/${id}/balas`, { teks }),   // admin hanya memberi komentar
  pesanKontak: () => Api._req('GET', '/admin/kontak'),
};

/* ---------- Format & ikon ---------- */
const rp = n => 'Rp' + Math.round(n).toLocaleString('id-ID');
const tgl = (t, pendek) => new Date(t).toLocaleDateString('id-ID', pendek ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' });
const wkt = t => t ? new Date(t).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }) : '';
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
// Ikon dari sprite /shared/icons.svg (satu berkas, di-cache browser)
const I = (n, c = 'w-5 h-5') => `<svg class="ic ${c}" aria-hidden="true"><use href="/shared/icons.svg#${n}"/></svg>`;
const ikon = (akar = document) => $$('[data-ikon]', akar).forEach(e => { if (!e.dataset.sudah) { e.dataset.sudah = 1; e.insertAdjacentHTML('afterbegin', I(e.dataset.ikon, e.dataset.kelas || 'w-5 h-5')); } });
// Bintang rating 1-5 (nilai dibulatkan). Produk tanpa ulasan memakai ratingTeks() -> "Belum ada ulasan"
const bintang = r => { const p = Math.round(r || 0); return `<span class="bintang" role="img" aria-label="Rating ${r || 0} dari 5">${[1, 2, 3, 4, 5].map(i => `<svg class="ic ic-isi ${i > p ? 'mati' : ''}" aria-hidden="true"><use href="/shared/icons.svg#star"/></svg>`).join('')}</span>`; };
const ratingTeks = p => p.jumlahUlasan ? `${Number(p.rating).toFixed(1)} (${p.jumlahUlasan} ulasan)` : 'Belum ada ulasan';
const avatar = (u, c = 'w-10 h-10') => u.foto && K.url(u.foto) ? `<img src="${K.url(u.foto)}" alt="" class="${c} rounded-full object-cover">` : `<span class="${c} rounded-full bg-brand-600 text-white grid place-items-center font-bold uppercase shrink-0">${K.esc(u.username[0])}</span>`;
const badgeStatus = o => `<span class="lencana ${STATUS[o.status][2]}">${K.esc(namaStatus(o))}</span>`;

/* ---------- Binder template ----------
   HTML hidup di <template id="t-..."> pada berkas .html; JS hanya memanggil T.klon('t-...', data). Atribut:
     data-t="jalur|filter"          isi teks            data-src="jalur"        gambar (disaring K.url)
     data-href="/produk/{id}"       tautan              data-a-NAMA="{jalur}"   atribut apa saja (aria-label, title, ...)
     data-if / data-ifnot="jalur"   hapus elemen bila salah/benar                data-cls="jalur=kelas kelas;!jalur=kelas"
     data-stars="jalur"             bintang rating      data-val="jalur"        nilai input
     <template data-each="jalur">   ulangi isinya untuk tiap anggota larik
   Semua nilai masuk lewat textContent / setAttribute, tidak pernah innerHTML, jadi data pengguna tidak bisa menjadi XSS. */
const T = {
  filter: { rp: v => rp(v || 0), tgl: v => v ? tgl(v) : '', wkt, n: v => Number(v || 0).toLocaleString('id-ID'), rating: v => Number(v || 0).toFixed(1), status: v => STATUS[v] ? STATUS[v][0] : v },
  ambil(d, ekspr) {
    const [jalur, ...fs] = String(ekspr).trim().split('|'); let v = jalur === '.' ? d : jalur.split('.').reduce((a, k) => a == null ? undefined : a[k], d);
    for (const f of fs) v = (T.filter[f.trim()] || (x => x))(v, d); return v;
  },
  _tpl: (s, d) => String(s).replace(/\{([^}]+)\}/g, (_, e) => { const v = T.ambil(d, e); return v == null ? '' : v; }),
  isi(akar, d) {
    const semua = (akar.nodeType === 1 ? [akar] : []).concat($$('*', akar));
    for (const el of semua) {
      if (el !== akar && !akar.contains(el)) continue;          // sudah terhapus bersama induknya
      if (el.tagName === 'TEMPLATE' && el.hasAttribute('data-each')) {
        for (const item of T.ambil(d, el.getAttribute('data-each')) || []) { const f = el.content.cloneNode(true); T.isi(f, { ...d, ...item, _induk: d }); el.before(f); }
        el.remove(); continue;
      }
      if (el.hasAttribute('data-if') && !T.ambil(d, el.getAttribute('data-if'))) { el.remove(); continue; }
      if (el.hasAttribute('data-ifnot') && T.ambil(d, el.getAttribute('data-ifnot'))) { el.remove(); continue; }
      for (const a of [...el.attributes]) {
        const n = a.name, v = a.value;
        if (n === 'data-t') el.textContent = T.ambil(d, v) ?? '';
        else if (n === 'data-src') { const u = K.url(T.ambil(d, v)); if (u) el.setAttribute('src', u); else el.removeAttribute('src'); }
        else if (n === 'data-href') el.setAttribute('href', T._tpl(v, d));
        else if (n === 'data-val') el.value = T.ambil(d, v) ?? '';
        else if (n === 'data-stars') el.innerHTML = bintang(T.ambil(d, v));
        else if (n === 'data-cls') v.split(';').forEach(r => { const i = r.indexOf('='), neg = r.startsWith('!'), k = r.slice(neg ? 1 : 0, i), on = !!T.ambil(d, k); if (on !== neg) el.classList.add(...r.slice(i + 1).split(' ').filter(Boolean)); });
        else if (n.startsWith('data-a-')) el.setAttribute(n.slice(7), T._tpl(v, d));
      }
    }
    return akar;
  },
  klon(id, d = {}) { const t = document.getElementById(id); if (!t) throw new Error('Template tidak ada: ' + id); const f = t.content.cloneNode(true); T.isi(f, d); ikon(f); return f; },
  satu(id, d) { return T.klon(id, d).firstElementChild; },
  daftar(induk, id, larik, kosongId) { induk.replaceChildren(...(larik.length ? larik.map((x, i) => { const e = T.satu(id, { ...x, _i: i }); e.style.animationDelay = Math.min(i, 10) * 45 + 'ms'; return e; }) : kosongId ? [T.satu(kosongId, {})] : [])); },
};

const Toast = {
  tampil(pesan, tipe = 'ok') {
    let w = $('#toast-w'); if (!w) { w = document.createElement('div'); w.id = 'toast-w'; w.className = 'fixed top-4 right-4 z-[100] flex flex-col gap-2 w-[min(92vw,340px)]'; w.setAttribute('role', 'status'); document.body.append(w); }
    const t = document.createElement('div'), warna = tipe === 'err' ? 'border-rose-400 text-rose-700' : 'border-brand-500 text-brand-800';
    t.className = `animate-slide-in bg-white shadow-xl rounded-xl border-l-4 ${warna} px-4 py-3 text-sm font-medium flex gap-2 items-start`;
    const ik = document.createElement('span'), tx = document.createElement('span'); ik.textContent = tipe === 'err' ? '✕' : '✓'; tx.textContent = pesan; t.append(ik, tx); w.append(t);
    setTimeout(() => { t.style.transition = 'opacity .3s'; t.style.opacity = 0; setTimeout(() => t.remove(), 300); }, 3600);
  },
  ok: m => Toast.tampil(m), err: m => Toast.tampil(m, 'err'),
};
const Modal = {
  // `isi` = string HTML statis ATAU Node/DocumentFragment dari T.klon (disarankan)
  buka(isi, lebar = 'max-w-lg') {
    const m = document.createElement('div'); m.className = 'fixed inset-0 z-[90] grid place-items-center p-4 animate-fade-in';
    const lat = document.createElement('div'); lat.dataset.tutup = ''; lat.className = 'absolute inset-0 bg-slate-900/50 backdrop-blur-sm';
    const kotak = document.createElement('div'); kotak.className = `relative bg-white rounded-2xl shadow-2xl w-full ${lebar} max-h-[90vh] overflow-y-auto animate-pop`; kotak.setAttribute('role', 'dialog'); kotak.setAttribute('aria-modal', 'true');
    if (typeof isi === 'string') kotak.innerHTML = isi; else kotak.append(isi);
    m.append(lat, kotak);
    const tutup = () => { m.remove(); removeEventListener('keydown', esc); }, esc = e => e.key === 'Escape' && tutup();
    m.addEventListener('click', e => { if (e.target.closest('[data-tutup]')) tutup(); }); addEventListener('keydown', esc); document.body.append(m); m.tutup = tutup;
    const f = $('[autofocus],input,textarea,select,button:not([data-tutup])', kotak); if (f) f.focus({ preventScroll: true }); return m;
  },
  dari: (id, d, lebar) => Modal.buka(T.klon(id, d), lebar),
  konfirmasi(pesan, tombol = 'Ya, lanjutkan') {
    return new Promise(ok => { const m = this.dari('t-konfirmasi', { pesan, tombol }, 'max-w-sm');
      $('[data-ya]', m).onclick = () => { m.tutup(); ok(true); }; m.addEventListener('click', e => e.target.closest('[data-tutup]') && ok(false)); });
  },
};
// Gambar rusak diganti placeholder (tanpa atribut onerror inline agar sesuai CSP)
document.addEventListener('error', e => { const t = e.target; if (t.tagName === 'IMG' && !t.dataset.gagal) { t.dataset.gagal = 1; t.src = 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><rect width="400" height="400" fill="#dcf1e1"/><path d="M200 300c-40-20-60-60-50-110 30 0 60 20 70 50 10-40 40-70 80-80 10 60-20 120-100 140z" fill="#5ab37c"/></svg>'); } }, true);
const Animasi = {
  reveal() { const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('tampil'); io.unobserve(e.target); } }), { threshold: .12 });
    $$('[data-reveal]:not(.tampil)').forEach(el => { el.style.transitionDelay = (el.dataset.delay || 0) + 'ms'; io.observe(el); }); },
  hitung(el, akhir, fmt = v => Math.round(v).toLocaleString('id-ID'), dur = 900) {
    if (matchMedia('(prefers-reduced-motion:reduce)').matches) { el.textContent = fmt(akhir); return; }
    const t0 = performance.now(); (function f(t) { const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3); el.textContent = fmt(akhir * e); if (p < 1) requestAnimationFrame(f); })(t0);
  },
};

/* ---------- Grafik SVG (tanpa pustaka luar) ---------- */
const Grafik = {
  // Batas atas sumbu yang rapi + jumlah garis bantu (bilangan bulat untuk data cacah kecil)
  skala(data) {
    const mx = Math.max(0, ...data);
    if (mx <= 4 && data.every(Number.isInteger)) { const top = Math.max(1, Math.ceil(mx)); return { top, t: top }; }
    const raw = mx / 4, p = Math.pow(10, Math.floor(Math.log10(raw))), s = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 10].map(x => x * p).find(x => x >= raw * .999) || 10 * p;
    return { top: s * 4, t: 4 };
  },
  singkat(v) { const f = (x, m) => x.toLocaleString('id-ID', { maximumFractionDigits: m }); return v >= 1e6 ? f(v / 1e6, 2) + ' jt' : v >= 1e3 ? f(v / 1e3, 1) + ' rb' : f(v, 0); },
  _sumbu(top, t, L, W, H, T, B) { let g = ''; for (let i = 0; i <= t; i++) { const y = T + (H - T - B) * (1 - i / t); g += `<line x1="${L}" x2="${W - 8}" y1="${y}" y2="${y}" stroke="#e2e8f0" stroke-dasharray="3 4"/><text x="${L - 6}" y="${y + 4}" text-anchor="end" font-size="10" fill="#94a3b8">${Grafik.singkat(top * i / t)}</text>`; } return g; },
  _label(labels, x, H) { const st = Math.ceil(labels.length / 10); return labels.map((l, i) => i % st ? '' : `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="10" fill="#94a3b8">${K.esc(l)}</text>`).join(''); },
  _kosong: (W, H) => `<text x="${W / 2}" y="${H / 2 - 6}" text-anchor="middle" font-size="12" fill="#94a3b8">Belum ada data pada rentang ini</text>`,
  // Tooltip interaktif: klik/sentuh (HP) atau arahkan kursor pada batang/titik/irisan -> muncul gelembung berisi nilai. Klik di luar menutupnya.
  _pasang(el) {
    el.style.position = 'relative'; el.querySelector('.tip-grafik')?.remove();
    const tip = document.createElement('div'); tip.className = 'tip-grafik'; tip.setAttribute('role', 'status'); el.append(tip);
    let kunci = null; const tutup = () => { tip.classList.remove('on'); el.querySelectorAll('.hit.on').forEach(h => h.classList.remove('on')); kunci = null; };
    const buka = (h, e) => {
      el.querySelectorAll('.hit.on').forEach(x => x.classList.remove('on')); h.classList.add('on');
      const [judul, ...baris] = h.dataset.tip.split('||'); tip.innerHTML = `<b>${K.esc(judul)}</b>${baris.map(b => `<span>${K.esc(b)}</span>`).join('')}`;
      const er = el.getBoundingClientRect(), svg = h.ownerSVGElement, sr = svg.getBoundingClientRect(), k = sr.width / svg.viewBox.baseVal.width;
      let x = h.dataset.ax ? sr.left - er.left + h.dataset.ax * k : e.clientX - er.left, y = h.dataset.ay ? sr.top - er.top + h.dataset.ay * k : e.clientY - er.top;
      tip.classList.add('on'); const w = tip.offsetWidth, hh = tip.offsetHeight;
      x = Math.min(Math.max(x, w / 2 + 4), er.width - w / 2 - 4); y = y - hh - 10; if (y < 0) y = y + hh + 24;
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    };
    if (el._tipPasang) return; el._tipPasang = 1;
    el.addEventListener('pointermove', e => { if (kunci || e.pointerType === 'touch') return; const h = e.target.closest?.('.hit'); h ? buka(h, e) : el.querySelector('.tip-grafik')?.classList.remove('on'); });
    el.addEventListener('pointerleave', e => { if (!kunci && e.pointerType !== 'touch') { el.querySelector('.tip-grafik')?.classList.remove('on'); el.querySelectorAll('.hit.on').forEach(h => h.classList.remove('on')); } });
    el.addEventListener('click', e => { const h = e.target.closest?.('.hit'); e.stopPropagation(); if (!h) return tutup(); if (kunci === h) return tutup(); kunci = h; buka(h, e); });
    document.addEventListener('click', e => { if (!el.contains(e.target)) tutup(); });
  },
  bar(el, labels, seri, fmt = v => v.toLocaleString('id-ID')) {
    const W = 640, H = 260, L = 50, B = 28, T = 12, all = seri.flatMap(s => s.data), { top, t } = this.skala(all), n = labels.length, gw = (W - L - 8) / n, bw = Math.min(26, gw / (seri.length + .6));
    let g = this._sumbu(top, t, L, W, H, T, B) + this._label(labels, i => L + gw * i + gw / 2, H);
    labels.forEach((l, i) => seri.forEach((s, j) => { const v = s.data[i]; if (!v) return; const h = (H - T - B) * v / top, x = L + gw * i + gw / 2 - bw * seri.length / 2 + j * bw;
      g += `<rect class="bar" x="${x}" y="${H - B - h}" width="${Math.max(bw - 2, 3)}" height="${h}" rx="3" fill="${s.warna}" style="animation-delay:${i * 25 + j * 40}ms"/>`; }));
    labels.forEach((l, i) => { const top0 = Math.min(...seri.map(s => s.data[i] ? H - B - (H - T - B) * s.data[i] / top : H - B)); g += `<rect class="hit" x="${L + gw * i}" y="${T}" width="${gw}" height="${H - T - B}" fill="transparent" data-ax="${L + gw * i + gw / 2}" data-ay="${top0}" data-tip="${K.esc(l)}||${seri.map(s => (seri.length > 1 ? s.nama + ': ' : '') + fmt(s.data[i] || 0)).map(K.esc).join('||')}"/>`; });
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="w-full h-auto" role="img">${g}${all.some(Boolean) ? '' : this._kosong(W, H)}</svg>`; this._pasang(el);
  },
  area(el, labels, data, warna = '#38995e', fmt = v => v.toLocaleString('id-ID')) {
    const W = 640, H = 240, L = 50, B = 28, T = 14, { top, t } = this.skala(data), n = labels.length, sx = i => L + (W - L - 14) * (n === 1 ? .5 : i / (n - 1)), sy = v => T + (H - T - B) * (1 - v / top);
    const d = 'M' + data.map((v, i) => `${sx(i)},${sy(v)}`).join(' L'), g = this._sumbu(top, t, L, W, H, T, B) + this._label(labels, sx, H), pts = n <= 16;
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="w-full h-auto" role="img"><defs><linearGradient id="ga${warna.slice(1)}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${warna}" stop-opacity=".35"/><stop offset="1" stop-color="${warna}" stop-opacity="0"/></linearGradient></defs>${g}
      <path class="area" d="${d} L${sx(n - 1)},${H - B} L${sx(0)},${H - B}Z" fill="url(#ga${warna.slice(1)})"/><path class="garis" pathLength="1" d="${d}" fill="none" stroke="${warna}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      ${data.map((v, i) => (pts || v) ? `<circle class="titik" cx="${sx(i)}" cy="${sy(v)}" r="${pts ? 4 : 3}" fill="#fff" stroke="${warna}" stroke-width="2.5" style="animation-delay:${500 + i * 25}ms"/>` : '').join('')}${data.map((v, i) => `<rect class="hit" x="${sx(i) - (W - L - 14) / Math.max(n - 1, 1) / 2}" y="${T}" width="${(W - L - 14) / Math.max(n - 1, 1)}" height="${H - T - B}" fill="transparent" data-ax="${sx(i)}" data-ay="${sy(v)}" data-tip="${K.esc(labels[i])}||${K.esc(fmt(v))}"/>`).join('')}${data.some(Boolean) ? '' : this._kosong(W, H)}</svg>`; this._pasang(el);
  },
  donut(el, items, satuan = '') {
    const tot = items.reduce((a, i) => a + i.nilai, 0) || 1; let off = 0;
    const arc = items.map((i, k) => { const p = i.nilai / tot * 100, s = p ? `<circle class="arc hit" r="15.9" cx="21" cy="21" fill="none" stroke="${i.warna}" stroke-width="6" pathLength="100" stroke-dasharray="${Math.max(p - 1, 0)} ${100 - Math.max(p - 1, 0)}" stroke-dashoffset="${-off}" data-tip="${K.esc(i.label)}||${i.nilai}${satuan} (${Math.round(p)}%)" style="animation-delay:${k * 150}ms"/>` : ''; off += p; return s; }).join('');
    el.innerHTML = `<div class="flex items-center gap-6 flex-wrap justify-center"><svg viewBox="0 0 42 42" class="w-40 h-40 -rotate-90">${arc}</svg><ul class="space-y-2 text-sm">${items.map(i => `<li class="flex items-center gap-2"><span class="w-3 h-3 rounded-full" style="background:${i.warna}"></span><span class="text-slate-600">${K.esc(i.label)}</span><b class="ml-auto pl-4">${i.nilai} <span class="text-slate-400 font-medium">(${Math.round(i.nilai / tot * 100)}%)</span></b></li>`).join('')}</ul></div>`; this._pasang(el);
  },
  // Awal periode berjalan & periode sebelumnya. hari = hari ini, minggu = Senin sampai hari ini, bulan = tanggal 1 bulan ini sampai hari ini
  _periode(r) {
    const n = new Date(), y = n.getFullYear(), m = n.getMonth(), D = 864e5, h0 = new Date(y, m, n.getDate()).getTime();
    if (r === 'hari') return { s: h0, ps: h0 - D }; if (r === 'minggu') { const s = h0 - ((n.getDay() + 6) % 7) * D; return { s, ps: s - 7 * D }; }
    if (r === 'bulan') return { s: new Date(y, m, 1).getTime(), ps: new Date(y, m - 1, 1).getTime() }; return null;
  },
  // Bandingkan periode berjalan dengan periode sebelumnya pada rentang waktu yang sama panjang
  banding(items, r, nilai) {
    const p = this._periode(r); if (!p) return null; const el = Date.now() - p.s, jum = (a, b) => items.filter(i => i.t >= a && i.t < b).reduce((x, i) => x + nilai(i), 0);
    return { now: jum(p.s, p.s + el + 1), prev: jum(p.ps, p.ps + el) };
  },
  seri(items, rentang, nilai) {
    const now = new Date(), y = now.getFullYear(), m = now.getMonth(), D = 864e5, h0 = new Date(y, m, now.getDate()).getTime(), b = [];
    if (rentang === 'hari') for (let i = 0; i < 24; i++) b.push({ l: String(i).padStart(2, '0') + ':00', s: h0 + i * 36e5, e: h0 + (i + 1) * 36e5 });
    else if (rentang === 'minggu') { const s0 = this._periode('minggu').s; for (let i = 0; i < 7; i++) { const s = s0 + i * D; b.push({ l: new Date(s).toLocaleDateString('id-ID', { weekday: 'short' }), s, e: s + D }); } }
    else if (rentang === 'bulan') { const dim = new Date(y, m + 1, 0).getDate(); for (let i = 1; i <= dim; i++) b.push({ l: String(i), s: new Date(y, m, i).getTime(), e: new Date(y, m, i + 1).getTime() }); }
    else { const a = new Date(items.length ? Math.min(...items.map(x => x.t)) : Date.now()), n = Math.min(12, (y - a.getFullYear()) * 12 + m - a.getMonth() + 1);
      for (let i = n - 1; i >= 0; i--) { const s = new Date(y, m - i, 1), e = new Date(y, m - i + 1, 1); b.push({ l: s.toLocaleDateString('id-ID', { month: 'short', year: '2-digit' }), s: s.getTime(), e: e.getTime() }); } }
    return { labels: b.map(x => x.l), data: b.map(x => items.filter(i => i.t >= x.s && i.t < x.e).reduce((a, i) => a + nilai(i), 0)) };
  },
};

/* ---------- Kerangka dashboard (sidebar buka/tutup, navigasi seksi, logout) ---------- */
const Dash = {
  init(render, user) {
    const body = document.body, side = $('#sidebar'), ov = $('#overlay');
    if (localStorage.getItem('tp_side_min') === '1') body.classList.add('side-min');
    const desktop = () => matchMedia('(min-width:1024px)').matches;
    const toggle = () => { if (desktop()) { body.classList.toggle('side-min'); localStorage.setItem('tp_side_min', body.classList.contains('side-min') ? '1' : '0'); } else { side.classList.toggle('open'); ov.classList.toggle('hidden'); } $('#btn-side').setAttribute('aria-expanded', desktop() ? !body.classList.contains('side-min') : side.classList.contains('open')); };
    $('#btn-side').onclick = toggle; ov.onclick = () => { side.classList.remove('open'); ov.classList.add('hidden'); };
    $('#btn-logout').onclick = async () => { if (await Modal.konfirmasi('Keluar dari akun ini?', 'Keluar')) Sesi.keluar(); };
    const tampil = () => {
      const nama = (location.hash.slice(1) || $('.nav-item').dataset.sec); const ada = $$('.sec').some(s => s.id === 'sec-' + nama), n = ada ? nama : $('.nav-item').dataset.sec;
      $$('.sec').forEach(s => s.classList.toggle('hidden', s.id !== 'sec-' + n));
      $$('.nav-item').forEach(a => { const on = a.dataset.sec === n; a.classList.toggle('aktif', on); on ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'); });
      const s = $('#sec-' + n); s.classList.remove('animate-fade-up'); void s.offsetWidth; s.classList.add('animate-fade-up');
      $('#judul').textContent = $(`.nav-item[data-sec="${n}"] .lbl`).textContent; Promise.resolve(render[n] && render[n]()).catch(er => Toast.err(er.message));
      if (!desktop()) { side.classList.remove('open'); ov.classList.add('hidden'); }
    };
    addEventListener('hashchange', tampil); tampil();
    $$('.js-user').forEach(e => e.textContent = user.username); $$('.js-avatar').forEach(e => e.innerHTML = avatar(user, 'w-full h-full'));
  },
  segarkanAvatar(user) { $$('.js-avatar').forEach(e => e.innerHTML = avatar(user, 'w-full h-full')); $$('.js-user').forEach(e => e.textContent = user.username); },
};

/* ---------- Lacak paket (dipakai dashboard customer & admin): cari nomor pesanan atau resi -> linimasa status ----------
   Markup ada di <template id="t-lacak"> dan <template id="t-lacak-form"> pada halaman yang memakainya. */
const Lacak = {
  node(d) {
    const p = d.pesanan, tl = d.timeline, aktif = tl.findLastIndex(x => x.selesai), batal = p.status === 'dibatalkan';
    return T.satu('t-lacak', { ...p, namaStatus: namaStatus(p), kelasStatus: STATUS[p.status][2], batal, adaResi: !!p.resi, tanpaResi: !p.resi,
      ringkas: p.items.map(x => `${x.nama} x${x.qty}`).join(', '), tujuan: p.pengiriman ? `Dikirim ke ${p.pengiriman.penerima}, ${p.pengiriman.alamat}, ${p.pengiriman.kota} ${p.pengiriman.kodePos}` : '',
      timeline: tl.map((x, i) => ({ ...x, no: x.selesai ? (batal && i === tl.length - 1 ? '✕' : '✓') : String(i + 1), waktuTeks: x.selesai ? (x.waktu ? wkt(x.waktu) : '') : 'Menunggu',
        ok: x.selesai, belum: !x.selesai, gagal: x.selesai && batal && i === tl.length - 1, berjalan: i === aktif && !batal && p.status !== 'selesai' })) });
  },
  pasang(root, awal) {
    root.replaceChildren(T.klon('t-lacak-form'));
    const f = $('form', root), inp = $('input', f), err = $('[role=alert]', root), out = $('.hasil', root);
    const cari = async kode => { err.textContent = ''; out.replaceChildren(); if (!kode.trim()) { err.textContent = 'Isi nomor pesanan atau nomor resi.'; return; }
      try { out.append(Lacak.node(await Api.lacak(kode.trim()))); } catch (x) { err.textContent = x.message; } };
    f.onsubmit = e => { e.preventDefault(); cari(inp.value); };
    if (awal) { inp.value = awal; cari(awal); }
  },
};

/* Percakapan di bawah ulasan: balasan pertama admin + balasan lanjutan (admin <-> pemilik ulasan). Memakai <template id="t-balasan"> */
const Balasan = {
  pesan: u => [...(u.balasan ? [{ dari: 'admin', teks: u.balasan.teks, dibuat: u.balasan.dibuat }] : []), ...(u.lanjutan || [])],
  perluAdmin: u => { const p = Balasan.pesan(u); return !p.length || p[p.length - 1].dari === 'customer'; },
  nodes(u, namaPemilik) { return Balasan.pesan(u).map(x => T.satu('t-balasan', { ...x, nama: x.dari === 'admin' ? 'Admin' : namaPemilik, admin: x.dari === 'admin', pelanggan: x.dari !== 'admin' })); },
};

// Penyiapan awal tiap halaman: ikon dari atribut data-ikon
document.addEventListener('DOMContentLoaded', () => ikon());
