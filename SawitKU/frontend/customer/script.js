'use strict';
let user, filterPesanan = 'semua', rentang = 'semua', fotoBaru = null;
const aktif = o => o.status !== 'dibatalkan';
const kelompok = { semua: 'Semua', proses: 'Dalam Proses', selesai: 'Selesai', batal: 'Dibatalkan' };
const tab = (map, cur, aksi) => Object.entries(map).map(([k, v]) => `<button class="tab ${k === cur ? 'aktif' : ''}" data-aksi="${aksi}" data-v="${k}">${v}</button>`).join('');
const kosong = (t, l, h) => `<div class="panel text-center py-14"><p class="text-slate-500">${t}</p>${l ? `<a href="${h}" class="btn btn-p mt-4">${l}</a>` : ''}</div>`;
const statCard = (kls, judul, nilai, ket, i = 0) => `<div class="kartu-stat ${kls}" style="animation-delay:${i * 90}ms"><p class="text-sm font-semibold opacity-90 relative">${judul}</p><p class="text-3xl font-extrabold mt-3 relative" data-hitung="${nilai}">0</p><p class="text-sm mt-4 opacity-90 relative">${ket}</p></div>`;
function hitungAngka(root) { $$('[data-hitung]', root).forEach(e => Animasi.hitung(e, +e.dataset.hitung, e.dataset.rp ? rp : undefined)); }
async function badgeNav() { const c = await Api.jumlahKeranjang(), a = $('.nav-item[data-sec="keranjang"]'); let p = $('.pin', a); if (!c) return p && p.remove(); if (!p) { p = document.createElement('span'); p.className = 'pin'; a.append(p); } p.textContent = c; }

