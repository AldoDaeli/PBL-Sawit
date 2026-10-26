'use strict';
let email = '', jeda = 0, timer = null;
function hitungMundur(d) {
  clearInterval(timer); jeda = d; const b = $('#ulang');
  const t = () => { b.disabled = jeda > 0; b.textContent = jeda > 0 ? `Kirim ulang kode (${jeda} dtk)` : 'Kirim ulang kode'; };
  t(); timer = setInterval(() => { jeda--; t(); if (jeda <= 0) clearInterval(timer); }, 1000);
}
async function kirim(btn, err) {
  err.textContent = ''; btn.disabled = true;
  try { const d = await Api.lupaKirim(email); $('#f1').classList.add('hidden'); $('#f2').classList.remove('hidden'); hitungMundur(d.jeda);
    $('#sub').textContent = `Jika ${email} terdaftar, kode 6 angka sudah dikirim (berlaku ${d.berlaku} menit). Cek juga folder spam.`; $('#kode').focus(); }
  catch (x) { err.textContent = x.message; }
  btn.disabled = false;
}
$('#f1').onsubmit = e => { e.preventDefault(); email = $('#email').value.trim().toLowerCase(); if (!K.email(email)) return $('#err1').textContent = 'Format email tidak valid.'; kirim($('#b1'), $('#err1')); };
$('#ulang').onclick = () => kirim($('#ulang'), $('#err2'));
$('#f2').onsubmit = async e => {
  e.preventDefault(); const err = $('#err2'), b = $('#b2'), kode = $('#kode').value.replace(/\s/g, ''), pw = $('#pw').value; err.textContent = '';
  if (!/^\d{6}$/.test(kode)) return err.textContent = 'Kode OTP terdiri dari 6 angka.';
  if (!K.password(pw)) return err.textContent = 'Password 8–64 karakter, kombinasi huruf dan angka.';
  if (pw !== $('#pw2').value) return err.textContent = 'Konfirmasi password tidak sama.';
  b.disabled = true; b.textContent = 'Memproses...';
  try { await Api.lupaReset(email, kode, pw); b.textContent = 'Berhasil'; Toast.ok('Password diubah. Silakan masuk.'); setTimeout(() => location.href = ROOT + 'masuk', 1200); }
  catch (x) { err.textContent = x.message; b.disabled = false; b.textContent = 'Simpan Password Baru'; }
};
