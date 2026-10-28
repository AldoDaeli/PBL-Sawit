import { loadImage, toCanvas, removeBackground } from "./image.js";
import { $, $$, api, countTo, dropzone, sendJson, showError, stamp, toast } from "./ui.js";

const LOGO_RATIO = 0.28; // diameter lingkaran putih di tengah QR, relatif terhadap lebar QR
const MAX_IMAGE_MB = 8;
const CAN_COPY_IMAGE = Boolean(window.ClipboardItem && navigator.clipboard?.write && window.isSecureContext);

const state = {
  value: "",          // isi yang dikodekan ke QR
  ours: false,        // isi QR adalah link pendek milik kita (pindaian dihitung)
  withLogo: false,
  logoSource: null,   // gambar logo asli (sudah diperkecil)
  logo: null,         // logo hasil proses (background terhapus)
  pic: null,          // file foto untuk "QR dari foto"
  links: [],
  openCode: null,
};

const composer = $("#composer");
const preview = $("#preview");
const logoField = $("#logo-field");
const picField = $("#pic-field");

const fmt = (n) => Number(n).toLocaleString("id-ID");
const dateId = (iso) => new Date(iso).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
const stripScheme = (url) => url.replace(/^https?:\/\//, "");
const isExpired = (link) => link.expiresAt && Date.now() > Date.parse(link.expiresAt);
const useLogo = () => Boolean(state.logo && state.withLogo);
const show = (view) => { preview.dataset.view = view; };

/* ---------- Tema ---------- */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("theme", theme); } catch { /* penyimpanan dinonaktifkan */ }
}
let savedTheme = null;
try { savedTheme = localStorage.getItem("theme"); } catch { /* abaikan */ }
applyTheme(savedTheme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
$("#theme").addEventListener("click", () =>
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));

/* ---------- Mode form ---------- */
const currentMode = () =>
  $('input[name="tab"]:checked').value === "short" ? "short" : $('input[name="mode"]:checked').value;

function syncMode() {
  composer.dataset.mode = currentMode();
  showError();
}

function selectMode(mode) {
  $(`input[name="tab"][value="${mode === "short" ? "short" : "qr"}"]`).checked = true;
  if (mode !== "short") $(`input[name="mode"][value="${mode}"]`).checked = true;
  syncMode();
}

$$('input[name="tab"], input[name="mode"]').forEach((r) => r.addEventListener("change", syncMode));
$$("a[data-mode]").forEach((a) => a.addEventListener("click", () => selectMode(a.dataset.mode)));

/* ---------- Upload gambar (logo & foto) ---------- */
function isValidImage(file) {
  if (!file?.type.startsWith("image/")) { toast("File harus berupa gambar"); return false; }
  if (file.size > MAX_IMAGE_MB * 1024 * 1024) { toast(`Ukuran gambar maksimal ${MAX_IMAGE_MB} MB`); return false; }
  return true;
}

async function setLogo(file) {
  if (!isValidImage(file)) return;
  const url = URL.createObjectURL(file);
  try {
    state.logoSource = toCanvas(await loadImage(url));
  } catch (err) {
    return toast(err.message);
  } finally {
    URL.revokeObjectURL(url);
  }
  $("#logo-name").textContent = file.name || "Gambar dari clipboard";
  logoField.dataset.state = "filled";
  processLogo();
}

function processLogo() {
  if (!state.logoSource) return;
  const auto = $("#bg-auto").checked;
  let status = "off";
  state.logo = state.logoSource;
  if (auto) ({ canvas: state.logo, status } = removeBackground(state.logoSource, Number($("#bg-tol").value)));
  $("#logo-prev").src = state.logo.toDataURL("image/png");
  $("#logo-note").textContent = $("#logo-note").dataset[status];
  $("#bg-tol").disabled = !auto;
  refreshLogoQr();
}

function clearLogo() {
  state.logoSource = state.logo = null;
  resetLogoInput();
  logoField.dataset.state = "idle";
  refreshLogoQr();
}

function setPic(file) {
  if (!isValidImage(file)) return;
  state.pic = file;
  $("#pic-prev").src = URL.createObjectURL(file);
  $("#pic-name").textContent = file.name || "Foto";
  picField.dataset.state = "filled";
}

function clearPic() {
  state.pic = null;
  resetPicInput();
  picField.dataset.state = "idle";
}

const refreshLogoQr = () => { if (state.value && state.withLogo) renderQr(); };
const resetLogoInput = dropzone($("#drop"), $("#logo-file"), setLogo);
const resetPicInput = dropzone($("#pic-drop"), $("#pic-file"), setPic);

$("#logo-remove").addEventListener("click", (e) => { e.stopPropagation(); clearLogo(); });
$("#pic-remove").addEventListener("click", (e) => { e.stopPropagation(); clearPic(); });
$("#bg-auto").addEventListener("input", processLogo);

let toleranceFrame;
$("#bg-tol").addEventListener("input", () => {
  cancelAnimationFrame(toleranceFrame);
  toleranceFrame = requestAnimationFrame(processLogo);
});

