'use strict';
/* Halaman bayar: QR/VA dari Midtrans ditampilkan di sini, lalu pembeli WAJIB mengunggah bukti. Admin yang menyetujui. */
const oid = Number(location.pathname.split('/').filter(Boolean).pop());   // /bayar/<id pesanan>
const IKON_METODE = { qris: 'qr', bca: 'bank', bni: 'bank', bri: 'bank', permata: 'bank', mandiri: 'bank' };
const STATUS_MIDTRANS = {
  pending: ['Menunggu pembayaran', 'bg-amber-100 text-amber-800'], settlement: ['Pembayaran terdeteksi', 'bg-brand-100 text-brand-800'], capture: ['Pembayaran terdeteksi', 'bg-brand-100 text-brand-800'],
  expire: ['Tagihan kedaluwarsa', 'bg-rose-100 text-rose-800'], cancel: ['Tagihan dibatalkan', 'bg-rose-100 text-rose-800'], deny: ['Ditolak Midtrans', 'bg-rose-100 text-rose-800'], failure: ['Gagal', 'bg-rose-100 text-rose-800'],
};
let pesanan = null, bukti = null, timer = null, poll = null;

function tampilkanTagihan(o) {
  const m = o.midtrans, d = m ? m.data : {}, area = $('#area-tagihan'), st = $('#status-midtrans'), s = STATUS_MIDTRANS[m ? m.status : 'pending'] || [m ? m.status : '', 'bg-slate-100 text-slate-700'];
  st.textContent = s[0]; st.className = 'lencana ' + s[1];
  area.replaceChildren(T.klon({ qris: 't-tagihan-qris', va: 't-tagihan-va', bill: 't-tagihan-bill' }[d.jenis] || 't-tagihan-va', d));
}
function mulaiHitung(batas) {
  clearInterval(timer); const el = $('#hitung-mundur');
  const t = () => { const s = Math.max(0, Math.floor((batas - Date.now()) / 1000)); el.textContent = s ? `Sisa ${Math.floor(s / 3600)} jam ${String(Math.floor(s % 3600 / 60)).padStart(2, '0')} menit ${String(s % 60).padStart(2, '0')} detik` : 'Batas waktu habis'; if (!s) clearInterval(timer); };
  t(); timer = setInterval(t, 1000);
}
function pasangHalaman(o) {
  pesanan = o; const d = o.midtrans ? o.midtrans.data : {};
  $('#isi').replaceChildren(T.klon('t-bayar', { ...o, label: d.label || 'Pembayaran' }));
  tampilkanTagihan(o); mulaiHitung(o.batasBayar); ikon($('#isi'));
}
async function muat() {
  let o = await Api.pesananById(oid);
  if (!o) return $('#isi').replaceChildren(T.klon('t-tak-bisa', { judul: 'Pesanan tidak ditemukan', isi: 'Pesanan ini tidak ada di akunmu.' }));
  if (o.status === 'menunggu_verifikasi') return $('#isi').replaceChildren(T.klon('t-menunggu', o));
  if (o.status !== 'menunggu_bayar') return $('#isi').replaceChildren(T.klon('t-tak-bisa', { judul: 'Pesanan tidak perlu dibayar', isi: `Status pesanan #${o.id} saat ini: ${STATUS[o.status][0]}.` }));
  if (!o.midtrans) o = await Api.buatTagihan(oid, o.metode || undefined);   // tagihan dibuat saat halaman dibuka pertama kali
  pasangHalaman(o);
  clearInterval(poll); poll = setInterval(() => { if (!document.hidden && pesanan) Api.cekTagihan(oid).then(x => { pesanan = x; tampilkanTagihan(x); }).catch(() => {}); }, 20000);
}
async function gantiMetode() {
  const daftar = await Api.metodeBayar(), m = Modal.dari('t-ganti-metode', {}, 'max-w-md'), pilih = pesanan.midtrans ? pesanan.midtrans.data.metode : '';
  $('#daftar-metode', m).replaceChildren(...daftar.map(x => { const e = T.satu('t-opsi-metode', { ...x, ikon: IKON_METODE[x.kode] || 'card' }); $('input', e).checked = x.kode === pilih; return e; }));
  ikon(m);
  $('form', m).onsubmit = async e => { e.preventDefault(); const v = $('input:checked', m); if (!v) return $('#gm-err', m).textContent = 'Pilih salah satu metode.';
    try { pasangHalaman(await Api.buatTagihan(oid, v.value)); m.tutup(); Toast.ok('Metode pembayaran diganti.'); } catch (x) { $('#gm-err', m).textContent = x.message; } };
}
document.addEventListener('click', async e => {
  const a = e.target.closest('[data-aksi]'); if (!a) return;
  try { switch (a.dataset.aksi) {
    case 'salin': Toast.ok(await K.salin(a.dataset.teks) ? 'Disalin.' : 'Tidak bisa menyalin, salin manual.'); break;
    case 'salin-total': Toast.ok(await K.salin(String(pesanan.total)) ? 'Nominal disalin.' : 'Tidak bisa menyalin, salin manual.'); break;
    case 'cek': { a.disabled = true; try { pesanan = await Api.cekTagihan(oid); tampilkanTagihan(pesanan); const s = pesanan.midtrans && pesanan.midtrans.status;
        Toast.ok(['settlement', 'capture'].includes(s) ? 'Pembayaran terdeteksi. Unggah bukti agar admin bisa memeriksa.' : 'Belum ada pembayaran yang terdeteksi.'); } finally { a.disabled = false; } break; }
    case 'ganti': await gantiMetode(); break;
  } } catch (er) { Toast.err(er.message); }
});
document.addEventListener('change', async e => {
  if (e.target.id !== 'bk-file') return;
  const f = e.target.files[0], er = await K.cekGambar(f), p = $('#bk-prev'); $('#bk-err').textContent = er || ''; $('#bk-kirim').disabled = true; bukti = null;
  if (er) { p.classList.add('hidden'); e.target.value = ''; return; }
  try { bukti = await K.kecilkan(f); p.src = bukti; p.classList.remove('hidden'); $('#bk-kirim').disabled = false; } catch (x) { $('#bk-err').textContent = x.message; }
});
document.addEventListener('click', async e => {
  const b = e.target.closest('#bk-kirim'); if (!b || !bukti) return; b.disabled = true; b.textContent = 'Mengirim...';
  try { await Api.kirimBukti(oid, bukti); clearInterval(timer); clearInterval(poll); Toast.ok('Bukti terkirim. Menunggu verifikasi admin.'); muat(); }
  catch (x) { $('#bk-err').textContent = x.message; b.disabled = false; b.textContent = 'Kirim bukti pembayaran'; }
});
document.addEventListener('sesi-berubah', e => { if (!e.detail) location.replace('/masuk?habis=1'); });
(async () => {
  const u = await Sesi.wajib('customer'); if (!u) return;
  try { await muat(); } catch (er) { $('#isi').replaceChildren(T.klon('t-tak-bisa', { judul: 'Gagal memuat pembayaran', isi: er.message })); }
})();