let chatC = null, lencanaC = null;
const R = {
  async pesan() {
    if (chatC) chatC.hentikan();
    chatC = Chat.pasang($('#chat-root'), { saya: 'customer', muat: p => Api.chat(p), kirim: isi => Api.chatKirim(isi), diMuat: () => lencanaC && lencanaC.segarkan() });
  },
  async ringkasan() {
    const [os, jmlKer] = await Promise.all([Api.pesananSaya(), Api.jumlahKeranjang()]), belanja = os.filter(o => ['diproses', 'dikirim', 'selesai'].includes(o.status)).reduce((a, o) => a + o.total, 0), akt = os.filter(o => STATUS[o.status][1] === 'proses').length;
    $('#r-stat').innerHTML = statCard('g1', 'Total Belanja', belanja, `${os.filter(o => o.status === 'selesai').length} pesanan selesai`, 0).replace('data-hitung', 'data-rp="1" data-hitung') + statCard('g2', 'Pesanan Berjalan', akt, 'Menunggu bayar atau dikirim', 1) + statCard('g3', 'Item di Keranjang', jmlKer, 'Siap untuk checkout', 2);
    hitungAngka($('#r-stat'));
    const s = Grafik.seri(os.filter(o => ['diproses', 'dikirim', 'selesai'].includes(o.status)).map(o => ({ t: o.dibuat, v: o.total })), 'minggu', i => i.v); Grafik.bar($('#r-grafik'), s.labels, [{ nama: 'Belanja', warna: '#38995e', data: s.data }]);
    const g = { selesai: 0, proses: 0, batal: 0 }; os.forEach(o => g[STATUS[o.status][1]]++);
    Grafik.donut($('#r-donut'), [{ label: 'Selesai', nilai: g.selesai, warna: '#38995e' }, { label: 'Dalam Proses', nilai: g.proses, warna: '#f7c948' }, { label: 'Dibatalkan', nilai: g.batal, warna: '#fb7185' }]);
    $('#r-terbaru').innerHTML = os.slice(0, 4).map((o, i) => `<div class="baris py-3 flex items-center gap-3" style="animation-delay:${i * 60}ms"><img class="w-12 h-12 rounded-xl object-cover" src="${K.url(o.items[0].gambar)}" alt=""><div class="min-w-0 flex-1"><p class="font-semibold text-sm truncate">${K.esc(o.items[0].nama)}${o.items.length > 1 ? ` +${o.items.length - 1} lainnya` : ''}</p><p class="text-xs text-slate-500">#${o.id} &middot; ${tgl(o.dibuat)}</p></div><div class="text-right"><b class="text-sm">${rp(o.total)}</b><div class="mt-1">${badgeStatus(o.status)}</div></div></div>`).join('') || '<p class="text-slate-500 py-4">Belum ada pesanan.</p>';
  },
  async keranjang() {
    const k = await Api.keranjang(), el = $('#k-isi'); badgeNav();
    if (!k.length) return el.innerHTML = kosong('Keranjangmu masih kosong.', 'Mulai Belanja', '/#katalog');
    const total = k.reduce((a, c) => a + c.p.harga * c.qty, 0);
    el.innerHTML = `<div class="grid lg:grid-cols-3 gap-6"><div class="lg:col-span-2 space-y-3">${k.map((c, i) => `<div class="panel baris flex gap-4 items-center !p-4" style="animation-delay:${i * 60}ms"><img class="w-20 h-20 rounded-xl object-cover" src="${K.url(c.p.gambar)}" alt="${K.esc(c.p.nama)}"><div class="flex-1 min-w-0"><a class="font-bold hover:text-brand-600 block truncate" href="/produk/${c.p.id}">${K.esc(c.p.nama)}</a><p class="text-brand-700 font-bold text-sm">${rp(c.p.harga)}</p><p class="text-xs text-slate-500">Stok ${c.p.stok}</p></div>
      <div class="flex items-center rounded-xl border border-slate-200"><button class="w-8 h-9" data-aksi="qty" data-id="${c.p.id}" data-d="-1" aria-label="Kurangi">&minus;</button><b class="w-8 text-center text-sm">${c.qty}</b><button class="w-8 h-9" data-aksi="qty" data-id="${c.p.id}" data-d="1" aria-label="Tambah">+</button></div>
      <button class="btn btn-d !w-10 !px-0" data-aksi="hapus" data-id="${c.p.id}" aria-label="Hapus">${I('trash', 'w-4 h-4')}</button></div>`).join('')}</div>
      <div class="panel h-fit space-y-3 lg:sticky lg:top-24"><h2 class="font-extrabold">Ringkasan</h2><div class="flex justify-between text-sm"><span class="text-slate-500">${k.reduce((a, c) => a + c.qty, 0)} item</span><b>${rp(total)}</b></div><div class="border-t pt-3 flex justify-between font-extrabold"><span>Total</span><span class="text-brand-700">${rp(total)}</span></div><button class="btn btn-p w-full !h-12" data-aksi="checkout">Checkout</button></div></div>`;
  },
  async pesanan() {
    $('#p-tab').innerHTML = tab(kelompok, filterPesanan, 'tabPesanan');
    const semua = await Api.pesananSaya(), os = semua.filter(o => filterPesanan === 'semua' || STATUS[o.status][1] === filterPesanan);
    // produk yang sudah diulas (satu permintaan per produk unik dari pesanan selesai)
    const sudah = new Set(), calon = [...new Set(os.filter(o => o.status === 'selesai').flatMap(o => o.items.map(x => x.produkId)).filter(x => x != null))];
    await Promise.all(calon.map(async pid => { if (await Api.sudahUlas(pid)) sudah.add(pid); }));
    $('#p-isi').innerHTML = os.map((o, i) => {
      const bisaUlas = o.status === 'selesai' ? o.items.filter(x => x.produkId != null && !sudah.has(x.produkId)) : [];
      return `<article class="panel baris" style="animation-delay:${i * 50}ms"><div class="flex flex-wrap justify-between gap-2 items-center"><div><b>Pesanan #${o.id}</b> <span class="text-xs text-slate-500 ml-2">${tgl(o.dibuat)}</span></div>${badgeStatus(o.status)}</div>
      <div class="mt-3 divide-y divide-slate-100">${o.items.map(x => `<div class="py-2 flex items-center gap-3"><img class="w-12 h-12 rounded-lg object-cover" src="${K.url(x.gambar)}" alt=""><div class="flex-1 min-w-0 text-sm"><p class="font-semibold truncate">${K.esc(x.nama)}</p><p class="text-slate-500">${x.qty} x ${rp(x.harga)}</p></div>${bisaUlas.includes(x) ? `<button class="btn btn-o !h-8 !text-xs" data-aksi="ulas" data-id="${o.id}" data-p="${x.produkId}">Beri Ulasan</button>` : ''}</div>`).join('')}</div>
      ${tujuanHtml(o)}
      ${o.alasan && o.status === 'dibatalkan' ? `<p class="mt-2 text-sm rounded-xl bg-rose-50 text-rose-700 px-3 py-2">Alasan: ${K.esc(o.alasan)}</p>` : ''}
      ${o.status === 'menunggu_bayar' ? `<p class="mt-2 text-xs text-amber-700">Bayar sebelum ${new Date(o.batasBayar).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })}, jika lewat pesanan otomatis dibatalkan.</p>` : ''}
      <div class="mt-3 flex flex-wrap items-center justify-between gap-2"><b class="text-brand-700">${rp(o.total)}</b><div class="flex gap-2">
        ${o.status === 'menunggu_bayar' ? `<button class="btn btn-d" data-aksi="batal" data-id="${o.id}">Batalkan</button><button class="btn btn-p" data-aksi="bayar" data-id="${o.id}">Bayar via QRIS</button>` : ''}
        ${o.status === 'dikirim' ? `<button class="btn btn-p" data-aksi="terima" data-id="${o.id}">Barang Diterima</button>` : ''}</div></div></article>`;
    }).join('') || kosong('Tidak ada pesanan di kategori ini.');
  },
  async favorit() {
    const [ids, ps] = await Promise.all([Api.favorit(), Api.produk()]), f = ps.filter(p => ids.includes(p.id));
    $('#f-isi').innerHTML = f.map((p, i) => `<article class="panel baris !p-0 overflow-hidden" style="animation-delay:${i * 60}ms"><a href="/produk/${p.id}"><img class="aspect-square object-cover w-full" src="${K.url(p.gambar)}" alt="${K.esc(p.nama)}"></a><div class="p-4"><p class="font-bold text-sm line-clamp-1">${K.esc(p.nama)}</p><b class="text-brand-700 text-sm">${rp(p.harga)}</b><div class="flex gap-2 mt-3"><button class="btn btn-p flex-1 !h-9" data-aksi="favCart" data-id="${p.id}">Keranjang</button><button class="btn btn-d !h-9 !px-3" data-aksi="favHapus" data-id="${p.id}" aria-label="Hapus">${I('x', 'w-4 h-4')}</button></div></div></article>`).join('') || `<div class="col-span-full">${kosong('Belum ada produk favorit.', 'Jelajahi Produk', '/#katalog')}</div>`;
  },
  async statistik() {
    $('#s-tab').innerHTML = tab({ semua: 'Semua Waktu', bulan: 'Bulanan', minggu: 'Mingguan', hari: 'Hari Ini' }, rentang, 'rentang');
    const os = (await Api.pesananSaya()).filter(o => ['diproses', 'dikirim', 'selesai'].includes(o.status)), t = os.map(o => ({ t: o.dibuat, v: o.total })), sb = Grafik.seri(t, rentang, i => i.v), sj = Grafik.seri(t, rentang, () => 1);
    const jum = sj.data.reduce((a, b) => a + b, 0), tot = sb.data.reduce((a, b) => a + b, 0);
    $('#s-kartu').innerHTML = statCard('g1', 'Total Belanja', tot, 'pada rentang ini', 0).replace('data-hitung', 'data-rp="1" data-hitung') + statCard('g2', 'Jumlah Pesanan', jum, 'pesanan yang sudah dibayar', 1) + statCard('g3', 'Rata-rata Pesanan', jum ? tot / jum : 0, 'per transaksi', 2).replace('data-hitung', 'data-rp="1" data-hitung');
    hitungAngka($('#s-kartu')); Grafik.bar($('#s-bar'), sb.labels, [{ nama: 'Belanja', warna: '#38995e', data: sb.data }]); Grafik.area($('#s-area'), sj.labels, sj.data, '#0f766e');
  },
  profil() { $('#pf-foto').innerHTML = avatar({ ...user, foto: fotoBaru || user.foto }, 'w-full h-full text-3xl'); $('#pf-user').value = user.username; $('#pf-email').value = user.email;
    $('#pf-tel').value = user.telepon || ''; $('#pf-alm').value = user.alamat || ''; $('#pf-kota').value = user.kota || ''; $('#pf-pos').value = user.kodePos || ''; },
};

