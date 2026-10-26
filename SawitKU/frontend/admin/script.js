'use strict';
/* Dashboard admin. Markup ada di <template> pada index.html; berkas ini mengambil data dan mengisinya (lihat T di core.js). */
let tabPesan = 'chat', uidChat = null, chatA = null, lencanaA = null, timerDaftar = null;
let user, rentang = 'bulan', filterBayar = 'menunggu_verifikasi', filterUlasan = 'belum', cari = '', fotoProduk = null, lacakAwal = '';
const MIDTRANS = {   // status transaksi Midtrans -> [teks, kelas]; hanya bahan pertimbangan, bukan persetujuan
  pending: ['Menunggu bayar', 'bg-amber-100 text-amber-800'], settlement: ['Terbayar', 'bg-brand-100 text-brand-800'], capture: ['Terbayar', 'bg-brand-100 text-brand-800'],
  expire: ['Kedaluwarsa', 'bg-rose-100 text-rose-800'], cancel: ['Dibatalkan', 'bg-rose-100 text-rose-800'], deny: ['Ditolak', 'bg-rose-100 text-rose-800'], failure: ['Gagal', 'bg-rose-100 text-rose-800'],
};
const TERBAYAR = ['settlement', 'capture'];
const laku = o => ['diproses', 'dikirim', 'selesai'].includes(o.status);
// Angka dashboard (pendapatan, terjual, grafik) hanya dari transaksi ASLI: disetujui admin DAN tercatat lunas di Midtrans (settlement/capture)
const lunasMid = o => laku(o) && !!o.midtrans && TERBAYAR.includes(o.midtrans.status);
const tabs = (map, cur, aksi) => Object.entries(map).map(([kode, nama]) => T.satu('t-tab', { kode, nama, aksi, aktif: kode === cur }));
const stat = (warna, judul, nilai, ket, rp = false) => T.satu('t-stat', { warna, judul, nilai, ket, rp: rp ? '1' : '' });
const kosong = teks => T.satu('t-kosong', { teks });
const hitungAngka = root => $$('[data-hitung]', root).forEach(e => Animasi.hitung(e, +e.dataset.hitung, e.dataset.rp ? rp : undefined));
const pesananDari = id => Api.adminPesanan().then(l => l.find(x => x.id === id));

/* ---- Chat pelanggan: daftar percakapan (kiri) + percakapan terpilih (kanan). Teks pelanggan hanya lewat textContent (T). ---- */
async function segarkanDaftarChat() {
  const box = $('#ps-daftar'), l = await Api.adminChatDaftar();
  if (!l.length) return box.replaceChildren(T.satu('t-chat-kosong', {}));
  box.replaceChildren(...l.map(c => T.satu('t-chat-item', { ...c, nama: c.username + (c.aktif ? '' : ' (nonaktif)'), cuplikan: (c.dari === 'admin' ? 'Kamu: ' : '') + c.terakhir,
    tanggal: tgl(c.dibuat, true), belumTeks: c.belum > 99 ? '99+' : c.belum, aktif: c.userId === uidChat })));
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
    diMuat: d => { if (d.pelanggan) judul.textContent = d.pelanggan.username + ' · ' + d.pelanggan.email + (d.pelanggan.aktif ? '' : ' (nonaktif)'); segarkanDaftarChat().catch(() => {}); lencanaA && lencanaA.segarkan(); } });
}
document.addEventListener('click', e => {
  const b = e.target.closest('#ps-daftar [data-uid]'); if (b) bukaChat(+b.dataset.uid);
  const t = e.target.closest('[data-aksi="tabPesan"]'); if (t) { tabPesan = t.dataset.v; R.pesan().catch(er => Toast.err(er.message)); }
});

