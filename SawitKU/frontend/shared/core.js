'use strict';
/* ===== Inti bersama: konfigurasi, keamanan, sesi, API (REST ke backend Flask), UI, grafik, kerangka dashboard =====
   Semua fungsi Api bersifat asinkron (return Promise): panggil dengan `await`. */
const ROOT = '/';   // semua tautan memakai URL pendek dari akar situs: /masuk, /daftar, /dashboard, /admin, /produk/<id>
const CFG = { SESI_MENIT: 20, MAKS_GAGAL: 5, BLOKIR_MENIT: 5, BATAS_BAYAR_JAM: 24, MAKS_MB: 2 };
const KATEGORI = ['Tanaman Hias Daun', 'Tanaman Berbunga', 'Sukulen & Kaktus', 'Tanaman Gantung', 'Pot & Media Tanam', 'Perawatan'];   // sama dengan backend (app/config.py)
const NEXT = { landing: '', customer: 'dashboard', admin: 'admin' };   // dipakai sebagai ROOT + NEXT[x]
const STATUS = {
  menunggu_bayar: ['Menunggu Pembayaran', 'proses', 'bg-amber-100 text-amber-700'],
  menunggu_verifikasi: ['Menunggu Verifikasi', 'proses', 'bg-sky-100 text-sky-700'],
  diproses: ['Sedang Dikemas', 'proses', 'bg-indigo-100 text-indigo-700'],
  dikirim: ['Dalam Pengiriman', 'proses', 'bg-violet-100 text-violet-700'],
  selesai: ['Selesai', 'selesai', 'bg-brand-100 text-brand-700'],
  dibatalkan: ['Dibatalkan', 'batal', 'bg-rose-100 text-rose-700'],
};

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
};

/* ---------- Sesi & RBAC ----------
   Token Bearer dari server disimpan di sessionStorage (hilang saat tab ditutup). `user` hanya cache untuk tampilan;
   kebenaran dan hak akses selalu diputuskan server. Server memperpanjang sesi (sliding) di setiap permintaan. */
const Sesi = {
  KEY: 'tp_sesi',
  baca() { try { const s = JSON.parse(sessionStorage.getItem(this.KEY)); if (s && s.token && s.user) return s; } catch {} sessionStorage.removeItem(this.KEY); return null; },
  token() { const s = this.baca(); return s ? s.token : null; },
  user() { const s = this.baca(); return s ? s.user : null; },
  mulai(token, user) { sessionStorage.setItem(this.KEY, JSON.stringify({ token, user })); },
  simpanUser(user) { const s = this.baca(); if (s) { s.user = user; sessionStorage.setItem(this.KEY, JSON.stringify(s)); } },
  hapus() { sessionStorage.removeItem(this.KEY); },
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
    if (!this.user()) { location.replace(ROOT + 'masuk?next=' + peran); return null; }
    let u; try { u = await Api.saya(); } catch (e) { if (e.status !== 401) Toast.err(e.message); return null; }   // 401 -> Api sudah mengalihkan ke login
    if (u.peran !== peran) { location.replace(this.beranda(u.peran)); return null; }
    let aktifTerakhir = Date.now(), ping = Date.now();
    ['click', 'keydown', 'mousemove', 'touchstart'].forEach(e => addEventListener(e, () => {
      aktifTerakhir = Date.now();
      if (Date.now() - ping > 120000) { ping = Date.now(); Api.saya(true).catch(() => {}); }   // jaga sesi server tetap hidup selama pengguna aktif
    }, { passive: true }));
    setInterval(() => { if (Date.now() - aktifTerakhir > CFG.SESI_MENIT * 60000) this.keluar(true); }, 15000);
    return u;
  },
};