// Form alamat tujuan; pesanan dibuat dari dalam modal agar galat validasi server tampil di form (tidak menutupnya).
function checkoutDenganAlamat() {
  return new Promise(ok => {
    const v = x => K.esc(x || '');
    const m = Modal.buka(`<form id="al" class="p-6 space-y-3" novalidate><h2 class="font-extrabold text-lg">Alamat Pengiriman</h2><p class="text-sm text-slate-500">Pesanan akan dikirim ke alamat ini.</p>
      <input id="al-pen" class="in" maxlength="80" placeholder="Nama penerima" aria-label="Nama penerima" value="${v(user.username)}">
      <input id="al-tel" class="in" maxlength="20" inputmode="tel" placeholder="Nomor HP (081234567890)" aria-label="Nomor HP" value="${v(user.telepon)}">
      <textarea id="al-alm" rows="3" maxlength="200" class="in !h-auto py-2" placeholder="Alamat lengkap (jalan, nomor rumah, RT/RW, kelurahan)" aria-label="Alamat lengkap">${v(user.alamat)}</textarea>
      <div class="grid grid-cols-2 gap-3"><input id="al-kota" class="in" maxlength="60" placeholder="Kota/Kabupaten" aria-label="Kota atau kabupaten" value="${v(user.kota)}"><input id="al-pos" class="in" maxlength="5" inputmode="numeric" placeholder="Kode pos" aria-label="Kode pos" value="${v(user.kodePos)}"></div>
      <label class="flex items-center gap-2 text-sm"><input id="al-simpan" type="checkbox" class="accent-green-700" checked> Simpan sebagai alamat utama</label>
      <p id="al-err" class="text-sm text-rose-600 min-h-5" role="alert"></p>
      <div class="flex justify-end gap-2"><button type="button" data-tutup class="btn btn-o">Batal</button><button id="al-btn" class="btn btn-p">Buat Pesanan</button></div></form>`);
    m.addEventListener('click', e => { if (e.target.closest('[data-tutup]')) ok(null); });
    $('#al', m).onsubmit = async e => { e.preventDefault(); const b = $('#al-btn', m); b.disabled = true;
      try { const o = await Api.checkout({ penerima: $('#al-pen', m).value, telepon: $('#al-tel', m).value, alamat: $('#al-alm', m).value,
                                          kota: $('#al-kota', m).value, kodePos: $('#al-pos', m).value, simpan: $('#al-simpan', m).checked });
        m.tutup(); ok(o); }
      catch (x) { $('#al-err', m).textContent = x.message; b.disabled = false; } };
  });
}
const tujuanHtml = o => o.pengiriman ? `<p class="mt-2 text-xs text-slate-500">Dikirim ke: <b>${K.esc(o.pengiriman.penerima)}</b> &middot; ${K.esc(o.pengiriman.telepon)} &middot; ${K.esc(o.pengiriman.alamat)}, ${K.esc(o.pengiriman.kota)} ${K.esc(o.pengiriman.kodePos)}</p>` : '';
async function bayar(id) {
  const o = (await Api.pesananSaya()).find(x => x.id === id); if (!o) return Toast.err('Pesanan tidak ditemukan.'); let bukti = null;
  const m = Modal.buka(`<div class="p-6"><h2 class="font-extrabold text-lg">Pembayaran QRIS #${o.id}</h2><p class="text-sm text-slate-500">Scan kode di bawah lalu bayar sesuai nominal.</p>
    <div class="mx-auto my-4 w-52 h-52 p-3 rounded-2xl border-2 border-brand-200 bg-white">${QR(o.id + 7)}</div><p class="text-center text-xs text-slate-400 -mt-2 mb-2">QRIS toko (simulasi)</p>
    <p class="text-center text-2xl font-extrabold text-brand-700">${rp(o.total)}</p>
    <label class="block mt-5 text-sm font-semibold">Unggah bukti pembayaran</label><input id="bk-file" type="file" accept="image/jpeg,image/png,image/webp" class="mt-1 w-full text-sm file:mr-3 file:btn file:btn-o file:border-0 file:rounded-xl file:px-3 file:py-2 file:bg-brand-100 file:text-brand-800 file:font-semibold">
    <img id="bk-prev" class="hidden mt-3 max-h-48 rounded-xl mx-auto" alt="Pratinjau bukti"><p id="bk-err" class="text-sm text-rose-600 min-h-5 mt-2" role="alert"></p>
    <div class="flex justify-end gap-2 mt-3"><button data-tutup class="btn btn-o">Nanti</button><button id="bk-kirim" class="btn btn-p" disabled>Kirim Bukti</button></div></div>`);
  $('#bk-file', m).onchange = async e => { const f = e.target.files[0], er = await K.cekGambar(f), p = $('#bk-prev', m); $('#bk-err', m).textContent = er || ''; $('#bk-kirim', m).disabled = true; if (er) { p.classList.add('hidden'); e.target.value = ''; return; }
    try { bukti = await K.kecilkan(f); p.src = bukti; p.classList.remove('hidden'); $('#bk-kirim', m).disabled = false; } catch (x) { $('#bk-err', m).textContent = x.message; } };
  $('#bk-kirim', m).onclick = async () => { const b = $('#bk-kirim', m); b.disabled = true; try { await Api.bayar(id, bukti); m.tutup(); Toast.ok('Bukti terkirim. Menunggu verifikasi admin.'); R.pesanan(); } catch (x) { $('#bk-err', m).textContent = x.message; b.disabled = false; } };
}
async function ulas(pid) {
  const p = await Api.produkById(pid); if (!p) return Toast.err('Produk tidak ditemukan.'); let r = 5;
  const m = Modal.buka(`<div class="p-6"><h2 class="font-extrabold text-lg">Ulasan ${K.esc(p.nama)}</h2><div id="ul-bin" class="text-3xl my-3 flex gap-1" role="radiogroup" aria-label="Rating"></div>
    <textarea id="ul-teks" rows="4" maxlength="300" class="in !h-auto py-2" placeholder="Ceritakan pengalamanmu..."></textarea><p class="text-xs text-slate-500 mt-1">Ulasan langsung tampil di halaman produk. Admin dapat memberi komentar.</p><p id="ul-err" class="text-sm text-rose-600 min-h-5" role="alert"></p>
    <div class="flex justify-end gap-2 mt-2"><button data-tutup class="btn btn-o">Batal</button><button id="ul-kirim" class="btn btn-p">Kirim</button></div></div>`, 'max-w-md');
  const g = () => $('#ul-bin', m).innerHTML = [1, 2, 3, 4, 5].map(i => `<button data-r="${i}" class="${i <= r ? 'text-sun-500' : 'text-slate-300'} hover:scale-125 transition" aria-label="${i} bintang">★</button>`).join(''); g();
  $('#ul-bin', m).onclick = e => { const b = e.target.closest('[data-r]'); if (b) { r = +b.dataset.r; g(); } };
  $('#ul-kirim', m).onclick = async () => { try { await Api.kirimUlasan(pid, r, $('#ul-teks', m).value); m.tutup(); Toast.ok('Ulasan berhasil dipublikasikan.'); R.pesanan(); } catch (x) { $('#ul-err', m).textContent = x.message; } };
}
document.addEventListener('click', async e => {
  const a = e.target.closest('[data-aksi]'); if (!a) return; const id = +a.dataset.id, v = a.dataset.v;
  try { switch (a.dataset.aksi) {
    case 'qty': { const c = (await Api.keranjang()).find(x => x.produkId === id); if (!c) break; const n = c.qty + +a.dataset.d; if (n < 1) break; await Api.kerSet(id, n); R.keranjang(); break; }
    case 'hapus': await Api.kerHapus(id); R.keranjang(); Toast.ok('Item dihapus.'); break;
    case 'checkout': { const o = await checkoutDenganAlamat(); if (!o) break; user = await Api.saya(true); Toast.ok('Pesanan dibuat. Silakan bayar.'); filterPesanan = 'semua'; location.hash = '#pesanan'; setTimeout(() => bayar(o.id), 300); break; }
    case 'tabPesanan': filterPesanan = v; R.pesanan(); break; case 'rentang': rentang = v; R.statistik(); break;
    case 'bayar': bayar(id); break; case 'ulas': ulas(+a.dataset.p); break;
    case 'batal': if (await Modal.konfirmasi('Batalkan pesanan ini?', 'Batalkan')) { await Api.batal(id); Toast.ok('Pesanan dibatalkan.'); R.pesanan(); } break;
    case 'terima': if (await Modal.konfirmasi('Konfirmasi barang sudah kamu terima?', 'Sudah Diterima')) { await Api.terima(id); Toast.ok('Terima kasih! Pesanan selesai.'); R.pesanan(); } break;
    case 'favCart': await Api.kerAdd(id, 1); Toast.ok('Ditambahkan ke keranjang.'); badgeNav(); break;
    case 'favHapus': await Api.favToggle(id); R.favorit(); break; } } catch (er) { Toast.err(er.message); }
});
$('#pf-file').onchange = async e => { const f = e.target.files[0], er = await K.cekGambar(f); $('#pf-err').textContent = er || ''; if (er) { fotoBaru = null; e.target.value = ''; return; }
  try { fotoBaru = await K.kecilkan(f, 320); $('#pf-foto').innerHTML = avatar({ ...user, foto: fotoBaru }, 'w-full h-full text-3xl'); } catch (x) { $('#pf-err').textContent = x.message; } };