// Data turunan satu pesanan untuk template t-pesanan
function dataPesanan(o) {
  const mid = o.midtrans, st = mid ? mid.status : '', ms = MIDTRANS[st] || [st || 'Belum ada', 'bg-slate-100 text-slate-700'];
  return { ...o, namaStatus: namaStatus(o), kelasStatus: STATUS[o.status][2], ringkas: o.items.map(x => `${x.nama} x${x.qty}`).join(', '),
    adaMidtrans: !!mid, labelMetode: mid && mid.data.label || '', teksMidtrans: ms[0], kelasMidtrans: ms[1], beda: !!mid && o.status === 'menunggu_verifikasi' && !TERBAYAR.includes(st),
    bukti: o.bukti || '', bisaVerifikasi: o.status === 'menunggu_verifikasi', bisaLacak: ['dikirim', 'selesai'].includes(o.status), bisaKirim: o.status === 'diproses',
    bisaSampai: o.status === 'dikirim' && !(o.waktu && o.waktu.sampai), menungguTerima: o.status === 'dikirim' && !!o.batasTerima,
    fotoTerima: o.fotoTerima || '', otomatis: o.status === 'selesai' && o.otomatis, infoTolak: o.status === 'menunggu_bayar' && o.ditolak > 0, infoBatal: o.status === 'dibatalkan' && !!o.alasan };
}

