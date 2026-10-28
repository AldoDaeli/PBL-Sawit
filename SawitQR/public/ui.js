// Helper UI kecil yang dipakai berulang.
export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

let toastTimer;
export function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
}

export function showError(message = "") {
  const el = $("#error");
  el.textContent = message;
  el.hidden = !message;
}

// Salin <template> dari HTML lalu isi elemen [data-f="nama"] dengan teks.
export function stamp(templateSelector, data = {}) {
  const node = $(templateSelector).content.firstElementChild.cloneNode(true);
  for (const [key, value] of Object.entries(data)) {
    const target = $(`[data-f="${key}"]`, node);
    if (target) target.textContent = value;
  }
  return node;
}

// Area seret-lepas + klik untuk memilih file. Mengembalikan fungsi untuk mengosongkan input.
export function dropzone(zone, input, onFile) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", () => onFile(input.files[0]));
  ["dragenter", "dragover"].forEach((type) =>
    zone.addEventListener(type, (e) => { e.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((type) =>
    zone.addEventListener(type, (e) => { e.preventDefault(); zone.classList.remove("over"); }));
  zone.addEventListener("drop", (e) => onFile(e.dataTransfer.files[0]));
  return () => { input.value = ""; };
}

// Animasi angka naik/turun dengan halus.
export function countTo(el, target, duration = 450) {
  const from = Number(el.textContent) || 0;
  if (from === target) return;
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    el.textContent = Math.round(from + (target - from) * (1 - (1 - t) ** 3));
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// Panggilan API: melempar Error berisi pesan dari server bila gagal.
export async function api(path, options) {
  const res = await fetch(path, options);
  const data = res.status === 204 ? null : await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error || "Terjadi kesalahan.");
  return data;
}

export const sendJson = (path, body, method = "POST") =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