$('#pf').onsubmit = async e => { e.preventDefault(); try { user = await Api.profil({ username: $('#pf-user').value.trim(), email: $('#pf-email').value.trim(), foto: fotoBaru,
    telepon: $('#pf-tel').value.trim(), alamat: $('#pf-alm').value.trim(), kota: $('#pf-kota').value.trim(), kodePos: $('#pf-pos').value.trim() }); fotoBaru = null; Dash.segarkanAvatar(user); $('#pf-err').textContent = ''; Toast.ok('Profil diperbarui.'); } catch (x) { $('#pf-err').textContent = x.message; } };
$('#pf-ganti-email').onclick = () => {
  const m = Modal.buka(`<div class="p-6 space-y-4"><h2 class="font-extrabold text-lg">Ganti email</h2>
    <div id="ge-1" class="space-y-3"><p class="text-sm text-slate-500">Kami kirim kode 6 angka ke email baru. Email lama tetap dipakai sampai kode dimasukkan.</p>
      <div><label class="text-sm font-semibold" for="ge-email">Email baru</label><input id="ge-email" type="email" class="in mt-1" maxlength="100" autocomplete="off"></div>
      <div><label class="text-sm font-semibold" for="ge-pw">Password saat ini</label><input id="ge-pw" type="password" class="in mt-1" maxlength="64" autocomplete="current-password"></div></div>
    <div id="ge-2" class="hidden space-y-3"><p class="text-sm text-slate-600">Kode dikirim ke <b id="ge-tujuan" class="break-all"></b>. Berlaku <span id="ge-menit"></span> menit. Cek juga folder spam.</p>
      <input id="ge-kode" inputmode="numeric" maxlength="6" placeholder="------" aria-label="Kode OTP 6 angka" class="in text-center font-bold tracking-[.6em]" autocomplete="one-time-code"></div>
    <p id="ge-err" class="text-sm text-rose-600 min-h-5" role="alert"></p>
    <div class="flex justify-end gap-2"><button type="button" data-tutup class="btn btn-o">Batal</button><button type="button" id="ge-ok" class="btn btn-p">Kirim Kode</button></div></div>`);
  let tahap = 1; const err = $('#ge-err', m), btn = $('#ge-ok', m);
  btn.onclick = async () => {
    err.textContent = ''; btn.disabled = true;
    try {
      if (tahap === 1) {
        const em = $('#ge-email', m).value.trim(), pw = $('#ge-pw', m).value;
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) throw new Error('Format email tidak valid.');
        if (!pw) throw new Error('Password saat ini wajib diisi.');
        const d = await Api.emailMinta(em, pw);
        $('#ge-tujuan', m).textContent = d.email; $('#ge-menit', m).textContent = d.berlaku;
        $('#ge-1', m).classList.add('hidden'); $('#ge-2', m).classList.remove('hidden'); btn.textContent = 'Verifikasi'; tahap = 2; $('#ge-kode', m).focus();
      } else {
        const k = $('#ge-kode', m).value.replace(/\D/g, '');
        if (k.length !== 6) throw new Error('Masukkan 6 angka kode OTP.');
        user = await Api.emailVerifikasi(k); $('#pf-email').value = user.email; m.tutup(); Toast.ok('Email berhasil diganti.'); return;
      }
    } catch (x) { err.textContent = x.message; }
    btn.disabled = false;
  };
};
(async () => {
  user = await Sesi.wajib('customer'); if (!user) return;
  $('#app').hidden = false; $('#logo').innerHTML = I('leaf', 'w-6 h-6'); $('#ikon-menu').innerHTML = I('menu');
  $$('.nav-item').forEach(a => { const s = a.querySelector('.ic') || a.querySelector('[data-ikon]'); if (s) s.innerHTML = I(a.dataset.ikon || 'out'); });
  Dash.init(R, user); badgeNav().catch(() => {});
  lencanaC = Chat.lencana('pesan', () => Api.chatBelum());
})();
