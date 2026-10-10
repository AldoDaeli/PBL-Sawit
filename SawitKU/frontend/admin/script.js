'use strict';
let tabPesan = 'chat', uidChat = null, chatA = null, lencanaA = null, timerDaftar = null;
let user, rentang = 'bulan', filterBayar = 'menunggu_verifikasi', filterUlasan = 'belum', cari = '', fotoProduk = null;
const tab = (map, cur, aksi) => Object.entries(map).map(([k, v]) => `<button class="tab ${k === cur ? 'aktif' : ''}" data-aksi="${aksi}" data-v="${k}">${v}</button>`).join('');
const statCard = (kls, judul, nilai, ket, i, uang) => `<div class="kartu-stat ${kls}" style="animation-delay:${i * 70}ms"><p class="text-sm font-semibold opacity-90 relative">${judul}</p><p class="text-2xl font-extrabold mt-2 relative" data-hitung="${nilai}" ${uang ? 'data-rp="1"' : ''}>0</p><p class="text-xs mt-3 opacity-90 relative">${ket}</p></div>`;
const hitungAngka = root => $$('[data-hitung]', root).forEach(e => Animasi.hitung(e, +e.dataset.hitung, e.dataset.rp ? rp : undefined));
const kosong = t => `<div class="panel text-center py-12 text-slate-500 col-span-full">${t}</div>`;
const laku = o => ['diproses', 'dikirim', 'selesai'].includes(o.status);

/* ---- Chat pelanggan: daftar percakapan (kiri) + percakapan terpilih (kanan) ---- */
async function segarkanDaftarChat() {
  const box = $('#ps-daftar'), l = await Api.adminChatDaftar(); box.textContent = '';
  if (!l.length) return box.append(Chat.el('p', 'text-center text-sm text-slate-500 py-10', 'Belum ada percakapan dari pelanggan.'));
  l.forEach(c => {   // semua teks dari pelanggan lewat textContent
    const b = Chat.el('button', 'w-full text-left rounded-xl px-3 py-2.5 hover:bg-brand-50 transition flex gap-3 items-center ' + (c.userId === uidChat ? 'bg-brand-50' : '')); b.type = 'button'; b.dataset.uid = c.userId;
    const kiri = Chat.el('div', 'min-w-0 flex-1'); kiri.append(Chat.el('p', 'font-bold text-sm truncate', c.username + (c.aktif ? '' : ' (nonaktif)')), Chat.el('p', 'text-xs text-slate-500 truncate', (c.dari === 'admin' ? 'Kamu: ' : '') + c.terakhir));
    const kanan = Chat.el('div', 'text-right shrink-0 space-y-1'); kanan.append(Chat.el('p', 'text-[10px] text-slate-400', tgl(c.dibuat, true)));
    if (c.belum) kanan.append(Chat.el('span', 'inline-block min-w-[1.15rem] h-[1.15rem] px-1 rounded-full bg-sun-500 text-brand-900 text-[10px] font-bold leading-[1.15rem] text-center', c.belum > 99 ? '99+' : c.belum));
    b.append(kiri, kanan); box.append(b);
  });
}
function jadwalDaftarChat() {   // perbarui daftar tiap 8 dtk hanya selama bagian Pesan terlihat
  clearTimeout(timerDaftar);
  timerDaftar = setTimeout(async () => {
    if (!document.hidden && !$('#sec-pesan').classList.contains('hidden') && tabPesan === 'chat') { try { await segarkanDaftarChat(); } catch {} lencanaA && lencanaA.segarkan(); }
    if (!$('#sec-pesan').classList.contains('hidden') && tabPesan === 'chat') jadwalDaftarChat();
  }, 8000);
}
function bukaChat(uid) {
  uidChat = uid; if (chatA) chatA.hentikan(); const judul = $('#ps-judul'); judul.textContent = 'Memuat...';
  chatA = Chat.pasang($('#ps-chat-root'), { saya: 'admin', kosong: 'Belum ada pesan.', muat: p => Api.adminChat(uid, p), kirim: isi => Api.adminChatKirim(uid, isi),
    diMuat: d => { if (d.pelanggan) judul.textContent = d.pelanggan.username + ' \u00b7 ' + d.pelanggan.email + (d.pelanggan.aktif ? '' : ' (nonaktif)'); segarkanDaftarChat().catch(() => {}); lencanaA && lencanaA.segarkan(); } });
}
document.addEventListener('click', e => {
  const b = e.target.closest('#ps-daftar [data-uid]'); if (b) bukaChat(+b.dataset.uid);
  const t = e.target.closest('[data-aksi="tabPesan"]'); if (t) { tabPesan = t.dataset.v; R.pesan().catch(er => Toast.err(er.message)); }
});

