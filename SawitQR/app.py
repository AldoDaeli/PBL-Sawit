import html
import json
import mimetypes
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import urlparse

import qrcode
import validators
from flask import Flask, jsonify, redirect, request, send_file, send_from_directory
from PIL import Image, ImageOps
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q

# Windows kadang salah mendeteksi .js; modul ES butuh MIME text/javascript
mimetypes.add_type("text/javascript", ".js")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_FILE = os.path.join(DATA_DIR, "links.json")
PHOTO_DIR = os.path.join(DATA_DIR, "photos")

PORT = int(os.environ.get("PORT", 3000))
QR_SIZE = 480  # ukuran QR tetap (px)
TZ = timezone(timedelta(hours=float(os.environ.get("TZ_OFFSET_HOURS", 7))))  # WIB
RESERVED = {"api", "public", "static", "admin", "favicon.ico", "favicon.png", "logo.png"}
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")
ECC = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ---------- Penyimpanan sederhana (file JSON) ----------
os.makedirs(PHOTO_DIR, exist_ok=True)
lock = threading.Lock()
try:
    with open(DB_FILE, encoding="utf-8") as f:
        links = json.load(f)
except (OSError, ValueError):
    links = {}


def save():
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(links, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DB_FILE)  # tulis atomik agar file tidak rusak


# ---------- Helper ----------
def err(msg, status):
    return jsonify({"error": msg}), status


def now_iso(plus_days=0):
    t = datetime.now(timezone.utc) + timedelta(days=plus_days)
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def is_expired(link):
    exp = link.get("expiresAt")
    return bool(exp) and datetime.now(timezone.utc) > datetime.fromisoformat(exp.replace("Z", "+00:00"))


def day_key(dt=None):
    return (dt or datetime.now(timezone.utc)).astimezone(TZ).strftime("%Y-%m-%d")


def device_of(ua=""):
    if re.search(r"ipad|tablet", ua, re.I):
        return "tablet"
    return "mobile" if re.search(r"mobi|android|iphone", ua, re.I) else "desktop"


def base_url():
    # Domain publik tampilan link. Untuk uji lokal: BASE_URL=http://localhost:3000
    return (os.environ.get("BASE_URL") or "https://sawit.qr").rstrip("/")


def new_code():
    while True:
        code = secrets.token_urlsafe(5)[:6]
        if code not in links and code.lower() not in RESERVED:
            return code


def normalize_url(value):
    value = str(value or "").strip()
    if not value:
        return None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        value = "https://" + value
    if urlparse(value).scheme not in ("http", "https"):
        return None
    return value if validators.url(value) is True else None


def page(title, msg):
    return (
        f'<!DOCTYPE html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="/favicon.png">'
        f"<title>{title}</title>"
        f'<body style="font:16px system-ui;display:grid;place-items:center;min-height:100vh;margin:0;background:#F3EBDD;color:#292D25">'
        f'<main style="text-align:center;padding:24px"><h1 style="margin:0 0 8px">{title}</h1>'
        f'<p style="color:#817B54">{msg}</p><a href="/" style="color:#344834;font-weight:600">Buat link baru</a></main>'
    )


def wifi_page(link):
    pw = html.escape(link.get("password") or "")
    pw_row = (f'<code id="pw">{pw}</code><button style="margin-left:12px" onclick="copyPw(this)">Salin sandi</button>'
              if pw else "<i>Tanpa sandi (jaringan terbuka)</i>")
    return (
        '<!DOCTYPE html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="/favicon.png">'
        '<title>Wi-Fi · sawit.qr</title>'
        '<body style="font:16px system-ui;display:grid;place-items:center;min-height:100vh;margin:0;background:#F3EBDD;color:#292D25">'
        '<main style="padding:8px 24px 24px;width:min(420px,100%);border-top:2px solid #292D25">'
        '<p style="margin:16px 0 4px;color:#817B54">Nama Wi-Fi</p>'
        f'<h1 style="margin:0 0 20px;font:600 2rem Georgia,serif;word-break:break-all">{html.escape(link["ssid"])}</h1>'
        '<p style="margin:0 0 4px;color:#817B54">Kata sandi</p>'
        f'<p style="margin:0 0 28px;font-size:1.3rem;word-break:break-all">{pw_row}</p>'
        '<p style="color:#817B54;font-size:.85rem;margin:0">sawit<span style="color:#B58A4A">.qr</span></p></main>'
        '<script>function copyPw(b){navigator.clipboard.writeText(document.getElementById("pw").textContent)'
        '.then(function(){b.textContent="Tersalin"})}</script>'
    )


