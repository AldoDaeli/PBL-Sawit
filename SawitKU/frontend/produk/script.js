'use strict';
/* Detail produk: data dari API, markup dari <template> di index.html. */
const id = Number(location.pathname.split('/').filter(Boolean).pop());   // URL pendek: /produk/<id>
let produk = null, me = null;
async function badge() { const c = await Api.jumlahKeranjang(), b = $('#badge'); b.textContent = c; b.classList.toggle('hidden', !c); b.classList.toggle('grid', !!c); }

async function render() {
  const el = $('#isi'), p = await Api.produkById(id); produk = p;
  if (!p) return el.replaceChildren(T.klon('t-tidak-ada'));
  document.title = p.nama + ' | SawitKu';
  me = Sesi.user();
  const [ul, favIds, semua] = await Promise.all([Api.ulasanTampil(p.id), Api.favorit(), Api.produk()]);
  const mirip = semua.filter(x => x.kategori === p.kategori && x.id !== p.id).slice(0, 4);
  const halaman = T.satu('t-produk', { ...p, fav: favIds.includes(p.id), habis: p.stok < 1, stokTipis: p.stok < 10, labelCart: p.stok < 1 ? 'Stok habis' : 'Tambah ke keranjang',
    spek: Object.entries(p.spesifikasi || {}).map(([k, v]) => ({ k, v })), adaSpek: Object.keys(p.spesifikasi || {}).length > 0, adaMirip: mirip.length > 0 });
  const kosong = ul.length === 0;
  const daftar = $('#daftar-ulasan', halaman);
  daftar.replaceChildren(...(kosong ? [T.satu('t-ulasan-kosong', {})] : ul.map(u => {
    const kartu = T.satu('t-ulasan', { ...u, inisial: (u.nama || '?')[0], bisaBalas: !!(me && me.peran === 'customer' && me.id === u.userId && u.balasan && Balasan.pesan(u).at(-1).dari === 'admin') });
    $('[data-balasan]', kartu).replaceWith(...Balasan.nodes(u, u.nama)); return kartu; })));
  if (mirip.length) $('#daftar-mirip', halaman).replaceChildren(...mirip.map(x => T.satu('t-mirip', x)));
  el.replaceChildren(halaman); ikon(el); Animasi.reveal();
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-balas]'); if (!b) return; const rid = +b.dataset.balas, m = Modal.dari('t-balas-modal', {}, 'max-w-md');
  $('#bl-ok', m).onclick = async () => { try { await Api.balasUlasan(rid, $('#bl', m).value); m.tutup(); Toast.ok('Balasan terkirim.'); render(); } catch (x) { $('#bl-err', m).textContent = x.message; } };
});
document.addEventListener('click', async e => {
  const q = $('#qty'), t = e.target.closest('[data-q]'); if (t && produk) q.value = Math.min(produk.stok, Math.max(1, (+q.value || 1) + +t.dataset.q));
  try {
    if (e.target.closest('#btn-cart')) { if (!Sesi.user()) { Toast.err('Masuk dulu untuk berbelanja.'); return setTimeout(() => location.href = '/masuk?next=landing', 900); } await Api.kerAdd(id, +q.value); Toast.ok('Ditambahkan ke keranjang.'); badge(); }
    if (e.target.closest('#btn-fav')) { if (!Sesi.user()) { Toast.err('Masuk dulu untuk menyimpan favorit.'); return; } const on = await Api.favToggle(id); $('#btn-fav').classList.toggle('fav-aktif', on); Toast.ok(on ? 'Masuk ke favorit.' : 'Dihapus dari favorit.'); }
  } catch (er) { Toast.err(er.message); }
});
document.addEventListener('sesi-berubah', () => location.reload());
(async () => {
  await Sesi.segarkan();
  try { await Promise.all([badge(), render()]); }
  catch (er) { $('#isi').replaceChildren(T.klon('t-gagal', { pesan: er.message })); }
})();