const R = {
  async lacak() { const k = lacakAwal; lacakAwal = ''; Lacak.pasang($('#lacak-root'), k); },
  async ringkasan() {
    const [os, ps, pengguna] = await Promise.all([Api.adminPesanan(), Api.produk(), Api.penggunaAll()]), akt = os.filter(o => o.status === 'menunggu_bayar').length;
    const pend = os.filter(lunasMid).reduce((a, o) => a + o.total, 0), tolak = os.filter(o => o.ditolak > 0).length, st = $('#r-stat');
    st.replaceChildren(stat('g1', 'Total pendapatan', pend, 'lunas di Midtrans & disetujui', true), stat('g2', 'Produk terjual', os.filter(lunasMid).reduce((a, o) => a + o.items.reduce((x, i) => x + i.qty, 0), 0), 'dari pesanan lunas'), stat('g3', 'Total stok', ps.reduce((a, p) => a + p.stok, 0), `${ps.length} jenis produk`), stat('g4', 'Pengguna terdaftar', pengguna.length, 'akun customer'),
      stat('g2', 'Checkout berjalan', akt, 'belum dibayar'), stat('g3', 'Menunggu persetujuan', os.filter(o => o.status === 'menunggu_verifikasi').length, 'bukti perlu diperiksa'), stat('g1', 'Bukti pernah ditolak', tolak, 'pembeli bisa unggah ulang'), stat('g4', 'Total pesanan', os.length, 'semua status'));
    hitungAngka(st); this.tren(os);
    const jual = {}; os.filter(lunasMid).forEach(o => o.items.forEach(i => jual[i.nama] = (jual[i.nama] || 0) + i.qty)); const top = Object.entries(jual).sort((x, y) => y[1] - x[1]).slice(0, 6);
    Grafik.bar($('#r-bar'), top.map(([n]) => n.length > 11 ? n.slice(0, 10) + '…' : n), [{ nama: 'Terjual', warna: '#38995e', data: top.map(x => x[1]) }], v => v + ' terjual');
    const g = { selesai: 0, proses: 0, batal: 0 }; os.forEach(o => g[STATUS[o.status][1]]++);
    Grafik.donut($('#r-donut'), [{ label: 'Selesai', nilai: g.selesai, warna: '#38995e' }, { label: 'Dalam proses', nilai: g.proses, warna: '#f7c948' }, { label: 'Dibatalkan', nilai: g.batal, warna: '#fb7185' }], ' pesanan');
  },
  async tren(os) {
    os = os || await Api.adminPesanan();
    $('#r-tab').replaceChildren(...tabs({ semua: 'Semua', bulan: 'Bulanan', minggu: 'Mingguan', hari: 'Hari ini' }, rentang, 'rentang'));
    const t = os.filter(lunasMid).map(o => ({ t: o.dibuat, v: o.total })), s = Grafik.seri(t, rentang, i => i.v), c = Grafik.banding(t, rentang, i => i.v), el = $('#r-tren');
    const nama = { hari: 'kemarin', minggu: 'minggu lalu', bulan: 'bulan lalu' }[rentang], total = s.data.reduce((x, y) => x + y, 0); let info = `Total ${rp(total)}`, warna = 'text-slate-500';
    // Persentase hanya ditampilkan bila data pembanding cukup besar, agar tidak melonjak ekstrem akibat sampel kecil.
    if (c && c.prev >= 150000) { const p = Math.round((c.now - c.prev) / c.prev * 100); info += `  |  ${p >= 0 ? '▲ naik' : '▼ turun'} ${Math.min(Math.abs(p), 300)}${Math.abs(p) > 300 ? '+' : ''}% dibanding ${nama}`; warna = p >= 0 ? 'text-brand-600' : 'text-rose-600'; }
    else if (c && c.now > 0) info += `  |  belum cukup data pembanding (${nama})`;
    else if (c) info += `  |  ${nama} belum ada transaksi`;
    el.textContent = info; el.className = 'ml-2 text-sm font-bold ' + warna; Grafik.area($('#r-area'), s.labels, s.data, '#38995e', rp);
  },
  async produk() {
    const a = (await Api.produk()).filter(p => !cari || p.nama.toLowerCase().includes(cari.toLowerCase())), tb = $('#pr-isi');
    if (a.length) T.daftar(tb, 't-produk-baris', a.map(p => ({ ...p, tipis: p.stok < 10 }))); else tb.replaceChildren(T.satu('t-produk-kosong', {}));
  },
  async pembayaran() {
    const os = await Api.adminPesanan(), map = { menunggu_verifikasi: 'Menunggu verifikasi', menunggu_bayar: 'Belum bayar', diproses: 'Siap dikirim', dikirim: 'Dikirim', selesai: 'Selesai', dibatalkan: 'Dibatalkan', semua: 'Semua' };
    $('#pb-tab').replaceChildren(...tabs(map, filterBayar, 'tabBayar')); const l = os.filter(o => filterBayar === 'semua' || o.status === filterBayar), el = $('#pb-isi');
    el.replaceChildren(...(l.length ? l.map((o, i) => { const e = T.satu('t-pesanan', dataPesanan(o)); e.style.animationDelay = Math.min(i, 8) * 45 + 'ms'; return e; }) : [kosong('Tidak ada pesanan di kategori ini.')]));
  },
  async pengguna() {
    const [os, us] = await Promise.all([Api.adminPesanan(), Api.penggunaAll()]), tb = $('#pg-isi');
    tb.replaceChildren(...us.map(u => { const e = T.satu('t-pengguna-baris', { ...u, jmlPesanan: os.filter(o => o.userId === u.id).length, teksStatus: u.aktif ? 'Aktif' : 'Nonaktif', teksAksi: u.aktif ? 'Nonaktifkan' : 'Aktifkan' }); $('[data-avatar]', e).innerHTML = avatar(u, 'w-9 h-9'); return e; }));
  },
  async ulasan() {
    $('#ul-tab').replaceChildren(...tabs({ belum: 'Belum dibalas', sudah: 'Sudah dibalas', semua: 'Semua' }, filterUlasan, 'tabUlasan'));
    const l = (await Api.ulasanAll()).filter(u => filterUlasan === 'semua' || (filterUlasan === 'sudah') === !Balasan.perluAdmin(u)), el = $('#ul-isi');
    el.replaceChildren(...(l.length ? l.map(u => { const e = T.satu('t-ulasan', { ...u, perluAdmin: Balasan.perluAdmin(u), labelBalas: u.lanjutan.length ? 'Balas pelanggan' : (u.balasan ? 'Ubah komentar' : 'Beri komentar') });
      $('[data-balasan]', e).replaceWith(...Balasan.nodes(u, u.nama)); return e; }) : [kosong('Tidak ada ulasan.')]));
  },
  async pesan() {
    $('#ps-tab').replaceChildren(...tabs({ chat: 'Chat pelanggan', tamu: 'Pesan tamu' }, tabPesan, 'tabPesan'));
    $('#ps-chat').classList.toggle('hidden', tabPesan !== 'chat'); $('#ps-isi').classList.toggle('hidden', tabPesan !== 'tamu');
    if (tabPesan === 'tamu') {   // formulir kontak dari pengunjung yang belum login (tidak bisa dibalas lewat chat -> balas lewat email)
      const l = await Api.pesanKontak();
      $('#ps-isi').replaceChildren(...(l.length ? l.map(p => T.satu('t-pesan-tamu', { ...p, mailto: `mailto:${p.email}?subject=${encodeURIComponent('Re: ' + p.jenis + ' - SawitKu')}` })) : [kosong('Belum ada pesan tamu.')]));
      return;
    }
    await segarkanDaftarChat(); jadwalDaftarChat();
  },
};