def photo_page(code):
    return (
        '<!DOCTYPE html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="icon" href="/favicon.png"><title>Foto · sawit.qr</title>'
        '<body style="font:16px system-ui;display:grid;place-items:center;min-height:100vh;margin:0;background:#F3EBDD;color:#292D25">'
        '<main style="padding:24px;width:min(720px,100%);text-align:center">'
        f'<img src="/p/{code}" alt="Foto" style="max-width:100%;max-height:75vh;border:1px solid #DED4C2;border-radius:6px">'
        f'<p><a href="/p/{code}" download="foto-{code}.jpg" style="color:#344834;font-weight:600">Unduh foto</a></p>'
        '<p style="color:#817B54;font-size:.85rem;margin:0">sawit<span style="color:#B58A4A">.qr</span></p></main>'
    )


@app.errorhandler(413)
def too_big(_):
    return err("Ukuran foto terlalu besar (maks. 8 MB).", 413)


# ---------- API ----------
@app.post("/api/shorten")
def shorten():
    body = request.get_json(silent=True) or {}
    url = normalize_url(body.get("url"))
    if not url:
        return err("URL tidak valid. Gunakan alamat http:// atau https://.", 400)

    code = str(body.get("alias") or "").strip()
    with lock:
        if code:
            if not ALIAS_RE.match(code):
                return err("Alias harus 3–30 karakter: huruf, angka, - atau _.", 400)
            if code.lower() in RESERVED or code in links:
                return err("Alias sudah dipakai. Coba alias lain.", 409)
        else:
            code = new_code()
        try:
            days = int(body.get("expiresInDays") or 0)
        except (TypeError, ValueError):
            days = 0
        links[code] = {
            "url": url,
            "clicks": 0,
            "createdAt": now_iso(),
            "expiresAt": now_iso(days) if 0 < days <= 365 else None,
        }
        save()
        return jsonify({"code": code, "shortUrl": f"{base_url()}/{code}", **links[code]}), 201


@app.get("/api/links")
def list_links():
    base = base_url()
    out = []
    for code, link in links.items():
        if link.get("type"):  # wifi/foto tidak masuk daftar link
            continue
        rest = {k: v for k, v in link.items() if k != "stats"}
        qr = sum(d.get("qr", 0) for d in (link.get("stats") or {}).get("days", {}).values())
        out.append({"code": code, "shortUrl": f"{base}/{code}", **rest, "qr": qr})
    out.sort(key=lambda x: x["createdAt"], reverse=True)
    return jsonify(out)


@app.post("/api/wifi")
def create_wifi():
    body = request.get_json(silent=True) or {}
    ssid = str(body.get("ssid") or "").strip()
    pw = str(body.get("password") or "")
    if not ssid or len(ssid) > 64 or len(pw) > 128:
        return err("Nama Wi-Fi wajib diisi (maks. 64 karakter), sandi maks. 128 karakter.", 400)
    with lock:
        code = new_code()
        links[code] = {"type": "wifi", "ssid": ssid, "password": pw, "clicks": 0,
                       "createdAt": now_iso(), "expiresAt": None}
        save()
    return jsonify({"code": code, "shortUrl": f"{base_url()}/{code}"}), 201


@app.post("/api/photo")
def create_photo():
    f = request.files.get("photo")
    if not f:
        return err("Pilih foto terlebih dahulu.", 400)
    try:
        img = ImageOps.exif_transpose(Image.open(f.stream))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        img.thumbnail((1600, 1600))
    except Exception:
        return err("File bukan gambar yang valid.", 400)
    with lock:
        code = new_code()
        img.save(os.path.join(PHOTO_DIR, f"{code}.jpg"), "JPEG", quality=85)
        links[code] = {"type": "photo", "clicks": 0, "createdAt": now_iso(), "expiresAt": None}
        save()
    return jsonify({"code": code, "shortUrl": f"{base_url()}/{code}"}), 201


@app.get("/p/<code>")
def photo_file(code):
    link = links.get(code)
    if not link or link.get("type") != "photo":
        return err("Foto tidak ditemukan.", 404)
    return send_from_directory(PHOTO_DIR, f"{code}.jpg")


