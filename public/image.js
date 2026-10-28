// Pemrosesan gambar: muat, perkecil, dan hapus background logo.
export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Gambar tidak bisa dibaca."));
    img.src = src;
  });
}

export function toCanvas(img, maxSide = 600) {
  const nw = img.naturalWidth || 512, nh = img.naturalHeight || 512;
  const k = Math.min(1, maxSide / Math.max(nw, nh));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(nw * k));
  c.height = Math.max(1, Math.round(nh * k));
  c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
  return c;
}

// Hapus background: warna latar diambil dari tepi gambar, lalu area yang
// "tersambung" ke tepi dan mirip warnanya dibuat transparan (flood fill).
// Bagian dalam logo (mis. huruf putih) tetap utuh.
export function removeBackground(src, tol) {
  const w = src.width, h = src.height, n = w * h;
  const img = src.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, w, h);
  const d = img.data;

  let see = 0;
  for (let i = 3; i < d.length; i += 4) if (d[i] < 200) see++;
  if (see > n * 0.02) return { canvas: src, status: "transparent" };   // sudah transparan

  // Warna latar = warna paling sering muncul di sepanjang tepi
  const bins = new Map();
  const edge = (x, y) => {
    const i = (y * w + x) * 4;
    const k = ((d[i] >> 4) << 8) | ((d[i + 1] >> 4) << 4) | (d[i + 2] >> 4);
    const b = bins.get(k) || [0, 0, 0, 0];
    b[0]++; b[1] += d[i]; b[2] += d[i + 1]; b[3] += d[i + 2];
    bins.set(k, b);
  };
  for (let x = 0; x < w; x++) { edge(x, 0); edge(x, h - 1); }
  for (let y = 1; y < h - 1; y++) { edge(0, y); edge(w - 1, y); }
  const top = [...bins.values()].sort((a, b) => b[0] - a[0])[0];
  const bg = [top[1] / top[0], top[2] / top[0], top[3] / top[0]];

  const dist = (p) => {
    const i = p * 4;
    return Math.hypot(d[i] - bg[0], d[i + 1] - bg[1], d[i + 2] - bg[2]);
  };

  const gone = new Uint8Array(n);
  const stack = [];
  const push = (p) => { if (!gone[p] && dist(p) <= tol) { gone[p] = 1; stack.push(p); } };
  for (let x = 0; x < w; x++) { push(x); push((h - 1) * w + x); }
  for (let y = 0; y < h; y++) { push(y * w); push(y * w + w - 1); }
  while (stack.length) {
    const p = stack.pop(), x = p % w, y = (p / w) | 0;
    if (x > 0) push(p - 1);
    if (x < w - 1) push(p + 1);
    if (y > 0) push(p - w);
    if (y < h - 1) push(p + w);
  }

  const near = (p, fn) => {
    const x = p % w, y = (p / w) | 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const nx = x + dx, ny = y + dy;
      if ((dx || dy) && nx >= 0 && ny >= 0 && nx < w && ny < h && fn(ny * w + nx)) return true;
    }
    return false;
  };

  // Rapikan tepi: buang sisa pinggiran yang masih mirip warna latar
  const fringe = [];
  for (let p = 0; p < n; p++) if (!gone[p] && dist(p) < tol * 1.6 && near(p, (q) => gone[q] === 1)) fringe.push(p);
  fringe.forEach((p) => (gone[p] = 2));

  let removed = 0;
  for (let p = 0; p < n; p++) if (gone[p]) removed++;
  if (removed === 0) return { canvas: src, status: "none" };
  if (removed > n * 0.97) return { canvas: src, status: "failed" };    // salah deteksi, pakai gambar asli

  // Haluskan tepi (anti-alias) dan hitung kotak batas
  const alpha = new Uint8ClampedArray(n);
  for (let p = 0; p < n; p++) alpha[p] = gone[p] ? 0 : 255;
  for (let p = 0; p < n; p++) {
    if (gone[p] || !near(p, (q) => gone[q] > 0)) continue;
    const x = p % w, y = (p / w) | 0;
    let keep = 0, tot = 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
      tot++; if (!gone[ny * w + nx]) keep++;
    }
    alpha[p] = Math.round(255 * Math.min(1, (keep / tot) * 1.4));
  }
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let p = 0; p < n; p++) {
    d[p * 4 + 3] = Math.min(d[p * 4 + 3], alpha[p]);
    if (alpha[p] > 16) {
      const x = p % w, y = (p / w) | 0;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
  }
  const full = document.createElement("canvas");
  full.width = w; full.height = h;
  full.getContext("2d").putImageData(img, 0, 0);

  const pad = 2;
  x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad);
  x1 = Math.min(w - 1, x1 + pad); y1 = Math.min(h - 1, y1 + pad);
  const out = document.createElement("canvas");
  out.width = x1 - x0 + 1; out.height = y1 - y0 + 1;
  out.getContext("2d").drawImage(full, x0, y0, out.width, out.height, 0, 0, out.width, out.height);
  return { canvas: out, status: "removed" };
}
