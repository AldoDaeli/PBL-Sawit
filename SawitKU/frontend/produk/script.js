'use strict';
const id = Number(location.pathname.split('/').filter(Boolean).pop());   // URL pendek: /produk/<id>
async function badge() { const c = await Api.jumlahKeranjang(), b = $('#badge'); b.textContent = c; b.classList.toggle('hidden', !c); b.classList.toggle('grid', !!c); }
let produk = null;
async function render() {
  const el = $('#isi'), p = await Api.produkById(id); produk = p;
  if (!p) return el.innerHTML = `<div class="text-center py-24"><h1 class="text-2xl font-extrabold">Produk tidak ditemukan</h1><a href="/#katalog" class="inline-block mt-4 text-brand-600 font-semibold">&larr; Kembali ke katalog</a></div>`;
  document.title = p.nama + ' | SawitKu';
  const me = Sesi.user(), [ul, favIds, semua] = await Promise.all([Api.ulasanTampil(p.id), Api.favorit(), Api.produk()]), fav = favIds.includes(p.id), lain = semua.filter(x => x.kategori === p.kategori && x.id !== p.id).slice(0, 4);
  el.innerHTML = `<nav class="text-sm text-slate-500 mb-6"><a class="hover:text-brand-600" href="/">Beranda</a> / <a class="hover:text-brand-600" href="/#katalog">${K.esc(p.kategori)}</a> / <span class="text-slate-800">${K.esc(p.nama)}</span></nav>
  <div class="grid md:grid-cols-2 gap-8 lg:gap-14">
    <div class="gambar-utama rounded-3xl overflow-hidden bg-brand-50 aspect-square shadow-xl"><img src="${K.url(p.gambar)}" alt="${K.esc(p.nama)}" class="w-full h-full object-cover"></div>
    <div class="animate-fade-up"><span class="text-xs font-bold text-brand-600 uppercase tracking-wide">${K.esc(p.kategori)}</span><h1 class="text-3xl md:text-4xl font-extrabold mt-1">${K.esc(p.nama)}</h1>
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 text-sm">${bintang(p.rating)}<b>${p.rating}</b><span class="text-slate-400">|</span><span>${p.terjual} terjual</span><span class="text-slate-400">|</span><span class="${p.stok < 10 ? 'text-rose-600 font-semibold' : ''}">Stok ${p.stok}</span></div>
      <p class="text-4xl font-extrabold text-brand-700 mt-5">${rp(p.harga)}</p><p class="text-slate-600 mt-4 leading-relaxed">${K.esc(p.deskripsi)}</p>
      <div class="flex items-center gap-3 mt-7"><div class="flex items-center rounded-xl border border-slate-200 h-12"><button data-q="-1" class="w-10 h-full hover:bg-brand-50 rounded-l-xl text-lg" aria-label="Kurangi">&minus;</button><input id="qty" type="number" min="1" max="${p.stok}" value="1" class="w-12 text-center font-bold outline-none [appearance:textfield]" aria-label="Jumlah"><button data-q="1" class="w-10 h-full hover:bg-brand-50 rounded-r-xl text-lg" aria-label="Tambah">+</button></div>
        <button id="btn-cart" ${p.stok < 1 ? 'disabled' : ''} class="flex-1 h-12 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:bg-slate-200 disabled:text-slate-400 text-white font-bold flex items-center justify-center gap-2 transition active:scale-[.98]">${I('cart')}${p.stok < 1 ? 'Stok Habis' : 'Tambah ke Keranjang'}</button>
        <button id="btn-fav" class="w-12 h-12 rounded-xl border border-slate-200 grid place-items-center text-slate-500 hover:text-rose-500 transition ${fav ? 'fav-aktif' : ''}" aria-label="Favorit">${I('heart')}</button></div>
      ${Object.keys(p.spesifikasi || {}).length ? `<div class="mt-8 rounded-2xl border border-slate-100 overflow-hidden"><h2 class="px-5 py-3 bg-brand-50 font-bold">Spesifikasi</h2><dl>${Object.entries(p.spesifikasi || {}).map(([k, v]) => `<div class="flex px-5 py-2.5 text-sm border-t border-slate-100"><dt class="w-40 text-slate-500">${K.esc(k)}</dt><dd class="font-medium">${K.esc(v)}</dd></div>`).join('')}</dl></div>` : ''}</div></div>
  <section class="mt-16" data-reveal><h2 class="text-2xl font-extrabold">Ulasan Pembeli <span class="text-slate-400 text-lg font-semibold">(${ul.length})</span></h2>
    <div class="mt-5 grid md:grid-cols-2 gap-4">${ul.length ? ul.map(u => `<article class="rounded-2xl border border-slate-100 p-5"><div class="flex items-center gap-3"><span class="w-10 h-10 rounded-full bg-brand-600 text-white grid place-items-center font-bold uppercase">${K.esc(u.nama[0])}</span><div><b class="text-sm">${K.esc(u.nama)}</b><div class="text-xs">${bintang(u.rating)} <span class="text-slate-400 ml-1">${tgl(u.dibuat)}</span></div></div></div><p class="mt-3 text-sm text-slate-600">${K.esc(u.teks)}</p>${Balasan.html(u, u.nama)}${me && me.peran === 'customer' && me.id === u.userId && u.balasan && Balasan.pesan(u).at(-1).dari === 'admin' ? `<div class="mt-3 text-right"><button class="px-3 py-1.5 rounded-lg bg-brand-100 text-brand-800 text-xs font-semibold hover:bg-brand-200 transition" data-balas="${u.id}">Balas</button></div>` : ''}</article>`).join('') : '<p class="text-slate-500">Belum ada ulasan untuk produk ini.</p>'}</div></section>
  ${lain.length ? `<section class="mt-16" data-reveal><h2 class="text-2xl font-extrabold">Produk Serupa</h2><div class="mt-5 grid grid-cols-2 md:grid-cols-4 gap-4">${lain.map(x => `<a href="/produk/${x.id}" class="group rounded-2xl border border-slate-100 overflow-hidden hover:shadow-lg hover:-translate-y-1 transition"><div class="aspect-square overflow-hidden"><img src="${K.url(x.gambar)}" alt="${K.esc(x.nama)}" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition duration-500"></div><div class="p-3"><p class="font-semibold text-sm line-clamp-1">${K.esc(x.nama)}</p><b class="text-brand-700 text-sm">${rp(x.harga)}</b></div></a>`).join('')}</div></section>` : ''}`;
  Animasi.reveal();
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-balas]'); if (!b) return; const rid = +b.dataset.balas;
  const m = Modal.buka(`<div class="p-6"><h2 class="font-extrabold text-lg">Balas Admin</h2><textarea id="bl" rows="4" maxlength="300" class="w-full rounded-xl border border-slate-200 px-3 py-2 mt-3" placeholder="Tulis balasanmu..."></textarea><p id="bl-err" class="text-sm text-rose-600 min-h-5" role="alert"></p><div class="flex justify-end gap-2 mt-2"><button data-tutup class="px-4 py-2 rounded-xl text-sm font-semibold bg-slate-100">Batal</button><button id="bl-ok" class="px-4 py-2 rounded-xl text-sm font-semibold bg-brand-600 text-white">Kirim</button></div></div>`, 'max-w-md');
  $('#bl-ok', m).onclick = async () => { try { await Api.balasUlasan(rid, $('#bl', m).value); m.tutup(); Toast.ok('Balasan terkirim.'); render(); } catch (x) { $('#bl-err', m).textContent = x.message; } };
});
document.addEventListener('click', async e => {
  const q = $('#qty'), t = e.target.closest('[data-q]'); if (t && produk) q.value = Math.min(produk.stok, Math.max(1, (+q.value || 1) + +t.dataset.q));
  try {
    if (e.target.closest('#btn-cart')) { if (!Sesi.user()) { Toast.err('Masuk dulu untuk berbelanja.'); return setTimeout(() => location.href = '/masuk?next=landing', 900); } await Api.kerAdd(id, +q.value); Toast.ok('Ditambahkan ke keranjang.'); badge(); }
    if (e.target.closest('#btn-fav')) { if (!Sesi.user()) { Toast.err('Masuk dulu untuk menyimpan favorit.'); return; } const on = await Api.favToggle(id); $('#btn-fav').classList.toggle('fav-aktif', on); Toast.ok(on ? 'Masuk ke favorit.' : 'Dihapus dari favorit.'); }
  } catch (er) { Toast.err(er.message); }
});
(async () => {
  $('#ikon-cart').innerHTML = I('cart');
  await Sesi.segarkan();
  try { await Promise.all([badge(), render()]); }
  catch (er) { $('#isi').innerHTML = `<div class="text-center py-24"><h1 class="text-2xl font-extrabold">Gagal memuat produk</h1><p class="text-slate-500 mt-2">${K.esc(er.message)}</p></div>`; }
})();