/* ---------- API (REST ke backend Flask; satu fungsi = satu endpoint) ---------- */
const API_BASE = '/api';   // frontend dilayani Flask dari origin yang sama
const qs = p => { const q = new URLSearchParams(Object.entries(p || {}).filter(([, v]) => v)).toString(); return q ? '?' + q : ''; };
const Api = {
  async _req(method, path, body, { diam } = {}) {
    const h = { Accept: 'application/json' }, t = Sesi.token();
    if (t) h.Authorization = 'Bearer ' + t;
    if (body !== undefined) h['Content-Type'] = 'application/json';
    let r, j = null;
    try { r = await fetch(API_BASE + path, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) }); }
    catch { throw new Error('Tidak dapat terhubung ke server. Coba lagi nanti.'); }
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
  checkout: a => Api._req('POST', '/checkout', a),   // a = {penerima, telepon, alamat, kota, kodePos, simpan}; harga & stok dihitung server
  pesananSaya: () => Api._req('GET', '/pesanan/saya'),
  bayar: (id, bukti) => Api._req('POST', `/pesanan/${id}/bayar`, { bukti }),
  batal: id => Api._req('POST', `/pesanan/${id}/batal`),
  terima: id => Api._req('POST', `/pesanan/${id}/terima`),
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
  lacak: kode => Api._req('GET', '/lacak?kode=' + encodeURIComponent(kode)),
  midtransBuat: id => Api._req('POST', `/pesanan/${id}/midtrans`),
  midtransCek: id => Api._req('POST', `/pesanan/${id}/midtrans/cek`),
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

