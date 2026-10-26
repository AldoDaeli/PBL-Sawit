'use strict';
/* Dashboard customer. Markup ada di <template> pada index.html; berkas ini hanya mengambil data dan mengisinya (lihat T di core.js). */
let user, filterPesanan = 'semua', rentang = 'semua', fotoBaru = null, METODE = null;
const kelompok = { semua: 'Semua', proses: 'Dalam proses', selesai: 'Selesai', batal: 'Dibatalkan' };
const IKON_METODE = { qris: 'qr', bca: 'bank', bni: 'bank', bri: 'bank', permata: 'bank', mandiri: 'bank' };
const BAYAR = ['diproses', 'dikirim', 'selesai'];
const LUNAS = o => BAYAR.includes(o.status) && !!o.midtrans && ['settlement', 'capture'].includes(o.midtrans.status);   // angka belanja hanya dari pembayaran asli                       // status yang dihitung sebagai belanja
const metode = async () => METODE || (METODE = await Api.metodeBayar());
const labelMetode = async kode => ((await metode()).find(m => m.kode === kode) || {}).label || 'Midtrans';

const tabs = (map, cur, aksi) => Object.entries(map).map(([kode, nama]) => T.satu('t-tab', { kode, nama, aksi, aktif: kode === cur }));
const kosong = (teks, tombol, href) => T.satu('t-kosong', { teks, tombol, href });
const stat = (warna, judul, nilai, ket, rp = false) => T.satu('t-stat', { warna, judul, nilai, ket, rp: rp ? '1' : '' });
function hitungAngka(root) { $$('[data-hitung]', root).forEach(e => Animasi.hitung(e, +e.dataset.hitung, e.dataset.rp ? rp : undefined)); }
async function badgeNav() { const c = await Api.jumlahKeranjang(), a = $('.nav-item[data-sec="keranjang"]'); let p = $('.pin', a); if (!c) return p && p.remove(); if (!p) { p = document.createElement('span'); p.className = 'pin'; a.append(p); } p.textContent = c; }

// Data turunan satu pesanan untuk template t-pesanan
function dataPesanan(o, sudah, daftarMetode) {
  const m = daftarMetode.find(x => x.kode === o.metode);
  return { ...o, namaStatus: namaStatus(o), kelasStatus: STATUS[o.status][2], labelMetode: m ? m.label : 'Midtrans',
    items: o.items.map(x => ({ ...x, bisaUlas: o.status === 'selesai' && x.produkId != null && !sudah.has(x.produkId) })),
    infoBatal: o.status === 'dibatalkan' && !!o.alasan, infoTolak: o.status === 'menunggu_bayar' && !!o.ditolak,
    menungguBayar: o.status === 'menunggu_bayar', labelBayar: o.ditolak ? 'Unggah ulang bukti' : 'Bayar sekarang', menungguVerifikasi: o.status === 'menunggu_verifikasi',
    infoTiba: o.status === 'dikirim' && !!o.batasTerima, bisaTerima: o.status === 'dikirim', bisaLacak: BAYAR.includes(o.status),
    fotoTerima: o.fotoTerima || '', otomatis: o.status === 'selesai' && o.otomatis };
}

