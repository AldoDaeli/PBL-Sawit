'use strict';
/* Beranda: data dari API, markup dari <template> di index.html (lihat T di core.js). */
const S = { kat: '', harga: '', rating: 0, urut: 'populer', q: '' };
// Satu sumber data kontak toko: ganti nomor/email di sini saja (nomor WhatsApp format internasional tanpa + / 0 di depan)
const KONTAK = { wa: '6281234567890', waTampil: '+62 812-3456-7890', email: 'halo@sawitku.id', jam: 'Senin–Sabtu, 08.00–17.00 WIB' };
const linkWa = teks => `https://wa.me/${KONTAK.wa}?text=${encodeURIComponent(teks)}`;
const linkEmail = subjek => `mailto:${KONTAK.email}?subject=${encodeURIComponent(subjek)}`;
const FITUR = [['leaf', 'Segar dari kebun', 'Dipilih langsung dan dikirim segar.'], ['shield', 'Garansi hidup', 'Layu dalam 7 hari, kami ganti.'], ['card', 'Bayar lewat Midtrans', 'QRIS atau Virtual Account bank pilihanmu.'], ['msg', 'Konsultasi gratis', 'Tanya cara rawat kapan saja.']];
let PRODUK = [], FAV = [];   // hasil satu kali ambil dari server; disaring di sisi klien