const R = {
  async ringkasan() {
    const [os, ps, pengguna] = await Promise.all([Api.adminPesanan(), Api.produk(), Api.penggunaAll()]), akt = os.filter(o => o.status === 'menunggu_bayar').length;
    const pend = os.filter(laku).reduce((a, o) => a + o.total, 0), tolak = os.filter(o => o.status === 'dibatalkan' && /bukti|tidak sesuai/i.test(o.alasan)).length;
    $('#r-stat').innerHTML = [['g1', 'Total Pendapatan', pend, 'dari pembayaran disetujui', 1], ['g2', 'Produk Terjual', os.filter(laku).reduce((a, o) => a + o.items.reduce((x, i) => x + i.qty, 0), 0), 'dari pesanan yang dibayar'], ['g3', 'Total Stok', ps.reduce((a, p) => a + p.stok, 0), `${ps.length} jenis produk`], ['g4', 'Pengguna Terdaftar', pengguna.length, 'akun customer'],
      ['g2', 'Checkout Berjalan', akt, 'belum dibayar'], ['g3', 'Menunggu Persetujuan', os.filter(o => o.status === 'menunggu_verifikasi').length, 'perlu diverifikasi'], ['g1', 'Pembayaran Ditolak', tolak, 'bukti tidak sesuai'], ['g4', 'Total Pesanan', os.length, 'semua status']]
      .map(([k, j, n, ket, u], i) => statCard(k, j, n, ket, i, u)).join('');
    hitungAngka($('#r-stat')); this.tren(os);
    const jual = {}; os.filter(laku).forEach(o => o.items.forEach(i => jual[i.nama] = (jual[i.nama] || 0) + i.qty)); const top = Object.entries(jual).sort((x, y) => y[1] - x[1]).slice(0, 6);
    Grafik.bar($('#r-bar'), top.map(([n]) => n.length > 11 ? n.slice(0, 10) + '…' : n), [{ nama: 'Terjual', warna: '#38995e', data: top.map(x => x[1]) }]);
    const g = { selesai: 0, proses: 0, batal: 0 }; os.forEach(o => g[STATUS[o.status][1]]++);
    Grafik.donut($('#r-donut'), [{ label: 'Selesai', nilai: g.selesai, warna: '#38995e' }, { label: 'Dalam Proses', nilai: g.proses, warna: '#f7c948' }, { label: 'Dibatalkan', nilai: g.batal, warna: '#fb7185' }]);
  },
  async tren(os) {
    os = os || await Api.adminPesanan();
    $('#r-tab').innerHTML = tab({ semua: 'Semua', bulan: 'Bulanan', minggu: 'Mingguan', hari: 'Hari Ini' }, rentang, 'rentang');
    const t = os.filter(laku).map(o => ({ t: o.dibuat, v: o.total })), s = Grafik.seri(t, rentang, i => i.v), c = Grafik.banding(t, rentang, i => i.v), el = $('#r-tren');
    const nama = { hari: 'kemarin', minggu: 'minggu lalu', bulan: 'bulan lalu' }[rentang], total = s.data.reduce((x, y) => x + y, 0); let info = `Total ${rp(total)}`, warna = 'text-slate-500';
    // Persentase hanya ditampilkan bila data pembanding cukup besar, agar tidak melonjak ekstrem akibat sampel kecil.
    if (c && c.prev >= 150000) { const p = Math.round((c.now - c.prev) / c.prev * 100); info += `  |  ${p >= 0 ? '▲ naik' : '▼ turun'} ${Math.min(Math.abs(p), 300)}${Math.abs(p) > 300 ? '+' : ''}% dibanding ${nama}`; warna = p >= 0 ? 'text-brand-600' : 'text-rose-600'; }
    else if (c && c.now > 0) info += `  |  belum cukup data pembanding (${nama})`;
    else if (c) info += `  |  ${nama} belum ada transaksi`;
    el.textContent = info; el.className = 'ml-2 text-sm font-bold ' + warna; Grafik.area($('#r-area'), s.labels, s.data);
  },
  async produk() {
    const a = (await Api.produk()).filter(p => !cari || p.nama.toLowerCase().includes(cari.toLowerCase()));
    $('#pr-isi').innerHTML = a.map((p, i) => `<tr class="baris border-t border-slate-100 hover:bg-brand-50/50" style="animation-delay:${i * 30}ms"><td class="p-4"><div class="flex items-center gap-3"><img class="w-11 h-11 rounded-lg object-cover" src="${K.url(p.gambar)}" alt=""><b class="max-w-[200px] truncate">${K.esc(p.nama)}</b></div></td><td>${K.esc(p.kategori)}</td><td>${rp(p.harga)}</td><td class="${p.stok < 10 ? 'text-rose-600 font-bold' : ''}">${p.stok}</td><td>${p.terjual}</td>
      <td class="pr-4"><div class="flex justify-end gap-2"><button class="btn btn-o !w-9 !px-0" data-aksi="edit" data-id="${p.id}" aria-label="Ubah">${I('edit', 'w-4 h-4')}</button><button class="btn btn-d !w-9 !px-0" data-aksi="hapusProduk" data-id="${p.id}" aria-label="Hapus">${I('trash', 'w-4 h-4')}</button></div></td></tr>`).join('') || `<tr><td colspan="6" class="p-8 text-center text-slate-500">Produk tidak ditemukan.</td></tr>`;
  },
  async pembayaran() {
    const os = await Api.adminPesanan(), map = { menunggu_verifikasi: 'Menunggu Verifikasi', diproses: 'Siap Dikirim', dikirim: 'Dikirim', selesai: 'Selesai', dibatalkan: 'Dibatalkan', semua: 'Semua' };
    $('#pb-tab').innerHTML = tab(map, filterBayar, 'tabBayar'); const l = os.filter(o => filterBayar === 'semua' || o.status === filterBayar);
    $('#pb-isi').innerHTML = l.map((o, i) => `<article class="panel baris" style="animation-delay:${i * 50}ms"><div class="flex flex-wrap justify-between gap-2"><div><b>#${o.id}</b> <span class="text-slate-500 text-sm ml-1">oleh ${K.esc(o.pembeli)} &middot; ${tgl(o.dibuat)}</span></div>${badgeStatus(o.status)}</div>
      <p class="text-sm text-slate-600 mt-2">${o.items.map(x => `${K.esc(x.nama)} x${x.qty}`).join(', ')}</p><div class="flex flex-wrap items-center justify-between gap-2 mt-3"><b class="text-brand-700 text-lg">${rp(o.total)}</b><div class="flex gap-2">
      ${o.bukti ? `<button class="btn btn-o" data-aksi="bukti" data-id="${o.id}">Lihat Bukti</button>` : ''}
      ${o.status === 'menunggu_verifikasi' ? `<button class="btn btn-d" data-aksi="tolak" data-id="${o.id}">Tolak</button><button class="btn btn-p" data-aksi="setuju" data-id="${o.id}">Setujui</button>` : ''}
      ${o.status === 'diproses' ? `<button class="btn btn-p" data-aksi="kirim" data-id="${o.id}">Tandai Dikirim</button>` : ''}</div></div>
      ${o.pengiriman ? `<div class="mt-3 rounded-xl bg-brand-50 px-3 py-2 text-sm"><b class="text-brand-700 text-xs">ALAMAT PENGIRIMAN</b><p class="mt-0.5">${K.esc(o.pengiriman.penerima)} &middot; ${K.esc(o.pengiriman.telepon)}</p><p class="text-slate-600">${K.esc(o.pengiriman.alamat)}, ${K.esc(o.pengiriman.kota)} ${K.esc(o.pengiriman.kodePos)}</p></div>` : ''}
      ${o.alasan && o.status === 'dibatalkan' ? `<p class="mt-2 text-xs text-rose-600">Alasan: ${K.esc(o.alasan)}</p>` : ''}</article>`).join('') || kosong('Tidak ada transaksi.');
  },
  async pengguna() {
    const [os, us] = await Promise.all([Api.adminPesanan(), Api.penggunaAll()]);
    $('#pg-isi').innerHTML = us.map((u, i) => `<tr class="baris border-t border-slate-100" style="animation-delay:${i * 40}ms"><td class="p-4"><div class="flex items-center gap-3">${avatar(u, 'w-9 h-9')}<b>${K.esc(u.username)}</b></div></td><td>${K.esc(u.email)}</td><td>${tgl(u.dibuat)}</td><td>${os.filter(o => o.userId === u.id).length}</td>
      <td><span class="px-2.5 py-1 rounded-full text-xs font-semibold ${u.aktif ? 'bg-brand-100 text-brand-700' : 'bg-rose-100 text-rose-700'}">${u.aktif ? 'Aktif' : 'Nonaktif'}</span></td><td class="pr-4 text-right"><button class="btn ${u.aktif ? 'btn-d' : 'btn-p'}" data-aksi="toggleUser" data-id="${u.id}">${u.aktif ? 'Nonaktifkan' : 'Aktifkan'}</button></td></tr>`).join('');
  },
  async ulasan() {
    $('#ul-tab').innerHTML = tab({ belum: 'Belum Dibalas', sudah: 'Sudah Dibalas', semua: 'Semua' }, filterUlasan, 'tabUlasan');
    const l = (await Api.ulasanAll()).filter(u => filterUlasan === 'semua' || (filterUlasan === 'sudah') === !!u.balasan);
    $('#ul-isi').innerHTML = l.map((u, i) => `<article class="panel baris" style="animation-delay:${i * 50}ms"><div class="flex justify-between gap-2"><div><b>${K.esc(u.nama)}</b><p class="text-xs text-slate-500">${K.esc(u.produk)} &middot; ${tgl(u.dibuat)}</p></div>${bintang(u.rating)}</div><p class="text-sm text-slate-600 mt-3">${K.esc(u.teks)}</p>
      ${u.balasan ? `<div class="mt-3 rounded-xl bg-brand-50 border-l-4 border-brand-500 px-3 py-2 text-sm"><b class="text-brand-700 text-xs">Komentar Admin &middot; ${tgl(u.balasan.dibuat)}</b><p class="text-slate-600 mt-0.5">${K.esc(u.balasan.teks)}</p></div>` : ''}
      <div class="flex justify-end mt-4"><button class="btn btn-p" data-aksi="balas" data-id="${u.id}">${u.balasan ? 'Ubah Komentar' : 'Beri Komentar'}</button></div></article>`).join('') || kosong('Tidak ada ulasan.');
  },
  async pesan() {
    $('#ps-tab').innerHTML = tab({ chat: 'Chat Pelanggan', tamu: 'Pesan Tamu' }, tabPesan, 'tabPesan');
    $('#ps-chat').classList.toggle('hidden', tabPesan !== 'chat'); $('#ps-isi').classList.toggle('hidden', tabPesan !== 'tamu');
    if (tabPesan === 'tamu') {   // formulir kontak dari pengunjung yang belum login (tidak bisa dibalas lewat chat -> balas lewat email)
      $('#ps-isi').innerHTML = (await Api.pesanKontak()).map((p, i) => `<article class="panel baris" style="animation-delay:${i * 50}ms"><div class="flex justify-between gap-2"><b>${K.esc(p.nama)}</b><span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-sun-400/30 text-amber-800">${K.esc(p.jenis)}</span></div><p class="text-xs text-slate-500">${K.esc(p.email)} &middot; ${tgl(p.dibuat)}</p><p class="text-sm mt-3" style="white-space:pre-wrap;overflow-wrap:anywhere">${K.esc(p.isi)}</p><div class="flex justify-end mt-3"><a class="btn btn-o" href="mailto:${K.esc(p.email)}?subject=${encodeURIComponent('Re: ' + p.jenis + ' - SawitKu')}">Balas lewat email</a></div></article>`).join('') || kosong('Belum ada pesan tamu.');
      return;
    }
    await segarkanDaftarChat(); jadwalDaftarChat();
  },
};
async function formProduk(id) {
  const p = id ? await Api.produkById(id) : { nama: '', kategori: KATEGORI[0], harga: '', stok: '', gambar: '', deskripsi: '', spesifikasi: {}, bestSeller: false }; fotoProduk = p.gambar || '';
  const m = Modal.buka(`<form id="fp" class="p-6 space-y-3" novalidate><h2 class="font-extrabold text-lg">${id ? 'Ubah' : 'Tambah'} Produk</h2>
    <input id="fp-nama" class="in" placeholder="Nama produk" maxlength="80" value="${K.esc(p.nama)}" aria-label="Nama"><select id="fp-kat" class="in" aria-label="Kategori">${KATEGORI.map(k => `<option ${k === p.kategori ? 'selected' : ''}>${K.esc(k)}</option>`).join('')}</select>
    <div class="grid grid-cols-2 gap-3"><input id="fp-harga" type="number" min="1000" class="in" placeholder="Harga (Rp)" value="${p.harga}" aria-label="Harga"><input id="fp-stok" type="number" min="0" class="in" placeholder="Stok" value="${p.stok}" aria-label="Stok"></div>
    <div class="flex items-center gap-3"><img id="fp-prev" class="w-16 h-16 rounded-xl object-cover bg-brand-50 ${p.gambar ? '' : 'hidden'}" src="${K.url(p.gambar)}" alt=""><label class="btn btn-o cursor-pointer">Unggah Foto<input id="fp-file" type="file" accept="image/jpeg,image/png,image/webp" class="hidden"></label></div>
    <input id="fp-url" class="in" placeholder="atau URL gambar (https://...)" maxlength="300" value="${p.gambar && p.gambar.startsWith('http') ? K.esc(p.gambar) : ''}" aria-label="URL gambar">
    <textarea id="fp-desk" rows="3" maxlength="400" class="in !h-auto py-2" placeholder="Deskripsi" aria-label="Deskripsi">${K.esc(p.deskripsi)}</textarea>
    <textarea id="fp-spek" rows="4" class="in !h-auto py-2" placeholder="Tinggi: 40 cm&#10;Cahaya: Terang" aria-label="Spesifikasi">${K.esc(Object.entries(p.spesifikasi || {}).map(([k, v]) => k + ': ' + v).join('\n'))}</textarea><p class="text-xs text-slate-500 -mt-2">Satu spesifikasi per baris, format <b>Nama: nilai</b> (pakai tanda titik dua). Maksimal 12 baris.</p>
    <label class="flex items-center gap-2 text-sm font-semibold"><input id="fp-best" type="checkbox" ${p.bestSeller ? 'checked' : ''} class="accent-green-700"> Tandai Terlaris</label><p id="fp-err" class="text-sm text-rose-600 min-h-5" role="alert"></p>
    <div class="flex justify-end gap-2"><button type="button" data-tutup class="btn btn-o">Batal</button><button class="btn btn-p">Simpan</button></div></form>`);
  $('#fp-file', m).onchange = async e => { const f = e.target.files[0], er = await K.cekGambar(f); $('#fp-err', m).textContent = er || ''; if (er) return e.target.value = '';
    try { fotoProduk = await K.kecilkan(f, 700); $('#fp-prev', m).src = fotoProduk; $('#fp-prev', m).classList.remove('hidden'); $('#fp-url', m).value = ''; } catch (x) { $('#fp-err', m).textContent = x.message; } };
  $('#fp', m).onsubmit = async e => { e.preventDefault(); const u = $('#fp-url', m).value.trim();
    try { await Api.produkSimpan({ id, nama: $('#fp-nama', m).value, kategori: $('#fp-kat', m).value, harga: $('#fp-harga', m).value, stok: $('#fp-stok', m).value, gambar: u || fotoProduk, deskripsi: $('#fp-desk', m).value, spek: $('#fp-spek', m).value, bestSeller: $('#fp-best', m).checked }); m.tutup(); Toast.ok('Produk disimpan.'); R.produk(); }
    catch (x) { $('#fp-err', m).textContent = x.message; } };
}
async function balas(id) {
  const r = (await Api.ulasanAll()).find(x => x.id === id); if (!r) return Toast.err('Ulasan tidak ditemukan.');
  const m = Modal.buka(`<div class="p-6"><h2 class="font-extrabold text-lg">Komentar untuk ${K.esc(r.nama)}</h2><p class="text-sm text-slate-500 mt-1 mb-3">Ulasan: ${K.esc(r.teks)}</p><textarea id="bl" rows="4" maxlength="300" class="in !h-auto py-2" placeholder="Tulis komentar untuk pembeli...">${K.esc(r.balasan ? r.balasan.teks : '')}</textarea><p id="bl-err" class="text-sm text-rose-600 min-h-5" role="alert"></p><div class="flex justify-end gap-2 mt-2"><button data-tutup class="btn btn-o">Batal</button><button id="bl-ok" class="btn btn-p">Kirim Komentar</button></div></div>`, 'max-w-md');
  $('#bl-ok', m).onclick = async () => { try { await Api.ulasanBalas(id, $('#bl', m).value); m.tutup(); Toast.ok('Komentar terkirim.'); R.ulasan(); } catch (x) { $('#bl-err', m).textContent = x.message; } };
}
async function tolak(id) {
  const m = Modal.buka(`<div class="p-6"><h2 class="font-extrabold text-lg">Tolak Pembayaran #${id}</h2><p class="text-sm text-slate-500 mt-1">Pesanan akan dibatalkan dan stok dikembalikan. Pembeli harus membuat pesanan baru.</p><textarea id="tl" rows="3" maxlength="200" class="in !h-auto py-2 mt-3" placeholder="Alasan penolakan"></textarea><div class="flex justify-end gap-2 mt-4"><button data-tutup class="btn btn-o">Batal</button><button id="tl-ok" class="btn btn-d">Tolak</button></div></div>`, 'max-w-md');
  $('#tl-ok', m).onclick = async () => { try { await Api.verifikasi(id, false, $('#tl', m).value.trim()); m.tutup(); Toast.ok('Pembayaran ditolak.'); R.pembayaran(); } catch (x) { Toast.err(x.message); } };
}
document.addEventListener('click', async e => {
  const a = e.target.closest('[data-aksi]'); if (!a) return; const id = +a.dataset.id, v = a.dataset.v;
  try { switch (a.dataset.aksi) {
    case 'rentang': rentang = v; R.tren(); break; case 'tabBayar': filterBayar = v; R.pembayaran(); break; case 'tabUlasan': filterUlasan = v; R.ulasan(); break;
    case 'edit': formProduk(id); break;
    case 'hapusProduk': if (await Modal.konfirmasi('Hapus produk ini secara permanen?', 'Hapus')) { await Api.produkHapus(id); Toast.ok('Produk dihapus.'); R.produk(); } break;
    case 'bukti': { const o = (await Api.adminPesanan()).find(x => x.id === id); if (!o) break; Modal.buka(`<div class="p-4"><img class="w-full rounded-xl" src="${K.url(o.bukti)}" alt="Bukti pembayaran"><button data-tutup class="btn btn-o w-full mt-3">Tutup</button></div>`, 'max-w-md'); break; }
    case 'setuju': if (await Modal.konfirmasi('Bukti sesuai? Pesanan akan diproses untuk pengiriman.', 'Setujui')) { await Api.verifikasi(id, true); Toast.ok('Pembayaran disetujui.'); R.pembayaran(); } break;
    case 'tolak': tolak(id); break; case 'kirim': await Api.kirimPesanan(id); Toast.ok('Pesanan ditandai dikirim.'); R.pembayaran(); break;
    case 'toggleUser': await Api.penggunaToggle(id); R.pengguna(); break;
    case 'balas': balas(id); break; } }
  catch (er) { Toast.err(er.message); }
});
$('#pr-baru').onclick = () => formProduk(); $('#pr-cari').oninput = e => { cari = e.target.value.slice(0, 60); R.produk(); };
(async () => {
  user = await Sesi.wajib('admin'); if (!user) return;
  $('#app').hidden = false; $('#logo').innerHTML = I('leaf', 'w-6 h-6'); $('#ikon-menu').innerHTML = I('menu');
  $$('.nav-item').forEach(a => { const s = a.querySelector('.ic') || a.querySelector('[data-ikon]'); if (s) s.innerHTML = I(a.dataset.ikon || 'out'); });
  Dash.init(R, user);
  lencanaA = Chat.lencana('pesan', () => Api.adminChatBelum());
})();