let chatC = null, lencanaC = null, lacakAwal = '';
const R = {
  async lacak() { const k = lacakAwal; lacakAwal = ''; Lacak.pasang($('#lacak-root'), k); },
  async pesan() {
    if (chatC) chatC.hentikan();
    chatC = Chat.pasang($('#chat-root'), { saya: 'customer', muat: p => Api.chat(p), kirim: isi => Api.chatKirim(isi), diMuat: () => lencanaC && lencanaC.segarkan() });
  },
  async ringkasan() {
    const [os, jmlKer] = await Promise.all([Api.pesananSaya(), Api.jumlahKeranjang()]), belanja = os.filter(LUNAS).reduce((a, o) => a + o.total, 0), akt = os.filter(o => STATUS[o.status][1] === 'proses').length;
    const st = $('#r-stat'); st.replaceChildren(stat('g1', 'Total belanja', belanja, `${os.filter(o => o.status === 'selesai').length} pesanan selesai`, true), stat('g2', 'Pesanan berjalan', akt, 'Menunggu bayar atau dikirim'), stat('g3', 'Item di keranjang', jmlKer, 'Siap untuk checkout')); hitungAngka(st);
    const s = Grafik.seri(os.filter(LUNAS).map(o => ({ t: o.dibuat, v: o.total })), 'minggu', i => i.v); Grafik.bar($('#r-grafik'), s.labels, [{ nama: 'Belanja', warna: '#38995e', data: s.data }], rp);
    const g = { selesai: 0, proses: 0, batal: 0 }; os.forEach(o => g[STATUS[o.status][1]]++);
    Grafik.donut($('#r-donut'), [{ label: 'Selesai', nilai: g.selesai, warna: '#38995e' }, { label: 'Dalam proses', nilai: g.proses, warna: '#f7c948' }, { label: 'Dibatalkan', nilai: g.batal, warna: '#fb7185' }], ' pesanan');
    const t = $('#r-terbaru'); if (os.length) T.daftar(t, 't-terbaru', os.slice(0, 4).map(o => ({ ...o, gambar: o.items[0].gambar, judul: o.items[0].nama + (o.items.length > 1 ? ` +${o.items.length - 1} lainnya` : ''), namaStatus: namaStatus(o), kelasStatus: STATUS[o.status][2] }))); else t.replaceChildren(kosong('Belum ada pesanan.', 'Mulai belanja', '/#katalog'));
  },
  async keranjang() {
    const k = await Api.keranjang(), el = $('#k-isi'); badgeNav();
    if (!k.length) return el.replaceChildren(kosong('Keranjangmu masih kosong.', 'Mulai belanja', '/#katalog'));
    const total = k.reduce((a, c) => a + c.p.harga * c.qty, 0), v = T.satu('t-keranjang', { jumlah: k.reduce((a, c) => a + c.qty, 0), total });
    T.daftar($('#k-daftar', v), 't-ker-item', k); el.replaceChildren(v);
  },
  async pesanan() {
    $('#p-tab').replaceChildren(...tabs(kelompok, filterPesanan, 'tabPesanan'));
    const [semua, dm] = await Promise.all([Api.pesananSaya(), metode()]), os = semua.filter(o => filterPesanan === 'semua' || STATUS[o.status][1] === filterPesanan);
    // produk yang sudah diulas (satu permintaan per produk unik dari pesanan selesai)
    const sudah = new Set(), calon = [...new Set(os.filter(o => o.status === 'selesai').flatMap(o => o.items.map(x => x.produkId)).filter(x => x != null))];
    await Promise.all(calon.map(async pid => { if (await Api.sudahUlas(pid)) sudah.add(pid); }));
    const isi = $('#p-isi'); if (!os.length) return isi.replaceChildren(kosong('Tidak ada pesanan di kategori ini.'));
    isi.replaceChildren(...os.map((o, i) => { const e = T.satu('t-pesanan', dataPesanan(o, sudah, dm)); e.dataset.id = o.id; e.style.animationDelay = Math.min(i, 8) * 50 + 'ms'; return e; }));
  },
  async favorit() {
    const [ids, ps] = await Promise.all([Api.favorit(), Api.produk()]), f = ps.filter(p => ids.includes(p.id)), el = $('#f-isi');
    if (f.length) T.daftar(el, 't-favorit', f); else el.replaceChildren(Object.assign(kosong('Belum ada produk favorit.', 'Jelajahi produk', '/#katalog'), { className: 'col-span-full' }));
    if (!f.length) el.firstElementChild.classList.add('col-span-full');
  },
  async statistik() {
    $('#s-tab').replaceChildren(...tabs({ semua: 'Semua waktu', bulan: 'Bulanan', minggu: 'Mingguan', hari: 'Hari ini' }, rentang, 'rentang'));
    const os = (await Api.pesananSaya()).filter(LUNAS), t = os.map(o => ({ t: o.dibuat, v: o.total })), sb = Grafik.seri(t, rentang, i => i.v), sj = Grafik.seri(t, rentang, () => 1);
    const jum = sj.data.reduce((a, b) => a + b, 0), tot = sb.data.reduce((a, b) => a + b, 0), k = $('#s-kartu');
    k.replaceChildren(stat('g1', 'Total belanja', tot, 'pada rentang ini', true), stat('g2', 'Jumlah pesanan', jum, 'pesanan yang sudah dibayar'), stat('g3', 'Rata-rata pesanan', jum ? tot / jum : 0, 'per transaksi', true));
    hitungAngka(k); Grafik.bar($('#s-bar'), sb.labels, [{ nama: 'Belanja', warna: '#38995e', data: sb.data }], rp); Grafik.area($('#s-area'), sj.labels, sj.data, '#0f766e', v => v + ' pesanan');
  },
  profil() { $('#pf-foto').innerHTML = avatar({ ...user, foto: fotoBaru || user.foto }, 'w-full h-full text-3xl'); $('#pf-user').value = user.username; $('#pf-email').value = user.email;
    $('#pf-tel').value = user.telepon || ''; $('#pf-alm').value = user.alamat || ''; $('#pf-kota').value = user.kota || ''; $('#pf-pos').value = user.kodePos || ''; },
};