/* Slider dan kartu samping dipilih otomatis dari data produk (bukan id/teks tetap), jadi selalu cocok dengan database. */
const urutBaru = (a, b) => (b.dibuat || 0) - (a.dibuat || 0) || b.id - a.id;
const urutLaris = (a, b) => b.terjual - a.terjual || b.id - a.id;
const urutRating = (a, b) => b.rating - a.rating || b.jumlahUlasan - a.jumlahUlasan || b.terjual - a.terjual;
const urutMurah = (a, b) => a.harga - b.harga || b.id - a.id;
function pilihBeranda() {
  const sedia = PRODUK.filter(p => p.stok > 0), ada = sedia.length ? sedia : PRODUK, pakai = new Set();
  const ambil = (urut, sub, n = 1, ulang = false, syarat = () => true) => ada.slice().sort(urut).filter(p => syarat(p) && (ulang || !pakai.has(p.id))).slice(0, n).map(p => (pakai.add(p.id), { p, sub }));
  const murah = ambil(urutMurah, 'Harga termurah');                                // kartu samping 2: SELALU produk yang benar-benar termurah
  let baru = ambil(urutBaru, 'Baru masuk');                                        // kartu samping 1: produk terbaru (selain yang termurah)
  if (!baru.length && murah.length) baru = ambil(urutBaru, 'Baru masuk', 1, true); // baru 1 produk: kartu tetap tampil
  let slide = [...ambil(urutLaris, 'Paling dicari'), ...ambil(urutRating, 'Rating tertinggi', 1, false, p => p.jumlahUlasan > 0), ...ambil(urutLaris, 'Favorit pembeli')];   // rating tertinggi hanya dari produk yang punya ulasan
  if (!slide.length) slide = ambil(urutLaris, 'Paling dicari', 1, true);          // katalog sangat kecil: boleh berulang
  return { slide, baru: [...baru, ...murah] };
}
const dataKartu = p => ({ ...p, fav: FAV.includes(p.id), habis: p.stok < 1, ada: p.stok >= 1, aksiCart: p.stok < 1 ? 'Stok habis' : 'Tambah ke keranjang' });
function renderKartu(induk, larik) {
  induk.replaceChildren(...larik.map(p => { const e = T.satu('t-kartu', dataKartu(p)); if (p.stok < 1) $('[data-aksi=cart]', e).disabled = true; return e; }));
  Animasi.reveal();
}
function filter() {
  let a = PRODUK.filter(p => (!S.kat || p.kategori === S.kat) && (!S.rating || (p.jumlahUlasan > 0 && p.rating >= S.rating)) && (!S.q || p.nama.toLowerCase().includes(S.q.toLowerCase())));
  if (S.harga) { const [x, y] = S.harga.split('-').map(Number); a = a.filter(p => p.harga >= x && p.harga < y); }
  const u = { populer: (p, q) => q.terjual - p.terjual, murah: (p, q) => p.harga - q.harga, mahal: (p, q) => q.harga - p.harga, rating: (p, q) => q.rating - p.rating || q.jumlahUlasan - p.jumlahUlasan }[S.urut]; return a.sort(u);
}
function renderKatalog() {
  const a = filter(), el = $('#grid-katalog'); $('#jml-hasil').textContent = `${a.length} produk`;
  if (a.length) renderKartu(el, a); else el.replaceChildren(T.satu('t-kosong-katalog', {}));
  $$('[data-rating]').forEach(b => b.classList.toggle('aktif', +b.dataset.rating === S.rating));
}
async function renderAuth() {
  const u = Sesi.user(), c = await Api.jumlahKeranjang().catch(() => 0), b = $('#badge-cart');
  const el = u ? T.satu('t-auth-user', { beranda: Sesi.beranda(u.peran) }) : T.satu('t-auth-masuk', {});
  if (u) $('[data-avatar]', el).innerHTML = avatar(u, 'w-9 h-9');
  $('#area-auth').replaceChildren(el);
  b.textContent = c; b.classList.toggle('hidden', !c); b.classList.toggle('grid', !!c);
  if (!u) { $('#btn-cart').href = '/masuk?next=customer'; $('#btn-fav').href = '/masuk?next=customer'; }
}
function renderSlider() {
  const el = $('#slider'), { slide, baru } = pilihBeranda();
  if (slide.length) {
    const sl = slide.map(({ p, sub }, i) => T.satu('t-slide', { ...p, sub, pertama: i === 0, ringkas: p.deskripsi || p.kategori }));
    const dots = document.createElement('div'); dots.className = 'absolute bottom-5 left-8 md:left-12 flex gap-2 z-10';
    dots.append(...slide.map((_, i) => T.satu('t-dot', { _i: i, no: i + 1, pertama: i === 0 })));
    el.replaceChildren(...sl, dots);
    let i = 0, t; const go = n => { i = (n + slide.length) % slide.length; $$('.slide', el).forEach((s, k) => s.classList.toggle('aktif', k === i)); $$('.dot', el).forEach((d, k) => d.classList.toggle('aktif', k === i)); },
      mulai = () => { clearInterval(t); if (slide.length > 1 && !matchMedia('(prefers-reduced-motion:reduce)').matches) t = setInterval(() => go(i + 1), 6000); };
    el.addEventListener('click', e => { const d = e.target.closest('[data-slide]'); if (d) { go(+d.dataset.slide); mulai(); } }); mulai();
  }
  $('#side-cards').replaceChildren(...baru.map(({ p, sub }) => T.satu('t-kartu-samping', { ...p, sub })));
}
function isiStatis() {
  const f = $('#fitur'); f.replaceChildren(...FITUR.map(([ikon, judul, isi], k) => { const e = T.satu('t-fitur', { ikon, judul, isi }); e.dataset.delay = k * 70; return e; }));
  $('#kontak-wa').href = linkWa('Halo SawitKu, saya ingin bertanya.'); $('#kontak-wa-teks').textContent = KONTAK.waTampil;
  $('#info-kontak').replaceChildren(...[{ ikon: 'phone', teks: KONTAK.waTampil, href: linkWa('Halo SawitKu, saya ingin bertanya.'), aksi: 'Chat WhatsApp' }, { ikon: 'mail', teks: KONTAK.email, href: linkEmail('Pertanyaan untuk SawitKu'), aksi: 'Kirim email' }, { ikon: 'clock', teks: KONTAK.jam }].map(x => T.satu('t-info-kontak', x)));
  $$('#info-kontak a').forEach(a => { if (a.href.startsWith('http')) { a.target = '_blank'; a.rel = 'noopener noreferrer'; } });
  $('#f-kat').replaceChildren(new Option('Semua kategori', ''), ...KATEGORI.map(k => new Option(k, k)));
  $('#menu-kat').replaceChildren(...KATEGORI.map(nama => T.satu('t-menu-kat', { nama })));
}
async function init() {
  isiStatis(); renderKartu($('#grid-terlaris'), PRODUK.filter(p => p.bestSeller).slice(0, 4));
  renderSlider(); renderKatalog(); Animasi.reveal(); await renderAuth();
}
const setKat = k => { S.kat = k; $('#f-kat').value = k; renderKatalog(); $('#menu-kat').classList.add('hidden'); };
document.addEventListener('click', async e => {
  const k = e.target.closest('[data-kat]'); if (k) setKat(k.dataset.kat);
  if (!e.target.closest('#btn-kat')) $('#menu-kat').classList.add('hidden');
  const r = e.target.closest('[data-rating]'); if (r) { S.rating = +r.dataset.rating; renderKatalog(); }
  const a = e.target.closest('[data-aksi]'); if (!a) return;
  try {
    if (!Sesi.user()) { Toast.err('Masuk dulu untuk melanjutkan.'); setTimeout(() => location.href = '/masuk?next=landing', 900); return; }
    const id = +a.dataset.id;
    if (a.dataset.aksi === 'cart') { await Api.kerAdd(id, 1); Toast.ok('Ditambahkan ke keranjang.'); await renderAuth(); $('#badge-cart').classList.add('denyut'); setTimeout(() => $('#badge-cart').classList.remove('denyut'), 400); }
    if (a.dataset.aksi === 'fav') { const on = await Api.favToggle(id); on ? FAV.push(id) : FAV = FAV.filter(x => x !== id); $$(`[data-aksi="fav"][data-id="${id}"]`).forEach(b => { b.classList.toggle('fav-aktif', on); b.setAttribute('aria-pressed', on); }); Toast.ok(on ? 'Masuk ke favorit.' : 'Dihapus dari favorit.'); }
  } catch (er) { Toast.err(er.message); }
});
$('#btn-kat').onclick = e => { e.stopPropagation(); const m = $('#menu-kat'); m.classList.toggle('hidden'); e.currentTarget.setAttribute('aria-expanded', !m.classList.contains('hidden')); };
$('#btn-menu').onclick = () => $('#nav-mobile').classList.toggle('hidden');
$('#form-cari').onsubmit = e => { e.preventDefault(); S.q = $('#cari').value.trim().slice(0, 60); renderKatalog(); $('#katalog').scrollIntoView(); };
$('#f-kat').onchange = e => { S.kat = e.target.value; renderKatalog(); }; $('#f-harga').onchange = e => { S.harga = e.target.value; renderKatalog(); };
$('#f-urut').onchange = e => { S.urut = e.target.value; renderKatalog(); };
$('#f-reset').onclick = () => { Object.assign(S, { kat: '', harga: '', rating: 0, urut: 'populer', q: '' }); ['f-kat', 'f-harga', 'cari'].forEach(i => $('#' + i).value = ''); $('#f-urut').value = 'populer'; renderKatalog(); };
$('#form-kontak').onsubmit = async e => {
  e.preventDefault(); const err = $('#k-err'); err.textContent = '';
  try { await Api.kirimPesan({ nama: $('#k-nama').value, email: $('#k-email').value.trim(), jenis: $('#k-jenis').value, isi: $('#k-isi').value }); e.target.reset(); Toast.ok('Pesan terkirim. Terima kasih!'); }
  catch (er) { err.textContent = er.message; }
};
function pasangChatKontak() {
  const u = Sesi.user(), form = $('#form-kontak');
  if (u && u.peran === 'customer') {        // pelanggan login: formulir diganti chat langsung dengan admin
    const kotak = T.satu('t-chat-kotak', {}); form.replaceWith(kotak);
    Chat.pasang($('[data-chat]', kotak), { saya: 'customer', muat: p => Api.chat(p), kirim: isi => Api.chatKirim(isi) });
  } else form.append(T.satu('t-ajak-masuk', {}));   // tamu: formulir tetap ada + ajakan masuk untuk chat
}
(async () => {
  await Sesi.segarkan();   // buang cache sesi yang sudah tidak berlaku di server
  pasangChatKontak();
  try { [PRODUK, FAV] = await Promise.all([Api.produk(), Api.favorit().catch(() => [])]); await init(); }
  catch (er) { $('#grid-katalog').replaceChildren(T.satu('t-gagal', { pesan: 'Gagal memuat produk: ' + er.message })); isiStatis(); }
})();
// Masuk/keluar di tab lain: muat ulang agar tombol akun, keranjang, dan chat ikut berubah
document.addEventListener('sesi-berubah', () => location.reload());

// Tombol kembali ke atas: muncul setelah menggulir
(() => { const b = document.getElementById('ke-atas'); if (!b) return; const cek = () => { const turun = scrollY > 600; b.classList.toggle('hidden', !turun); b.classList.toggle('grid', turun); };
  addEventListener('scroll', cek, { passive: true }); cek(); b.onclick = () => scrollTo({ top: 0, behavior: 'smooth' }); })();