async function formProduk(id) {
  const p = id ? await Api.produkById(id) : { nama: '', kategori: KATEGORI[0], harga: '', stok: '', gambar: '', deskripsi: '', spesifikasi: {}, bestSeller: false }; fotoProduk = p.gambar || '';
  const m = Modal.dari('t-produk-form', { ...p, judul: (id ? 'Ubah' : 'Tambah') + ' produk', urlGambar: p.gambar && p.gambar.startsWith('http') ? p.gambar : '', spekTeks: Object.entries(p.spesifikasi || {}).map(([k, v]) => k + ': ' + v).join('\n') });
  $('#fp-kat', m).replaceChildren(...KATEGORI.map(k => new Option(k, k, false, k === p.kategori))); $('#fp-best', m).checked = !!p.bestSeller;
  if (K.url(p.gambar)) $('#fp-prev', m).classList.remove('hidden');
  $('#fp-file', m).onchange = async e => { const f = e.target.files[0], er = await K.cekGambar(f); $('#fp-err', m).textContent = er || ''; if (er) return e.target.value = '';
    try { fotoProduk = await K.kecilkan(f, 700); $('#fp-prev', m).src = fotoProduk; $('#fp-prev', m).classList.remove('hidden'); $('#fp-url', m).value = ''; } catch (x) { $('#fp-err', m).textContent = x.message; } };
  $('#fp', m).onsubmit = async e => { e.preventDefault(); const u = $('#fp-url', m).value.trim();
    try { await Api.produkSimpan({ id, nama: $('#fp-nama', m).value, kategori: $('#fp-kat', m).value, harga: $('#fp-harga', m).value, stok: $('#fp-stok', m).value, gambar: u || fotoProduk, deskripsi: $('#fp-desk', m).value, spek: $('#fp-spek', m).value, bestSeller: $('#fp-best', m).checked }); m.tutup(); Toast.ok('Produk disimpan.'); R.produk(); }
    catch (x) { $('#fp-err', m).textContent = x.message; } };
}
async function balas(id) {
  const r = (await Api.ulasanAll()).find(x => x.id === id); if (!r) return Toast.err('Ulasan tidak ditemukan.');
  const m = Modal.dari('t-balas-modal', { judul: (r.lanjutan.length ? 'Balas ' : 'Komentar untuk ') + r.nama, teks: r.teks, komentar: r.balasan ? r.balasan.teks : '' }, 'max-w-md');
  $('#bl-ok', m).onclick = async () => { try { await Api.ulasanBalas(id, $('#bl', m).value); m.tutup(); Toast.ok('Komentar terkirim.'); R.ulasan(); } catch (x) { $('#bl-err', m).textContent = x.message; } };
}
function kirim(id) {
  const m = Modal.dari('t-kirim-modal', { id }, 'max-w-md');
  $('#kr-ok', m).onclick = async () => { try { await Api.kirimPesanan(id, $('#kr-kurir', m).value.trim(), $('#kr-resi', m).value.trim()); m.tutup(); Toast.ok('Pesanan ditandai dikirim.'); R.pembayaran(); } catch (x) { $('#kr-err', m).textContent = x.message; } };
}
function tolak(id) {
  const m = Modal.dari('t-tolak-modal', { id }, 'max-w-md');
  $('#tl-ok', m).onclick = async () => { try { await Api.verifikasi(id, false, $('#tl', m).value.trim()); m.tutup(); Toast.ok('Pembayaran ditolak.'); R.pembayaran(); } catch (x) { Toast.err(x.message); } };
}
async function setuju(id) {
  const o = await pesananDari(id); if (!o) return;
  // Midtrans hanya bahan pertimbangan: bila belum tercatat terbayar, admin diminta memastikan dulu
  const st = o.midtrans ? o.midtrans.status : '', peringatan = TERBAYAR.includes(st) ? '' : ' Midtrans belum mencatat pembayaran ini (status: ' + ((MIDTRANS[st] || [st || 'belum ada'])[0]) + '). Pastikan dana benar-benar masuk.';
  if (await Modal.konfirmasi('Bukti sesuai? Pesanan akan diproses untuk pengiriman.' + peringatan, 'Setujui')) { await Api.verifikasi(id, true); Toast.ok('Pembayaran disetujui.'); R.pembayaran(); }
}
document.addEventListener('click', async e => {
  const a = e.target.closest('[data-aksi]'); if (!a) return; const kartu = a.closest('[data-id]'), id = +(a.dataset.id || (kartu && kartu.dataset.id)), v = a.dataset.v;
  try { switch (a.dataset.aksi) {
    case 'rentang': rentang = v; R.tren(); break; case 'tabBayar': filterBayar = v; R.pembayaran(); break; case 'tabUlasan': filterUlasan = v; R.ulasan(); break;
    case 'edit': formProduk(id); break;
    case 'hapusProduk': if (await Modal.konfirmasi('Hapus produk ini secara permanen?', 'Hapus')) { await Api.produkHapus(id); Toast.ok('Produk dihapus.'); R.produk(); } break;
    case 'bukti': { const o = await pesananDari(id); if (o) Modal.dari('t-gambar', { src: o.bukti, alt: 'Bukti pembayaran' }, 'max-w-md'); break; }
    case 'fotoTerima': { const o = await pesananDari(id); if (o) Modal.dari('t-gambar', { src: o.fotoTerima, alt: 'Foto barang diterima pembeli' }, 'max-w-md'); break; }
    case 'cekMidtrans': await Api.adminCekMidtrans(id); Toast.ok('Status Midtrans diperbarui.'); R.pembayaran(); break;
    case 'setuju': setuju(id); break; case 'tolak': tolak(id); break; case 'kirim': kirim(id); break;
    case 'sampai': if (await Modal.konfirmasi(`Tandai pesanan #${id} sudah sampai? Pembeli punya ${CFG.AUTO_TERIMA_JAM} jam untuk konfirmasi, lalu pesanan selesai otomatis.`, 'Tandai sampai')) { await Api.tandaiSampai(id); Toast.ok('Pesanan ditandai sudah sampai.'); R.pembayaran(); } break;
    case 'lacak': lacakAwal = String(id); if (location.hash === '#lacak') R.lacak(); else location.hash = '#lacak'; break;
    case 'toggleUser': await Api.penggunaToggle(id); R.pengguna(); break;
    case 'balas': balas(id); break; } }
  catch (er) { Toast.err(er.message); }
});
$('#pr-baru').onclick = () => formProduk(); $('#pr-cari').oninput = e => { cari = e.target.value.slice(0, 60); R.produk(); };
(async () => {
  user = await Sesi.wajib('admin'); if (!user) return;
  $('#app').hidden = false; ikon();
  Dash.init(R, user);
  lencanaA = Chat.lencana('pesan', () => Api.adminChatBelum());
})();
