'use strict';
const S = { kat: '', harga: '', rating: 0, urut: 'populer', q: '' };
// Satu sumber data kontak toko: ganti nomor/email di sini saja (nomor WhatsApp format internasional tanpa + / 0 di depan)
const KONTAK = { wa: '6281234567890', waTampil: '+62 812-3456-7890', email: 'halo@sawitku.id', jam: 'Senin–Sabtu, 08.00–17.00 WIB' };
const linkWa = teks => `https://wa.me/${KONTAK.wa}?text=${encodeURIComponent(teks)}`;
const linkEmail = subjek => `mailto:${KONTAK.email}?subject=${encodeURIComponent(subjek)}`;
let PRODUK = [], FAV = [];   // hasil satu kali ambil dari server; disaring di sisi klien
/* Slider dan kartu samping dipilih otomatis dari data produk (bukan id/teks tetap), jadi selalu cocok dengan database. */
const urutBaru = (a, b) => (b.dibuat || 0) - (a.dibuat || 0) || b.id - a.id;
const urutLaris = (a, b) => b.terjual - a.terjual || b.id - a.id;
const urutRating = (a, b) => b.rating - a.rating || b.terjual - a.terjual;
const urutMurah = (a, b) => a.harga - b.harga || b.id - a.id;
function pilihBeranda() {
  const sedia = PRODUK.filter(p => p.stok > 0), ada = sedia.length ? sedia : PRODUK, pakai = new Set();
  const ambil = (urut, sub, n = 1, ulang = false) => ada.slice().sort(urut).filter(p => ulang || !pakai.has(p.id)).slice(0, n).map(p => (pakai.add(p.id), { p, sub }));
  const murah = ambil(urutMurah, 'Harga Termurah');                                // kartu samping 2: SELALU produk yang benar-benar termurah
  let baru = ambil(urutBaru, 'Baru Masuk');                                        // kartu samping 1: produk terbaru (selain yang termurah)
  if (!baru.length && murah.length) baru = ambil(urutBaru, 'Baru Masuk', 1, true); // baru 1 produk: kartu tetap tampil
  let slide = [...ambil(urutLaris, 'Paling Dicari'), ...ambil(urutRating, 'Rating Tertinggi'), ...ambil(urutLaris, 'Favorit Pembeli')];
  if (!slide.length) slide = ambil(urutLaris, 'Paling Dicari', 1, true);          // katalog sangat kecil: boleh berulang
  return { slide, baru: [...baru, ...murah] };
}
const kartu = p => {
  const fav = FAV.includes(p.id), habis = p.stok < 1;
  return `<article class="kartu group bg-white rounded-2xl border border-slate-100 overflow-hidden flex flex-col" data-reveal>
    <div class="relative aspect-square overflow-hidden bg-brand-50"><a href="/produk/${p.id}" aria-label="${K.esc(p.nama)}"><img src="${K.url(p.gambar)}" alt="${K.esc(p.nama)}" loading="lazy" class="w-full h-full object-cover"></a>
      ${p.bestSeller ? '<span class="absolute top-3 left-3 px-2.5 py-1 rounded-full bg-sun-400 text-brand-900 text-[11px] font-bold">Terlaris</span>' : ''}
      <button data-aksi="fav" data-id="${p.id}" class="absolute top-3 right-3 w-9 h-9 rounded-full bg-white/90 grid place-items-center text-slate-500 hover:text-rose-500 transition ${fav ? 'fav-aktif' : ''}" aria-label="Favorit" aria-pressed="${fav}">${I('heart', 'w-[18px] h-[18px]')}</button></div>
    <div class="p-4 flex flex-col flex-1"><p class="text-[11px] font-semibold text-brand-600 uppercase tracking-wide">${K.esc(p.kategori)}</p>
      <a href="/produk/${p.id}" class="font-bold leading-snug mt-1 hover:text-brand-700 line-clamp-2">${K.esc(p.nama)}</a>
      <div class="flex items-center gap-2 text-xs mt-1.5">${bintang(p.rating)}<span class="text-slate-500">${p.rating} &middot; ${p.terjual} terjual</span></div>
      <div class="mt-auto pt-3 flex items-center justify-between gap-2"><b class="text-brand-700 text-lg">${rp(p.harga)}</b>
        <button data-aksi="cart" data-id="${p.id}" ${habis ? 'disabled' : ''} class="w-10 h-10 rounded-xl grid place-items-center bg-brand-600 text-white hover:bg-brand-700 disabled:bg-slate-200 disabled:text-slate-400 transition active:scale-90" aria-label="${habis ? 'Stok habis' : 'Tambah ke keranjang'}">${habis ? '–' : I('plus')}</button></div></div></article>`;
};
function filter() {
  let a = PRODUK.filter(p => (!S.kat || p.kategori === S.kat) && p.stok >= 0 && p.rating >= S.rating && (!S.q || p.nama.toLowerCase().includes(S.q.toLowerCase())));
  if (S.harga) { const [x, y] = S.harga.split('-').map(Number); a = a.filter(p => p.harga >= x && p.harga < y); }
  const u = { populer: (p, q) => q.terjual - p.terjual, murah: (p, q) => p.harga - q.harga, mahal: (p, q) => q.harga - p.harga, rating: (p, q) => q.rating - p.rating }[S.urut]; return a.sort(u);
}
function renderKatalog() {
  const a = filter(); $('#jml-hasil').textContent = `${a.length} produk`;
  $('#grid-katalog').innerHTML = a.length ? a.map(kartu).join('') : `<p class="col-span-full text-center text-slate-500 py-16">Produk tidak ditemukan. Coba ubah filter pencarian.</p>`;
  Animasi.reveal();
}
async function renderAuth() {
  const u = Sesi.user(), c = await Api.jumlahKeranjang().catch(() => 0), b = $('#badge-cart');
  $('#area-auth').innerHTML = u ? `<a href="${Sesi.beranda(u.peran)}" class="flex items-center gap-2 h-11 pl-1 pr-4 rounded-xl bg-brand-50 hover:bg-brand-100 text-sm font-semibold text-brand-800 transition">${avatar(u, 'w-9 h-9')}<span class="hidden sm:inline">Dashboard</span></a>`
    : `<a href="/masuk?next=landing" class="h-11 px-5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-bold grid place-items-center transition">Masuk</a>`;
  b.textContent = c; b.classList.toggle('hidden', !c); b.classList.toggle('grid', !!c);
  if (!u) { $('#btn-cart').href = '/masuk?next=customer'; $('#btn-fav').href = '/masuk?next=customer'; }
}
function renderSlider() {
  const el = $('#slider'), { slide: SLIDE, baru } = pilihBeranda();
  if (SLIDE.length) el.innerHTML = SLIDE.map(({ p, sub }, i) =>
    `<div class="slide ${i ? '' : 'aktif'}"><div class="absolute inset-0 bg-[radial-gradient(circle_at_75%_50%,#bbe3c6,transparent_60%)]"></div>
    <div class="relative h-full grid md:grid-cols-2 items-center gap-4 p-8 md:p-12"><div class="s-teks"><p class="text-brand-600 font-bold">${sub}</p><h1 class="text-3xl md:text-5xl font-extrabold leading-tight mt-2">${K.esc(p.nama)}</h1><p class="text-slate-600 mt-3 max-w-sm line-clamp-3">${K.esc(p.deskripsi || p.kategori)}</p>
      <a href="/produk/${p.id}" class="inline-flex items-center gap-2 mt-6 h-12 px-6 rounded-full bg-brand-600 hover:bg-brand-700 text-white font-bold transition">Lihat Produk ${I('chev', 'w-4 h-4 -rotate-90')}</a></div>
      <div class="hidden md:block"><div class="aspect-square max-w-xs ml-auto rounded-full overflow-hidden ring-8 ring-white shadow-2xl"><img class="s-gambar w-full h-full object-cover" src="${K.url(p.gambar)}" alt="${K.esc(p.nama)}"></div></div></div></div>`).join('')
    + `<div class="absolute bottom-5 left-8 md:left-12 flex gap-2 z-10">${SLIDE.map((_, i) => `<button class="dot ${i ? '' : 'aktif'}" data-slide="${i}" aria-label="Slide ${i + 1}"></button>`).join('')}</div>`;
  let i = 0, t; if (SLIDE.length) { const go = n => { i = (n + SLIDE.length) % SLIDE.length; $$('.slide', el).forEach((s, k) => s.classList.toggle('aktif', k === i)); $$('.dot', el).forEach((d, k) => d.classList.toggle('aktif', k === i)); },
    mulai = () => { clearInterval(t); t = setInterval(() => go(i + 1), 5500); };
  el.addEventListener('click', e => { const d = e.target.closest('[data-slide]'); if (d) { go(+d.dataset.slide); mulai(); } }); mulai(); }
  $('#side-cards').innerHTML = baru.map(({ p, sub }) => `<a href="/produk/${p.id}" class="group relative overflow-hidden rounded-3xl bg-brand-50 p-6 flex items-center min-h-[180px] hover:bg-brand-100 transition"><div class="relative z-10 w-3/5"><p class="text-xs font-bold text-brand-600 uppercase tracking-wide">${sub}</p><h3 class="text-xl font-extrabold text-brand-700 mt-1 line-clamp-2">${K.esc(p.nama)}</h3><p class="mt-2 font-bold">${rp(p.harga)}</p><span class="inline-block mt-3 text-sm font-semibold text-brand-700 border border-brand-600 rounded-full px-4 py-1.5 group-hover:bg-brand-600 group-hover:text-white transition">Lihat Produk</span></div><img class="absolute right-0 top-0 h-full w-2/5 object-cover [mask-image:linear-gradient(to_left,#000_60%,transparent)] group-hover:scale-105 transition duration-500" src="${K.url(p.gambar)}" alt=""></a>`).join('');
}
async function init() {
  $('#logo-ikon').innerHTML = I('leaf', 'w-6 h-6'); $('#btn-cari').innerHTML = I('search'); $('#ikon-cart').innerHTML = I('cart', 'w-[22px] h-[22px]'); $('#btn-fav').insertAdjacentHTML('afterbegin', I('heart', 'w-[22px] h-[22px]'));
  $('#btn-menu').innerHTML = I('menu'); $('#ikon-kat').innerHTML = I('menu', 'w-4 h-4'); $('#ikon-tel').innerHTML = I('phone', 'w-6 h-6');
  [['shield', 'Tanaman Sehat Bergaransi'], ['truck', 'Packing Aman ke Seluruh Indonesia'], ['leaf', 'Garansi Hidup 7 Hari']].forEach(([i, t], k) => $('#strip-' + (k + 1)).innerHTML = I(i, 'w-4 h-4') + t);
  $('#fitur').innerHTML = [['leaf', 'Segar dari Kebun', 'Dipilih langsung dan dikirim segar.'], ['shield', 'Garansi Hidup', 'Layu dalam 7 hari, kami ganti.'], ['card', 'Bayar via QRIS', 'Semua e-wallet dan mobile banking.'], ['msg', 'Konsultasi Gratis', 'Tanya cara rawat kapan saja.']]
    .map(([i, t, d], k) => `<div data-reveal data-delay="${k * 80}" class="rounded-2xl border border-slate-100 p-5 hover:border-brand-300 hover:shadow-lg transition"><div class="w-11 h-11 rounded-xl bg-brand-100 text-brand-700 grid place-items-center mb-3">${I(i)}</div><h3 class="font-bold">${t}</h3><p class="text-sm text-slate-500 mt-1">${d}</p></div>`).join('');
  const wa = $('#kontak-wa'); wa.href = linkWa('Halo SawitKu, saya ingin bertanya.'); $('#kontak-wa-teks').textContent = KONTAK.waTampil;
  $('#info-kontak').innerHTML = [['phone', KONTAK.waTampil, linkWa('Halo SawitKu, saya ingin bertanya.'), 'Chat WhatsApp'], ['mail', KONTAK.email, linkEmail('Pertanyaan untuk SawitKu'), 'Kirim email'], ['clock', KONTAK.jam]]
    .map(([i, t, h, a]) => `<li>${h ? `<a href="${K.esc(h)}" ${h.startsWith('http') ? 'target="_blank" rel="noopener noreferrer"' : ''} aria-label="${a}: ${K.esc(t)}" class="flex items-center gap-3 hover:text-white group">` : '<div class="flex items-center gap-3">'}<span class="w-10 h-10 rounded-xl bg-brand-700 group-hover:bg-brand-600 grid place-items-center transition">${I(i)}</span><span class="${h ? 'underline-offset-4 group-hover:underline' : ''}">${t}</span>${h ? '</a>' : '</div>'}</li>`).join('');
  $('#f-kat').innerHTML = '<option value="">Semua kategori</option>' + KATEGORI.map(k => `<option>${K.esc(k)}</option>`).join('');
  $('#menu-kat').innerHTML = KATEGORI.map(k => `<li><a href="#katalog" data-kat="${K.esc(k)}" class="block px-4 py-2.5 text-sm hover:bg-brand-50 hover:text-brand-700">${K.esc(k)}</a></li>`).join('');
  $('#grid-terlaris').innerHTML = PRODUK.filter(p => p.bestSeller).slice(0, 4).map(kartu).join('');
  renderSlider(); renderKatalog(); Animasi.reveal(); await renderAuth();
}
const setKat = k => { S.kat = k; $('#f-kat').value = k; renderKatalog(); $('#menu-kat').classList.add('hidden'); };
document.addEventListener('click', async e => {
  const k = e.target.closest('[data-kat]'); if (k) setKat(k.dataset.kat);
  if (!e.target.closest('#btn-kat')) $('#menu-kat').classList.add('hidden');
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
$('#f-rating').onchange = e => { S.rating = +e.target.value; renderKatalog(); }; $('#f-urut').onchange = e => { S.urut = e.target.value; renderKatalog(); };
$('#f-reset').onclick = () => { Object.assign(S, { kat: '', harga: '', rating: 0, urut: 'populer', q: '' }); ['f-kat', 'f-harga', 'cari'].forEach(i => $('#' + i).value = ''); $('#f-rating').value = 0; $('#f-urut').value = 'populer'; renderKatalog(); };
$('#form-kontak').onsubmit = async e => {
  e.preventDefault(); const err = $('#k-err'); err.textContent = '';
  try { await Api.kirimPesan({ nama: $('#k-nama').value, email: $('#k-email').value.trim(), jenis: $('#k-jenis').value, isi: $('#k-isi').value }); e.target.reset(); Toast.ok('Pesan terkirim. Terima kasih!'); }
  catch (er) { err.textContent = er.message; }
};
function pasangChatKontak() {
  const u = Sesi.user(), form = $('#form-kontak');
  if (u && u.peran === 'customer') {        // pelanggan login: formulir diganti chat langsung dengan admin
    const kotak = Chat.el('div', 'bg-white text-slate-800 p-6 md:p-10 flex flex-col');
    kotak.append(Chat.el('h3', 'font-extrabold text-lg', 'Chat dengan Admin'), Chat.el('p', 'text-sm text-slate-500 mb-3', 'Pesanmu langsung masuk ke admin dan balasannya muncul di sini.'));
    const isi = Chat.el('div', 'h-[420px] rounded-2xl border border-slate-100 overflow-hidden'); kotak.append(isi);
    form.replaceWith(kotak);
    Chat.pasang(isi, { saya: 'customer', muat: p => Api.chat(p), kirim: isi => Api.chatKirim(isi) });
  } else {                                  // tamu: formulir tetap ada + ajakan masuk untuk chat
    const info = Chat.el('p', 'text-xs text-slate-500 text-center', 'Ingin chat langsung dengan admin dan melihat balasannya di sini? ');
    const a = Chat.el('a', 'font-semibold text-brand-700 underline', 'Masuk dulu'); a.href = '/masuk?next=landing'; info.append(a); form.append(info);
  }
}
(async () => {
  await Sesi.segarkan();   // buang cache sesi yang sudah tidak berlaku di server
  pasangChatKontak();
  try { [PRODUK, FAV] = await Promise.all([Api.produk(), Api.favorit().catch(() => [])]); }
  catch (er) { $('#grid-katalog').innerHTML = `<p class="col-span-full text-center text-slate-500 py-16">Gagal memuat produk: ${K.esc(er.message)}</p>`; }
  await init();
})();
