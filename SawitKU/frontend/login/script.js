'use strict';
const p = new URLSearchParams(location.search), tujuan = Object.hasOwn(NEXT, p.get('next')) ? NEXT[p.get('next')] : null; // hanya tujuan terdaftar (cegah open redirect)
async function init() {
  $('#logo').innerHTML = I('leaf'); $('#i-user').innerHTML = I('user'); $('#i-lock').innerHTML = I('lock'); $('#lihat').innerHTML = I('eye');
  const u = await Sesi.segarkan(); if (u) return location.replace(Sesi.beranda(u.peran));   // token dicek ke server
  if (p.get('habis')) { const i = $('#info'); i.textContent = 'Sesi berakhir karena tidak aktif. Silakan masuk lagi.'; i.classList.remove('hidden'); }
}
$('#lihat').onclick = () => { const f = $('#password'); f.type = f.type === 'password' ? 'text' : 'password'; };
$('#form').onsubmit = async e => {
  e.preventDefault(); const err = $('#err'), btn = $('#btn'), u = $('#username').value.trim(), pw = $('#password').value; err.textContent = '';
  if (!u || !pw) return err.textContent = 'Username dan password wajib diisi.';
  btn.disabled = true; btn.textContent = 'Memproses...';
  try { const x = await Api.masuk(u, pw); btn.textContent = 'Berhasil'; const t = x.peran === 'admin' ? NEXT.admin : (tujuan ?? NEXT.customer);
    setTimeout(() => location.href = ROOT + t, 350); }
  catch (er) { err.textContent = er.message; btn.disabled = false; btn.textContent = 'Masuk'; $('#password').value = ''; $$('.campur').forEach(c => { c.classList.add('salah'); setTimeout(() => c.classList.remove('salah'), 1200); }); }
};
init();