/* ---- Checkout: pilih metode bayar + alamat; pesanan dibuat dari dalam modal agar galat validasi tampil di form ---- */
function checkout() {
  return new Promise(async ok => {
    const dm = await metode(), m = Modal.dari('t-checkout', user, 'max-w-xl');
    $('#co-metode', m).replaceChildren(...dm.map((x, i) => { const e = T.satu('t-opsi-metode', { ...x, ikon: IKON_METODE[x.kode] || 'card' }); $('input', e).checked = i === 0; return e; })); ikon(m);
    m.addEventListener('click', e => { if (e.target.closest('[data-tutup]')) ok(null); });
    $('form', m).onsubmit = async e => { e.preventDefault(); const b = $('#al-btn', m), pilih = $('input[name=metode]:checked', m); b.disabled = true;
      if (!pilih) { $('#al-err', m).textContent = 'Pilih metode pembayaran.'; b.disabled = false; return; }
      try { const o = await Api.checkout({ metode: pilih.value, penerima: $('#al-pen', m).value, telepon: $('#al-tel', m).value, alamat: $('#al-alm', m).value,
                                          kota: $('#al-kota', m).value, kodePos: $('#al-pos', m).value, simpan: $('#al-simpan', m).checked });
        m.tutup(); ok(o); }
      catch (x) { $('#al-err', m).textContent = x.message; b.disabled = false; } };
  });
}

/* ---- Konfirmasi barang diterima (foto opsional). Tanpa konfirmasi, pesanan selesai otomatis 24 jam setelah admin menandai tiba. ---- */
async function terima(id) {
  const o = await Api.pesananById(id); if (!o) return Toast.err('Pesanan tidak ditemukan.'); let foto = null;
  const m = Modal.dari('t-terima', { ...o, infoTiba: !!o.batasTerima }, 'max-w-md');
  $('#tr-file', m).onchange = async e => { const f = e.target.files[0], er = await K.cekGambar(f), p = $('#tr-prev', m); $('#tr-err', m).textContent = er || ''; foto = null;
    if (er) { p.classList.add('hidden'); e.target.value = ''; return; }
    try { foto = await K.kecilkan(f, 900); p.src = foto; p.classList.remove('hidden'); } catch (x) { $('#tr-err', m).textContent = x.message; } };
  $('#tr-kirim', m).onclick = async () => { const b = $('#tr-kirim', m); b.disabled = true;
    try { await Api.terima(id, foto); m.tutup(); Toast.ok('Terima kasih! Pesanan selesai.'); R.pesanan(); } catch (x) { $('#tr-err', m).textContent = x.message; b.disabled = false; } };
}