@app.patch("/api/links/<code>")
def update_link(code):
    link = links.get(code)
    if not link:
        return err("Link tidak ditemukan.", 404)
    url = normalize_url((request.get_json(silent=True) or {}).get("url"))
    if not url:
        return err("URL tidak valid. Gunakan alamat http:// atau https://.", 400)
    with lock:
        link["url"] = url
        save()
    return jsonify({"code": code, **link})


@app.get("/api/links/<code>/stats")
def link_stats(code):
    link = links.get(code)
    if not link:
        return err("Link tidak ditemukan.", 404)
    s = link.get("stats") or {"days": {}, "devices": {}, "refs": {}}
    now = datetime.now(timezone.utc)
    days = []
    for i in range(13, -1, -1):
        k = day_key(now - timedelta(days=i))
        days.append({"d": k, "link": 0, "qr": 0, **s["days"].get(k, {})})
    refs = sorted(s["refs"].items(), key=lambda kv: kv[1], reverse=True)[:5]
    return jsonify({"clicks": link["clicks"], "days": days, "devices": s["devices"], "refs": refs})


@app.delete("/api/links/<code>")
def delete_link(code):
    with lock:
        if code not in links:
            return err("Link tidak ditemukan.", 404)
        del links[code]
        save()
    return "", 204


# Generator QR: /api/qr?text=...&ec=M|H&format=png|svg&download=1 (ukuran tetap)
@app.get("/api/qr")
def qr_image():
    text = request.args.get("text", "")
    if not text or len(text) > 1000:
        return err("Teks wajib diisi (maksimal 1000 karakter).", 400)
    level = ECC.get(request.args.get("ec", "M").upper(), ERROR_CORRECT_M)
    fmt = "svg" if request.args.get("format") == "svg" else "png"

    qr = qrcode.QRCode(error_correction=level, box_size=10, border=2)
    qr.add_data(text)
    qr.make(fit=True)

    if fmt == "svg":
        m = qr.get_matrix()
        n = len(m)
        path = "".join(f"M{x} {y}h1v1h-1z" for y, row in enumerate(m) for x, on in enumerate(row) if on)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{QR_SIZE}" height="{QR_SIZE}" viewBox="0 0 {n} {n}" '
            f'shape-rendering="crispEdges"><path fill="#ffffff" d="M0 0h{n}v{n}H0z"/>'
            f'<path fill="#000000" d="{path}"/></svg>'
        )
        data, mime = BytesIO(svg.encode("utf-8")), "image/svg+xml"
    else:
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img = img.resize((QR_SIZE, QR_SIZE), Image.NEAREST)
        data, mime = BytesIO(), "image/png"
        img.save(data, "PNG")
        data.seek(0)
    return send_file(data, mimetype=mime, as_attachment=bool(request.args.get("download")),
                     download_name=f"qr-code.{fmt}")


# ---------- Halaman & redirect ----------
@app.get("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


# /abc123 -> URL asli (?src=qr menandai pemindaian QR). File statis (app.js, style.css) dilayani di sini juga.
@app.get("/<code>")
def go(code):
    if os.path.isfile(os.path.join(PUBLIC_DIR, code)):
        return send_from_directory(PUBLIC_DIR, code)
    link = links.get(code)
    if not link:
        return page("Link tidak ditemukan", "Periksa lagi alamatnya, atau link ini sudah dihapus."), 404
    if is_expired(link):
        return page("Link sudah kedaluwarsa", "Pemilik link ini membatasi masa aktifnya."), 410
    if link.get("type") == "wifi":
        return wifi_page(link)
    if link.get("type") == "photo":
        return photo_page(code)
    if request.method == "GET":
        src = "qr" if request.args.get("src") == "qr" else "link"
        with lock:
            s = link.setdefault("stats", {"days": {}, "devices": {}, "refs": {}})
            s["days"].setdefault(day_key(), {"link": 0, "qr": 0})[src] += 1
            dev = device_of(request.headers.get("User-Agent", ""))
            s["devices"][dev] = s["devices"].get(dev, 0) + 1
            ref = urlparse(request.referrer or "").hostname or "langsung"
            if ref in s["refs"] or len(s["refs"]) < 30:
                s["refs"][ref] = s["refs"].get(ref, 0) + 1
            link["clicks"] += 1
            save()
    return redirect(link["url"], 302)


if __name__ == "__main__":
    print(f"Berjalan di http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT)
