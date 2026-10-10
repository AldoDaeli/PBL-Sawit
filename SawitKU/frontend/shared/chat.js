'use strict';
/* Chat pelanggan <-> admin. Komponen bersama: landing (#kontak), dashboard pelanggan, dashboard admin.
   KEAMANAN : isi pesan hanya masuk lewat textContent, tidak pernah innerHTML, jadi tidak bisa menjadi XSS.
   EFISIEN  : polling hanya meminta pesan yang lebih baru (?sejak=<id>), melambat saat sepi, berhenti saat tab
              tersembunyi atau komponen disembunyikan/dilepas; daftar pesan di-render bertahap (bukan ulang semua). */
const Chat = (() => {
  const POLL_MIN = 4000, POLL_MAKS = 15000;
  const el = (tag, kls, teks) => { const e = document.createElement(tag); if (kls) e.className = kls; if (teks != null) e.textContent = teks; return e; };
  const jam = ms => new Date(ms).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  const hari = ms => new Date(ms).toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const kunciHari = ms => new Date(ms).toDateString();

  /* pasang(root, { saya: 'customer'|'admin', muat(params) -> {pesan, adaLagi, dibacaSampai}, kirim(isi) -> pesan,
                    diMuat?(data), kosong?: teks }) -> { hentikan() } */
  function pasang(root, opsi) {
    const saya = opsi.saya;
    let daftar = [], ids = new Set(), tanda = new Map(), hariAkhir = '', terakhir = 0, adaLagi = false, dibacaSampai = 0;
    let mati = false, timer = null, jeda = POLL_MIN, sepi = 0, sibuk = false, memuatLama = false;

    root.className = (root.className + ' flex flex-col min-h-0').trim();
    root.innerHTML = '<div data-log class="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-1.5 bg-slate-50" role="log" aria-live="polite" aria-label="Percakapan"></div>' +
      '<p data-err class="px-4 pt-2 text-sm text-rose-600 min-h-[1.25rem] bg-white" role="alert"></p>' +
      '<form data-form class="p-3 pt-1 flex gap-2 items-end bg-white" novalidate><textarea data-isi rows="1" maxlength="1000" placeholder="Tulis pesan..." aria-label="Tulis pesan" class="flex-1 resize-none max-h-32 rounded-xl border border-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-400"></textarea>' +
      '<button data-kirim class="h-10 px-5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white font-semibold transition disabled:opacity-60">Kirim</button></form>';
    const log = root.querySelector('[data-log]'), err = root.querySelector('[data-err]'), form = root.querySelector('[data-form]'),
          ta = root.querySelector('[data-isi]'), btn = root.querySelector('[data-kirim]');

    const perbaruiTanda = () => tanda.forEach((c, id) => { c.textContent = id <= dibacaSampai ? '✓✓' : '✓'; c.title = id <= dibacaSampai ? 'Dibaca' : 'Terkirim'; });
    const gelembung = m => {
      const milik = m.dari === saya, baris = el('div', 'flex ' + (milik ? 'justify-end' : 'justify-start')), b = el('div',
        'max-w-[82%] rounded-2xl px-3.5 py-2 text-sm shadow-sm ' + (milik ? 'bg-brand-600 text-white rounded-br-md' : 'bg-white text-slate-800 border border-slate-100 rounded-bl-md'));
      const p = el('p', '', m.isi); p.style.whiteSpace = 'pre-wrap'; p.style.overflowWrap = 'anywhere';   // isi pesan: textContent saja
      const meta = el('p', 'mt-0.5 text-[10px] text-right ' + (milik ? 'text-brand-100' : 'text-slate-400'), jam(m.dibuat));
      if (milik) { const c = el('span', 'ml-1'); meta.append(c); tanda.set(m.id, c); }
      b.append(p, meta); baris.append(b); return baris;
    };
    const pemisah = ms => { const d = el('div', 'flex justify-center py-1'); d.append(el('span', 'text-[11px] text-slate-500 bg-white border border-slate-100 rounded-full px-3 py-0.5', hari(ms))); return d; };
    const tombolLama = () => { const b = el('button', 'block mx-auto text-xs font-semibold text-brand-700 hover:underline py-1', 'Muat pesan sebelumnya'); b.type = 'button'; b.dataset.lama = '1'; return b; };
    const kosongNode = () => el('p', 'text-center text-sm text-slate-500 py-10', opsi.kosong || 'Belum ada pesan. Tulis pesanmu di bawah.');

    function renderPenuh() {
      log.textContent = ''; tanda.clear(); hariAkhir = '';
      if (adaLagi) log.append(tombolLama());
      if (!daftar.length) log.append(kosongNode());
      daftar.forEach(m => { const h = kunciHari(m.dibuat); if (h !== hariAkhir) { log.append(pemisah(m.dibuat)); hariAkhir = h; } log.append(gelembung(m)); });
      perbaruiTanda();
    }
    function tambah(pesan) {
      const baru = pesan.filter(m => !ids.has(m.id)); if (!baru.length) return false;
      const bawah = log.scrollHeight - log.scrollTop - log.clientHeight < 120, sendiri = baru.some(m => m.dari === saya);
      if (!daftar.length) log.textContent = '';      // hapus teks "belum ada pesan"
      baru.forEach(m => { ids.add(m.id); daftar.push(m); terakhir = Math.max(terakhir, m.id);
        const h = kunciHari(m.dibuat); if (h !== hariAkhir) { log.append(pemisah(m.dibuat)); hariAkhir = h; } log.append(gelembung(m)); });
      perbaruiTanda(); if (bawah || sendiri) log.scrollTop = log.scrollHeight;
      return true;
    }
    const tangani = d => { dibacaSampai = Math.max(dibacaSampai, d.dibacaSampai || 0); perbaruiTanda(); };

    async function muatAwal() {
      try {
        const d = await opsi.muat({});
        daftar = d.pesan.slice(); ids = new Set(daftar.map(m => m.id)); terakhir = daftar.reduce((a, m) => Math.max(a, m.id), 0); adaLagi = d.adaLagi; dibacaSampai = d.dibacaSampai || 0;
        renderPenuh(); log.scrollTop = log.scrollHeight; if (opsi.diMuat) opsi.diMuat(d);
      } catch (x) { err.textContent = x.message; }
      jadwal();
    }
    async function muatLama() {
      if (memuatLama || !daftar.length) return; memuatLama = true;
      try {
        const d = await opsi.muat({ sebelum: daftar[0].id }), tinggi = log.scrollHeight;
        const lama = d.pesan.filter(m => !ids.has(m.id)); lama.forEach(m => ids.add(m.id)); daftar = lama.concat(daftar); adaLagi = d.adaLagi;
        renderPenuh(); log.scrollTop = log.scrollHeight - tinggi;          // posisi baca tidak melompat
      } catch (x) { err.textContent = x.message; }
      memuatLama = false;
    }
    log.addEventListener('click', e => { if (e.target.closest('[data-lama]')) muatLama(); });

    function jadwal() { clearTimeout(timer); if (!mati) timer = setTimeout(tick, document.hidden || root.offsetParent === null ? 5000 : jeda); }
    async function tick() {
      if (mati) return; if (!root.isConnected) return hentikan();
      if (!document.hidden && root.offsetParent !== null && !sibuk) {        // hanya bertanya ke server bila terlihat
        try {
          const d = await opsi.muat({ sejak: terakhir });
          if (tambah(d.pesan)) { jeda = POLL_MIN; sepi = 0; } else if (++sepi > 10) jeda = Math.min(Math.round(jeda * 1.5), POLL_MAKS);
          tangani(d); if (err.dataset.poll) { err.textContent = ''; delete err.dataset.poll; }
        } catch (x) {
          if (x.status === 401 || x.status === 403) { err.textContent = 'Sesi berakhir. Muat ulang halaman lalu masuk lagi.'; return hentikan(); }
          err.textContent = 'Koneksi terputus, mencoba lagi...'; err.dataset.poll = '1'; jeda = Math.min(jeda * 2, 30000);
        }
      }
      jadwal();
    }
    const saatTampil = () => { if (!document.hidden && !mati) { jeda = POLL_MIN; clearTimeout(timer); tick(); } };
    document.addEventListener('visibilitychange', saatTampil);
    function hentikan() { mati = true; clearTimeout(timer); document.removeEventListener('visibilitychange', saatTampil); }

    const ukur = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 128) + 'px'; };
    ta.addEventListener('input', ukur);
    ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
    form.addEventListener('submit', async e => {
      e.preventDefault(); const isi = ta.value.trim(); if (!isi || sibuk) return;
      sibuk = true; btn.disabled = true; err.textContent = ''; delete err.dataset.poll;
      try { const m = await opsi.kirim(isi); ta.value = ''; ukur(); tambah([m]); jeda = POLL_MIN; sepi = 0; }
      catch (x) { err.textContent = x.message; }
      sibuk = false; btn.disabled = false; ta.focus();
    });
    muatAwal();
    return { hentikan, fokus: () => ta.focus() };
  }

  /* Lencana jumlah pesan belum dibaca pada item menu (.nav-item[data-sec=...]). Polling jarang & berhenti saat tab tersembunyi. */
  function lencana(sec, ambil, ms = 20000) {
    const a = document.querySelector(`.nav-item[data-sec="${sec}"]`); let berhenti = false, t = null;
    const tampil = n => { let p = a.querySelector('.pin'); if (!n) return p && p.remove(); if (!p) { p = el('span', 'pin'); a.append(p); } p.textContent = n > 99 ? '99+' : n; };
    const putar = async () => {
      clearTimeout(t); if (berhenti) return;
      if (!document.hidden) { try { tampil((await ambil()).belum); } catch (x) { if (x.status === 401 || x.status === 403) return; } }
      t = setTimeout(putar, document.hidden ? 60000 : ms);
    };
    document.addEventListener('visibilitychange', () => { if (!document.hidden) putar(); });
    putar();
    return { segarkan: putar, hentikan() { berhenti = true; clearTimeout(t); } };
  }

  return { pasang, lencana, el, jam };
})();