/* ---- Ulasan: bintang 1-5, awalnya belum dipilih ---- */
async function ulas(pid) {
  const p = await Api.produkById(pid); if (!p) return Toast.err('Produk tidak ditemukan.'); let r = 0;
  const m = Modal.dari('t-ulas', p, 'max-w-md'), bin = $('#ul-bin', m);
  const gambar = () => bin.replaceChildren(...[1, 2, 3, 4, 5].map(n => T.satu('t-bintang-pilih', { n, on: n <= r, aktif: n === r })));
  gambar(); bin.onclick = e => { const b = e.target.closest('[data-r]'); if (b) { r = +b.dataset.r; gambar(); } };
  $('#ul-kirim', m).onclick = async () => { if (!r) return $('#ul-err', m).textContent = 'Pilih rating 1 sampai 5 bintang.';
    try { await Api.kirimUlasan(pid, r, $('#ul-teks', m).value); m.tutup(); Toast.ok('Ulasan berhasil dipublikasikan.'); R.pesanan(); } catch (x) { $('#ul-err', m).textContent = x.message; } };
}

document.addEventListener('click', async e => {
  const a = e.target.closest('[data-aksi]'); if (!a) return; const kartu = a.closest('[data-id]'), id = +(a.dataset.id || (kartu && kartu.dataset.id)), v = a.dataset.v;
  try { switch (a.dataset.aksi) {
    case 'qty': { const c = (await Api.keranjang()).find(x => x.produkId === id); if (!c) break; const n = c.qty + +a.dataset.d; if (n < 1) break; await Api.kerSet(id, n); R.keranjang(); break; }
    case 'hapus': await Api.kerHapus(id); R.keranjang(); Toast.ok('Item dihapus.'); break;
    case 'checkout': { const o = await checkout(); if (!o) break; user = await Api.saya(true); Toast.ok('Pesanan dibuat. Lanjut ke pembayaran.'); location.href = '/bayar/' + o.id; break; }
    case 'tabPesanan': filterPesanan = v; R.pesanan(); break; case 'rentang': rentang = v; R.statistik(); break;
    case 'lacak': lacakAwal = String(id); if (location.hash === '#lacak') R.lacak(); else location.hash = '#lacak'; break;
    case 'ulas': ulas(+a.dataset.p); break;
    case 'batal': if (await Modal.konfirmasi('Batalkan pesanan ini? Tagihan pembayarannya ikut dibatalkan.', 'Batalkan pesanan')) { await Api.batal(id); Toast.ok('Pesanan dibatalkan.'); R.pesanan(); } break;
    case 'terima': terima(id); break;
    case 'favCart': await Api.kerAdd(id, 1); Toast.ok('Ditambahkan ke keranjang.'); badgeNav(); break;
    case 'favHapus': await Api.favToggle(id); R.favorit(); break; } } catch (er) { Toast.err(er.message); }
});
$('#pf-file').onchange = async e => { const f = e.target.files[0], er = await K.cekGambar(f); $('#pf-err').textContent = er || ''; if (er) { fotoBaru = null; e.target.value = ''; return; }
  try { fotoBaru = await K.kecilkan(f, 320); $('#pf-foto').innerHTML = avatar({ ...user, foto: fotoBaru }, 'w-full h-full text-3xl'); } catch (x) { $('#pf-err').textContent = x.message; } };
$('#pf').onsubmit = async e => { e.preventDefault(); try { user = await Api.profil({ username: $('#pf-user').value.trim(), email: $('#pf-email').value.trim(), foto: fotoBaru,
    telepon: $('#pf-tel').value.trim(), alamat: $('#pf-alm').value.trim(), kota: $('#pf-kota').value.trim(), kodePos: $('#pf-pos').value.trim() }); fotoBaru = null; Dash.segarkanAvatar(user); $('#pf-err').textContent = ''; Toast.ok('Profil diperbarui.'); } catch (x) { $('#pf-err').textContent = x.message; } };
$('#pf-ganti-email').onclick = () => {
  const m = Modal.dari('t-ganti-email', {}); let tahap = 1; const err = $('#ge-err', m), btn = $('#ge-ok', m);
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
  $('#app').hidden = false; ikon();
  Dash.init(R, user); badgeNav().catch(() => {});
  lencanaC = Chat.lencana('pesan', () => Api.chatBelum());
})();
