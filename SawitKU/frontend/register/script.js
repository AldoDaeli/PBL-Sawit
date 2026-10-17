'use strict';
const cek = {
  username: v => K.username(v) ? '' : 'Username 4–20 karakter: huruf, angka, garis bawah.',
  email: v => K.email(v) ? '' : 'Format email tidak valid.',
  password: v => K.password(v) ? '' : 'Minimal 8 karakter, kombinasi huruf dan angka.',
  konfirmasi: v => v === $('#password').value && v ? '' : 'Password tidak sama.',
};
const warna = ['#f43f5e', '#f59e0b', '#84cc16', '#38995e'];
function tampil(k) { const e = cek[k]($('#' + k).value.trim ? $('#' + k).value : ''); $('#e-' + k).textContent = e; $('#' + k).closest('.campur').classList.toggle('salah', !!e); return !e; }
async function init() {
  $('#i-user').innerHTML = I('user'); $('#i-mail').innerHTML = I('mail'); $('#i-lock').innerHTML = I('lock'); $('#i-lock2').innerHTML = I('lock'); $('#lihat').innerHTML = I('eye');
  const u = await Sesi.segarkan(); if (u) location.replace(Sesi.beranda(u.peran));
}
$('#lihat').onclick = () => { const f = $('#password'); f.type = f.type === 'password' ? 'text' : 'password'; };
['username', 'email', 'password', 'konfirmasi'].forEach(k => $('#' + k).addEventListener('blur', () => tampil(k)));
$('#password').addEventListener('input', e => { const s = K.skorPassword(e.target.value); $$('.kuat').forEach((b, i) => b.style.background = i < s ? warna[s - 1] : ''); });
/* ---- Langkah 1: kirim data -> server mengirim kode OTP ke email. Akun baru dibuat setelah kode benar (langkah 2). ---- */
let emailOtp = '', hitung = null;
function mulaiHitung(detik) {
  const b = $('#ulang'); clearInterval(hitung); b.disabled = true;
  const tick = () => { if (detik <= 0) { clearInterval(hitung); b.disabled = false; b.textContent = 'Kirim ulang kode'; } else b.textContent = `Kirim ulang (${detik--}s)`; };
  tick(); hitung = setInterval(tick, 1000);
}
function tampilOtp(d) {
  emailOtp = d.email; $('#otp-email').textContent = d.email; $('#otp-menit').textContent = d.berlaku;
  $('#form').classList.add('hidden'); $('#form-otp').classList.remove('hidden');
  $('#judul').textContent = 'Verifikasi email'; $('#sub').textContent = 'Satu langkah lagi untuk mengaktifkan akunmu.';
  $('#kode').value = ''; $('#err-otp').textContent = ''; $('#kode').focus(); mulaiHitung(d.jeda);
}
$('#form').onsubmit = async e => {
  e.preventDefault(); const err = $('#err'), btn = $('#btn'); err.textContent = '';
  if (!['username', 'email', 'password', 'konfirmasi'].map(tampil).every(Boolean)) return;
  btn.disabled = true; btn.textContent = 'Mengirim kode...';
  try { tampilOtp(await Api.daftar({ username: $('#username').value.trim(), email: $('#email').value.trim(), password: $('#password').value })); }
  catch (er) { err.textContent = er.message; }
  btn.disabled = false; btn.textContent = 'Daftar';
};

/* ---- Langkah 2: verifikasi kode ---- */
$('#i-otp').innerHTML = I('shield');
$('#kode').addEventListener('input', e => { e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6); });
$('#form-otp').onsubmit = async e => {
  e.preventDefault(); const err = $('#err-otp'), btn = $('#btn-otp'), kode = $('#kode').value; err.textContent = '';
  if (!/^\d{6}$/.test(kode)) return err.textContent = 'Masukkan 6 angka kode OTP.';
  btn.disabled = true; btn.textContent = 'Memverifikasi...';
  try { await Api.verifikasiOtp(emailOtp, kode); clearInterval(hitung); Toast.ok('Email terverifikasi. Akun berhasil dibuat. Silakan masuk.'); setTimeout(() => location.href = '/masuk', 1000); return; }
  catch (er) { err.textContent = er.message; $('#kode').value = ''; $('#kode').focus(); }
  btn.disabled = false; btn.textContent = 'Verifikasi & Buat Akun';
};
$('#ulang').onclick = async () => {
  const err = $('#err-otp'); err.textContent = ''; $('#ulang').disabled = true;
  try { const d = await Api.kirimUlangOtp(emailOtp); Toast.ok('Kode baru dikirim ke ' + d.email); $('#kode').value = ''; mulaiHitung(d.jeda); }
  catch (er) { err.textContent = er.message; $('#ulang').disabled = false; $('#ulang').textContent = 'Kirim ulang kode'; }
};
$('#ubah').onclick = () => {
  clearInterval(hitung); $('#form-otp').classList.add('hidden'); $('#form').classList.remove('hidden');
  $('#judul').textContent = 'Buat akun baru'; $('#sub').textContent = 'Gratis, cukup satu menit.';
};
init();