/* ---------- UI ---------- */
const rp = n => 'Rp' + Math.round(n).toLocaleString('id-ID');
const tgl = (t, pendek) => new Date(t).toLocaleDateString('id-ID', pendek ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' });
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const PATH = {
  home: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10', cart: 'M9 21h.01 M20 21h.01 M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6',
  heart: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21.2l7.8-7.7 1-1.1a5.5 5.5 0 0 0 0-7.8z',
  user: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
  users: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M23 21v-2a4 4 0 0 0-3-3.9 M16 3.1a4 4 0 0 1 0 7.8',
  box: 'M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z M3.3 7L12 12l8.7-5 M12 22V12',
  chart: 'M18 20V10 M12 20V4 M6 20v-6', out: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9', menu: 'M3 12h18 M3 6h18 M3 18h18',
  search: 'M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16z M21 21l-4.3-4.3', check: 'M20 6L9 17l-5-5', x: 'M18 6L6 18 M6 6l12 12', plus: 'M12 5v14 M5 12h14',
  star: 'M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.9L12 17.8 5.8 21l1.2-6.9-5-4.9 6.9-1z', card: 'M3 4h18a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M1 10h22',
  msg: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z', edit: 'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7 M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z',
  trash: 'M3 6h18 M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6 M10 11v6 M14 11v6 M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2',
  phone: 'M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z',
  lock: 'M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z M7 11V7a5 5 0 0 1 10 0v4', mail: 'M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M22 6l-10 7L2 6',
  eye: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
  leaf: 'M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10z M2 21c0-3 1.9-5.4 5.1-6C9.5 14.5 12 13 13 12',
  clock: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z M12 6v6l4 2', upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', trend: 'M23 6l-9.5 9.5-5-5L1 18 M17 6h6v6', chev: 'M6 9l6 6 6-6', truck: 'M1 3h15v13H1z M16 8h4l3 3v5h-7z M5.5 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4z M18.5 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
};
const I = (n, c = 'w-5 h-5') => `<svg class="${c} shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${PATH[n] || ''}"/></svg>`;
const bintang = r => { const p = Math.round(r); return `<span class="text-sun-500 tracking-tight" aria-label="Rating ${r} dari 5">${'★'.repeat(p)}<span class="text-slate-300">${'★'.repeat(5 - p)}</span></span>`; };
const avatar = (u, c = 'w-10 h-10') => u.foto && K.url(u.foto) ? `<img src="${K.url(u.foto)}" alt="" class="${c} rounded-full object-cover">` : `<span class="${c} rounded-full bg-brand-600 text-white grid place-items-center font-bold uppercase shrink-0">${K.esc(u.username[0])}</span>`;
const badgeStatus = s => `<span class="px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS[s][2]}">${STATUS[s][0]}</span>`;

const Toast = {
  tampil(pesan, tipe = 'ok') {
    let w = $('#toast-w'); if (!w) { w = document.createElement('div'); w.id = 'toast-w'; w.className = 'fixed top-4 right-4 z-[100] flex flex-col gap-2 w-[min(92vw,340px)]'; document.body.append(w); }
    const t = document.createElement('div'), warna = tipe === 'err' ? 'border-rose-400 text-rose-700' : 'border-brand-500 text-brand-800';
    t.className = `animate-slide-in bg-white shadow-xl rounded-xl border-l-4 ${warna} px-4 py-3 text-sm font-medium flex gap-2 items-start`;
    t.setAttribute('role', 'status'); t.innerHTML = `<span>${tipe === 'err' ? '✕' : '✓'}</span><span>${K.esc(pesan)}</span>`; w.append(t);
    setTimeout(() => { t.style.transition = 'opacity .3s'; t.style.opacity = 0; setTimeout(() => t.remove(), 300); }, 3200);
  },
  ok: m => Toast.tampil(m), err: m => Toast.tampil(m, 'err'),
};
const Modal = {
  buka(html, lebar = 'max-w-lg') {
    const m = document.createElement('div'); m.className = 'fixed inset-0 z-[90] grid place-items-center p-4 animate-fade-in';
    m.innerHTML = `<div data-tutup class="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"></div><div class="relative bg-white rounded-2xl shadow-2xl w-full ${lebar} max-h-[90vh] overflow-y-auto animate-pop" role="dialog" aria-modal="true">${html}</div>`;
    const tutup = () => { m.remove(); removeEventListener('keydown', esc); }, esc = e => e.key === 'Escape' && tutup();
    m.addEventListener('click', e => { if (e.target.closest('[data-tutup]')) tutup(); }); addEventListener('keydown', esc); document.body.append(m); m.tutup = tutup; return m;
  },
  konfirmasi(pesan, tombol = 'Ya, lanjutkan') {
    return new Promise(ok => { const m = this.buka(`<div class="p-6"><p class="font-semibold text-slate-800">${K.esc(pesan)}</p><div class="flex justify-end gap-2 mt-6"><button data-tutup class="px-4 py-2 rounded-xl text-sm font-semibold bg-slate-100 hover:bg-slate-200">Batal</button><button id="mk-ya" class="px-4 py-2 rounded-xl text-sm font-semibold bg-brand-600 text-white hover:bg-brand-700">${K.esc(tombol)}</button></div></div>`, 'max-w-sm');
      $('#mk-ya', m).onclick = () => { m.tutup(); ok(true); }; m.addEventListener('click', e => e.target.closest('[data-tutup]') && ok(false)); });
  },
};
// Gambar rusak diganti placeholder (tanpa atribut onerror inline agar sesuai CSP)
document.addEventListener('error', e => { const t = e.target; if (t.tagName === 'IMG' && !t.dataset.gagal) { t.dataset.gagal = 1; t.src = 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"><rect width="400" height="400" fill="#dcf1e1"/><path d="M200 300c-40-20-60-60-50-110 30 0 60 20 70 50 10-40 40-70 80-80 10 60-20 120-100 140z" fill="#5ab37c"/></svg>'); } }, true);
const Animasi = {
  reveal() { const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('tampil'); io.unobserve(e.target); } }), { threshold: .12 });
    $$('[data-reveal]:not(.tampil)').forEach((el, i) => { el.style.transitionDelay = (el.dataset.delay || 0) + 'ms'; io.observe(el); }); },
  hitung(el, akhir, fmt = v => Math.round(v).toLocaleString('id-ID'), dur = 900) {
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
  bar(el, labels, seri) {
    const W = 640, H = 260, L = 50, B = 28, T = 12, all = seri.flatMap(s => s.data), { top, t } = this.skala(all), n = labels.length, gw = (W - L - 8) / n, bw = Math.min(26, gw / (seri.length + .6));
    let g = this._sumbu(top, t, L, W, H, T, B) + this._label(labels, i => L + gw * i + gw / 2, H);
    labels.forEach((l, i) => seri.forEach((s, j) => { const v = s.data[i]; if (!v) return; const h = (H - T - B) * v / top, x = L + gw * i + gw / 2 - bw * seri.length / 2 + j * bw;
      g += `<rect class="bar" x="${x}" y="${H - B - h}" width="${Math.max(bw - 2, 3)}" height="${h}" rx="3" fill="${s.warna}" style="animation-delay:${i * 25 + j * 40}ms"><title>${K.esc(l)} - ${K.esc(s.nama)}: ${v.toLocaleString('id-ID')}</title></rect>`; }));
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="w-full h-auto" role="img">${g}${all.some(Boolean) ? '' : this._kosong(W, H)}</svg>`;
  },
  area(el, labels, data, warna = '#38995e') {
    const W = 640, H = 240, L = 50, B = 28, T = 14, { top, t } = this.skala(data), n = labels.length, sx = i => L + (W - L - 14) * (n === 1 ? .5 : i / (n - 1)), sy = v => T + (H - T - B) * (1 - v / top);
    const d = 'M' + data.map((v, i) => `${sx(i)},${sy(v)}`).join(' L'), g = this._sumbu(top, t, L, W, H, T, B) + this._label(labels, sx, H), pts = n <= 16;
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="w-full h-auto" role="img"><defs><linearGradient id="ga${warna.slice(1)}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${warna}" stop-opacity=".35"/><stop offset="1" stop-color="${warna}" stop-opacity="0"/></linearGradient></defs>${g}
      <path class="area" d="${d} L${sx(n - 1)},${H - B} L${sx(0)},${H - B}Z" fill="url(#ga${warna.slice(1)})"/><path class="garis" pathLength="1" d="${d}" fill="none" stroke="${warna}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      ${data.map((v, i) => (pts || v) ? `<circle class="titik" cx="${sx(i)}" cy="${sy(v)}" r="${pts ? 4 : 3}" fill="#fff" stroke="${warna}" stroke-width="2.5" style="animation-delay:${500 + i * 25}ms"><title>${K.esc(labels[i])}: ${v.toLocaleString('id-ID')}</title></circle>` : '').join('')}${data.some(Boolean) ? '' : this._kosong(W, H)}</svg>`;
  },
  donut(el, items) {
    const tot = items.reduce((a, i) => a + i.nilai, 0) || 1; let off = 0;
    const arc = items.map((i, k) => { const p = i.nilai / tot * 100, s = p ? `<circle class="arc" r="15.9" cx="21" cy="21" fill="none" stroke="${i.warna}" stroke-width="6" pathLength="100" stroke-dasharray="${Math.max(p - 1, 0)} ${100 - Math.max(p - 1, 0)}" stroke-dashoffset="${-off}" style="animation-delay:${k * 150}ms"/>` : ''; off += p; return s; }).join('');
    el.innerHTML = `<div class="flex items-center gap-6 flex-wrap justify-center"><svg viewBox="0 0 42 42" class="w-40 h-40 -rotate-90">${arc}</svg><ul class="space-y-2 text-sm">${items.map(i => `<li class="flex items-center gap-2"><span class="w-3 h-3 rounded-full" style="background:${i.warna}"></span><span class="text-slate-600">${K.esc(i.label)}</span><b class="ml-auto pl-4">${i.nilai} <span class="text-slate-400 font-medium">(${Math.round(i.nilai / tot * 100)}%)</span></b></li>`).join('')}</ul></div>`;
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
// Pola QR (simulasi visual QRIS; bukan QR sungguhan)
const QR = seed => { let s = seed * 9301 + 49297, r = () => (s = (s * 9301 + 49297) % 233280) / 233280, n = 25, c = '', f = (x, y) => (x < 8 && y < 8) || (x > 16 && y < 8) || (x < 8 && y > 16);
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (!f(x, y) && r() > .5) c += `<rect x="${x}" y="${y}" width="1" height="1"/>`;
  const fp = (x, y) => `<rect x="${x}" y="${y}" width="7" height="7" fill="none" stroke="#111" stroke-width="1"/><rect x="${x + 2}" y="${y + 2}" width="3" height="3"/>`;
  return `<svg viewBox="-1 -1 27 27" class="w-full h-full" fill="#111" shape-rendering="crispEdges">${c}${fp(.5, .5)}${fp(17.5, .5)}${fp(.5, 17.5)}</svg>`; };

/* ---------- Lacak paket (dipakai dashboard customer & admin): cari nomor pesanan atau resi -> linimasa status ---------- */
const Lacak = {
  html(d) {
    const p = d.pesanan, tl = d.timeline, aktif = tl.findLastIndex(x => x.selesai), batal = p.status === 'dibatalkan';
    const w = t => t ? new Date(t).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }) : 'Menunggu';
    return `<div class="panel space-y-4"><div class="flex flex-wrap justify-between gap-2 items-start"><div><b class="text-lg">Pesanan #${p.id}</b><p class="text-sm text-slate-500">${p.resi ? `${K.esc(p.kurir)} &middot; Resi <b class="text-slate-800 select-all">${K.esc(p.resi)}</b>` : 'Nomor resi belum tersedia (menunggu dikirim)'}</p></div>${badgeStatus(p.status)}</div>
      <ol class="relative ml-3 border-l-2 ${batal ? 'border-rose-200' : 'border-brand-100'} space-y-5 py-1">${tl.map((x, i) => `<li class="pl-6 relative"><span class="absolute -left-[13px] top-0 w-6 h-6 rounded-full grid place-items-center text-[11px] font-bold ${x.selesai ? (batal && i === tl.length - 1 ? 'bg-rose-500 text-white' : 'bg-brand-600 text-white') : 'bg-slate-200 text-slate-400'} ${i === aktif && !batal && p.status !== 'selesai' ? 'ring-4 ring-brand-100' : ''}">${x.selesai ? (batal && i === tl.length - 1 ? '✕' : '✓') : i + 1}</span>
        <p class="font-semibold text-sm ${x.selesai ? '' : 'text-slate-400'}">${K.esc(x.label)}</p><p class="text-xs text-slate-500">${x.selesai ? (x.waktu ? w(x.waktu) : '') : 'Menunggu'}</p></li>`).join('')}</ol>
      <div class="text-sm text-slate-600 border-t border-slate-100 pt-3">${p.items.map(x => `${K.esc(x.nama)} x${x.qty}`).join(', ')}${p.pengiriman ? `<p class="mt-1 text-xs text-slate-500">Dikirim ke <b>${K.esc(p.pengiriman.penerima)}</b>, ${K.esc(p.pengiriman.alamat)}, ${K.esc(p.pengiriman.kota)} ${K.esc(p.pengiriman.kodePos)}</p>` : ''}</div></div>`;
  },
  pasang(root, awal) {
    root.innerHTML = `<form class="panel flex flex-col sm:flex-row gap-3 max-w-2xl" novalidate><input class="in flex-1" maxlength="40" placeholder="Nomor pesanan (mis. 12) atau nomor resi" aria-label="Nomor pesanan atau resi" autocomplete="off"><button class="btn btn-p">Lacak Paket</button></form><p class="text-sm text-rose-600 min-h-5 mt-2" role="alert"></p><div class="hasil max-w-2xl mt-2"></div>`;
    const f = $('form', root), inp = $('input', f), err = $('[role=alert]', root), out = $('.hasil', root);
    const cari = async kode => { err.textContent = ''; out.innerHTML = ''; if (!kode.trim()) { err.textContent = 'Isi nomor pesanan atau nomor resi.'; return; }
      try { out.innerHTML = Lacak.html(await Api.lacak(kode.trim())); } catch (x) { err.textContent = x.message; } };
    f.onsubmit = e => { e.preventDefault(); cari(inp.value); };
    if (awal) { inp.value = awal; cari(awal); }
  },
};

/* Percakapan di bawah ulasan: balasan pertama admin + balasan lanjutan (admin <-> pemilik ulasan) */
const Balasan = {
  pesan: u => [...(u.balasan ? [{ dari: 'admin', teks: u.balasan.teks, dibuat: u.balasan.dibuat }] : []), ...(u.lanjutan || [])],
  perluAdmin: u => { const p = Balasan.pesan(u); return !p.length || p[p.length - 1].dari === 'customer'; },
  html(u, namaPemilik) {
    return Balasan.pesan(u).map(x => x.dari === 'admin'
      ? `<div class="mt-3 rounded-xl bg-brand-50 border-l-4 border-brand-500 px-3 py-2 text-sm"><b class="text-brand-700 text-xs">Admin &middot; ${tgl(x.dibuat)}</b><p class="text-slate-600 mt-0.5">${K.esc(x.teks)}</p></div>`
      : `<div class="mt-3 ml-6 rounded-xl bg-slate-50 border-l-4 border-sun-400 px-3 py-2 text-sm"><b class="text-slate-600 text-xs">${K.esc(namaPemilik)} &middot; ${tgl(x.dibuat)}</b><p class="text-slate-600 mt-0.5">${K.esc(x.teks)}</p></div>`).join('');
  },
};