// Cegah browser membuka file bila terlepas di luar area drop
["dragover", "drop"].forEach((type) => window.addEventListener(type, (e) => e.preventDefault()));
document.addEventListener("paste", (e) => {
  const file = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith("image/"));
  if (!file) return;
  const mode = currentMode();
  if (mode === "logo") setLogo(file);
  else if (mode === "pic") setPic(file);
});

/* ---------- Render QR ---------- */
let renderToken = 0;
let pngUrl = null;
let pngBlob = null;

const qrUrl = (format) => `/api/qr?${new URLSearchParams({
  text: state.ours ? `${state.value}?src=qr` : state.value,
  ec: useLogo() ? "H" : "M", // koreksi error tertinggi agar QR tetap terbaca meski tertutup logo
  format,
})}`;

// Logo dibuat muat di dalam lingkaran putih di tengah QR
function logoBox(side) {
  const diameter = side * LOGO_RATIO;
  const k = (diameter * 0.98) / Math.hypot(state.logo.width, state.logo.height);
  return { d: diameter, w: state.logo.width * k, h: state.logo.height * k };
}

function fillLink() {
  const link = $("#short-link");
  link.textContent = stripScheme(state.value);
  link.href = state.value;
}

async function renderQr() {
  const token = ++renderToken;
  if (state.ours) fillLink();
  show(state.ours ? "qr-link" : "qr");
  try {
    const base = await loadImage(qrUrl("png"));
    if (token !== renderToken) return;
    const canvas = document.createElement("canvas");
    canvas.width = base.naturalWidth;
    canvas.height = base.naturalHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(base, 0, 0);
    if (useLogo()) {
      const { d, w, h } = logoBox(canvas.width);
      const c = canvas.width / 2;
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(c, c, d / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(state.logo, c - w / 2, c - h / 2, w, h);
    }
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (token !== renderToken) return;
    if (pngUrl) URL.revokeObjectURL(pngUrl);
    pngUrl = URL.createObjectURL(blob);
    pngBlob = blob;
    $("#qr").src = pngUrl;
    $("#dl-png").href = pngUrl;
  } catch {
    if (token === renderToken) showError("Gagal membuat QR code.");
  }
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

$("#dl-svg").addEventListener("click", async (e) => {
  e.preventDefault();
  try {
    let svg = await (await fetch(qrUrl("svg"))).text();
    if (useLogo()) {
      const n = Number(svg.match(/viewBox="0 0 (\d+)/)[1]);
      const c = n / 2;
      const { d, w, h } = logoBox(n);
      svg = svg.replace("</svg>",
        `<g shape-rendering="geometricPrecision"><circle cx="${c}" cy="${c}" r="${d / 2}" fill="#fff"/>` +
        `<image href="${state.logo.toDataURL("image/png")}" x="${c - w / 2}" y="${c - h / 2}" width="${w}" height="${h}" preserveAspectRatio="xMidYMid meet"/></g></svg>`);
    }
    saveBlob(new Blob([svg], { type: "image/svg+xml" }), "qr-code.svg");
  } catch {
    toast("Gagal mengunduh SVG");
  }
});

async function copyText(text, okMessage, failMessage) {
  try { await navigator.clipboard.writeText(text); toast(okMessage); }
  catch { toast(failMessage); }
}

$("#copy").addEventListener("click", () => copyText(state.value, "Link disalin", "Gagal menyalin link"));
$("#copy-img").hidden = !CAN_COPY_IMAGE;
$("#copy-img").addEventListener("click", async () => {
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": pngBlob })]);
    toast("Gambar QR disalin");
  } catch {
    toast("Browser ini tidak bisa menyalin gambar");
  }
});

/* ---------- Submit: satu handler per mode ---------- */
const showQrFor = (value, { ours = false, withLogo = false } = {}) => {
  Object.assign(state, { value, ours, withLogo });
  return renderQr();
};

const submitHandlers = {
  async short() {
    const url = $("#url").value.trim();
    if (!url) throw new Error("Isi link panjang terlebih dahulu.");
    const data = await sendJson("/api/shorten", {
      url,
      alias: $("#alias").value.trim(),
      expiresInDays: $("#expires").value,
    });
    Object.assign(state, { value: data.shortUrl, ours: true, withLogo: false });
    fillLink();
    show("link");
    toast("Link dibuat");
    loadLinks();
  },

  qr() {
    const text = $("#text").value.trim();
    if (!text) throw new Error("Isi teks atau link terlebih dahulu.");
    return showQrFor(text, { ours: state.links.some((l) => l.shortUrl === text) });
  },

  logo() {
    const text = $("#text").value.trim();
    if (!text) throw new Error("Isi teks atau link terlebih dahulu.");
    if (!state.logo) throw new Error("Seret foto logo ke kotak di atas terlebih dahulu.");
    return showQrFor(text, { ours: state.links.some((l) => l.shortUrl === text), withLogo: true });
  },

  async pic() {
    if (!state.pic) throw new Error("Pilih foto terlebih dahulu.");
    const body = new FormData();
    body.append("photo", state.pic);
    const data = await api("/api/photo", { method: "POST", body });
    return showQrFor(data.shortUrl);
  },

  async wifi() {
    const ssid = $("#ssid").value.trim();
    if (!ssid) throw new Error("Isi nama Wi-Fi terlebih dahulu.");
    const data = await sendJson("/api/wifi", { ssid, password: $("#wpass").value });
    return showQrFor(data.shortUrl);
  },
};

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError();
  $("#submit").disabled = true;
  try {
    await submitHandlers[currentMode()]();
  } catch (err) {
    showError(err.message);
  } finally {
    $("#submit").disabled = false;
  }
});

/* ---------- Daftar link ---------- */
function buildRow(link) {
  const row = stamp("#tpl-row", { url: link.url, clicks: fmt(link.clicks) });
  row.dataset.code = link.code;
  const anchor = $('[data-f="short"]', row);
  anchor.href = link.shortUrl;
  anchor.textContent = stripScheme(link.shortUrl);
  $('[data-f="url"]', row).title = link.url;
  if (link.expiresAt) {
    const dead = isExpired(link);
    const badge = $('[data-f="badge"]', row);
    badge.hidden = false;
    badge.textContent = dead ? "kedaluwarsa" : `s.d. ${dateId(link.expiresAt)}`;
    badge.classList.toggle("off", dead);
  }
  return row;
}

function renderRows() {
  const query = $("#search").value.trim().toLowerCase();
  const list = state.links.filter((l) => !query || l.code.toLowerCase().includes(query) || l.url.toLowerCase().includes(query));
  const empty = $("#no-links");
  empty.hidden = list.length > 0;
  empty.textContent = empty.dataset[state.links.length ? "nomatch" : "none"];
  $("#rows").replaceChildren(...list.map(buildRow));
}

async function loadLinks() {
  state.links = await api("/api/links");
  const dead = state.links.filter(isExpired).length;
  countTo($("#n-all"), state.links.length);
  countTo($("#n-live"), state.links.length - dead);
  countTo($("#n-dead"), dead);
  renderRows();
}

async function removeLink(link) {
  if (!confirm(`Hapus link ${link.code}? QR code yang sudah dicetak akan berhenti bekerja.`)) return;
  await api(`/api/links/${encodeURIComponent(link.code)}`, { method: "DELETE" });
  toast("Link dihapus");
  loadLinks();
}

const rowActions = {
  qr(link) {
    showQrFor(link.shortUrl, { ours: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  },
  detail: (link) => openDetail(link),
  delete: (link) => removeLink(link),
};

$("#rows").addEventListener("click", (e) => {
  const button = e.target.closest("button[data-act]");
  const link = button && state.links.find((l) => l.code === button.closest("tr").dataset.code);
  if (link) rowActions[button.dataset.act](link);
});
$("#search").addEventListener("input", renderRows);

/* ---------- Detail & statistik ---------- */
function renderChart(days) {
  const max = Math.max(1, ...days.map((d) => d.link + d.qr));
  $("#d-chart").replaceChildren(...days.map((d, i) => {
    const showLabel = i % 3 === 0 || i === days.length - 1;
    const bar = stamp("#tpl-bar", { label: showLabel ? `${d.d.slice(8)}/${d.d.slice(5, 7)}` : "" });
    bar.style.setProperty("--link", `${(d.link / max) * 100}%`);
    bar.style.setProperty("--qr", `${(d.qr / max) * 100}%`);
    bar.style.setProperty("--i", i);
    bar.title = `${d.d}: ${d.link} klik, ${d.qr} pindaian QR`;
    return bar;
  }));
}

function renderList(ul, entries) {
  const items = entries.length ? entries : [["Belum ada data", ""]];
  ul.replaceChildren(...items.map(([name, count]) => stamp("#tpl-li", { name, count: count === "" ? "" : fmt(count) })));
}

async function openDetail(link) {
  state.openCode = link.code;
  $("#d-title").textContent = stripScheme(link.shortUrl);
  $("#d-meta").textContent = `Dibuat ${dateId(link.createdAt)} · ${fmt(link.clicks)} klik, ${fmt(link.qr)} dari QR`;
  $("#d-url").value = link.url;
  $("#d-chart").replaceChildren();
  $("#detail").showModal();
  const stats = await api(`/api/links/${encodeURIComponent(link.code)}/stats`);
  renderChart(stats.days);
  renderList($("#d-dev"), Object.entries(stats.devices).sort((a, b) => b[1] - a[1]));
  renderList($("#d-ref"), stats.refs);
}

$("#d-save").addEventListener("click", async () => {
  try {
    await sendJson(`/api/links/${encodeURIComponent(state.openCode)}`, { url: $("#d-url").value }, "PATCH");
    toast("Tujuan diperbarui");
    loadLinks();
  } catch (err) {
    toast(err.message);
  }
});

/* ---------- Mulai ---------- */
$("#year").textContent = new Date().getFullYear();
syncMode();
loadLinks();
