"""Chat pelanggan <-> admin. Satu percakapan per pelanggan; pelanggan hanya bisa mengakses percakapannya sendiri
(id pemilik SELALU diambil dari sesi, tidak pernah dari input), admin bisa membaca dan membalas semua percakapan pelanggan."""
from flask import request

from . import api, ok
from ..config import cfg
from ..db import get_db
from ..errors import ApiError
from ..schemas import badan, ChatIn
from ..security import now_ms, wajib, batasi_laju
from ..serializers import chat_out
from ..validators import bersihkan_chat

HALAMAN = 50
pelanggan, admin_saja = wajib('customer'), wajib('admin')


def _id_param(args, nama):
    v = args.get(nama)
    return int(v) if v and v.isdigit() and len(v) < 12 else 0


def _ambil(db, uid, args, lawan):
    """Pesan satu percakapan. sejak=<id>: hanya yang lebih baru (polling ringan); sebelum=<id>: halaman lebih lama;
    tanpa keduanya: halaman terbaru. Pesan dari `lawan` ditandai dibaca. dibacaSampai = id pesan MILIK pembaca yang sudah dibaca lawan."""
    sejak, sebelum, ada_lagi = _id_param(args, 'sejak'), _id_param(args, 'sebelum'), False
    if sejak:
        rows = db.all('SELECT * FROM chat_pesan WHERE user_id=%s AND id>%s ORDER BY id LIMIT 100', (uid, sejak))
    else:
        if sebelum: rows = db.all('SELECT * FROM chat_pesan WHERE user_id=%s AND id<%s ORDER BY id DESC LIMIT %s', (uid, sebelum, HALAMAN + 1))
        else: rows = db.all('SELECT * FROM chat_pesan WHERE user_id=%s ORDER BY id DESC LIMIT %s', (uid, HALAMAN + 1))
        ada_lagi, rows = len(rows) > HALAMAN, rows[:HALAMAN][::-1]
    if any(r['dari'] == lawan and not r['dibaca'] for r in rows):       # tulis ke DB hanya bila memang ada yang baru dibaca
        db.run('UPDATE chat_pesan SET dibaca=1 WHERE user_id=%s AND dari=%s AND dibaca=0', (uid, lawan))
    milik = 'admin' if lawan == 'customer' else 'customer'
    m = db.one('SELECT MAX(id) AS m FROM chat_pesan WHERE user_id=%s AND dari=%s AND dibaca=1', (uid, milik))
    return {'pesan': [chat_out(r) for r in rows], 'adaLagi': ada_lagi, 'dibacaSampai': (m and m['m']) or 0}


def _simpan(db, uid, dari, isi, admin_id=None):
    i, _ = db.run('INSERT INTO chat_pesan (user_id,dari,admin_id,isi,dibuat,dibaca) VALUES (%s,%s,%s,%s,%s,0)', (uid, dari, admin_id, isi, now_ms()))
    return chat_out(db.one('SELECT * FROM chat_pesan WHERE id=%s', (i,)))


# ---------------- Pelanggan ----------------
@api.get('/chat', tags=['Chat'])
@pelanggan
def chat_saya(u):
    return ok(_ambil(get_db(), u['id'], request.args, 'admin'))


@api.get('/chat/belum', tags=['Chat'])
@pelanggan
def chat_belum_saya(u):
    r = get_db().one("SELECT COUNT(*) AS n FROM chat_pesan WHERE user_id=%s AND dari='admin' AND dibaca=0", (u['id'],))
    return ok({'belum': r['n']})


@api.post('/chat', status_code=201, tags=['Chat'])
@pelanggan
def chat_kirim(u):
    b = badan(ChatIn)
    c, db, uid = cfg, get_db(), u['id']
    batasi_laju('chat', c['LAJU_CHAT'], 60, siapa=f'u{uid}')                  # per akun
    batasi_laju('chat-ip', c['LAJU_CHAT'] * 3, 60)                           # per IP (banyak akun dari satu tempat)
    isi = bersihkan_chat(b.isi)
    r = db.one("SELECT COUNT(*) AS n FROM chat_pesan WHERE user_id=%s AND dari='customer' AND id > "
               "COALESCE((SELECT MAX(id) FROM chat_pesan WHERE user_id=%s AND dari='admin'), 0)", (uid, uid))
    if r['n'] >= c['CHAT_MAKS_BERUNTUN']:
        raise ApiError('Admin belum membalas. Tunggu balasan sebelum mengirim pesan lagi.', 429)
    return ok(_simpan(db, uid, 'customer', isi))


# ---------------- Admin ----------------
def _pelanggan(db, uid):
    u = db.one('SELECT id, username, email, aktif, peran FROM pengguna WHERE id=%s', (uid,))
    if not u or u['peran'] != 'customer': raise ApiError('Pelanggan tidak ditemukan.', 404)
    return u


@api.get('/admin/chat', tags=['Chat'])
@admin_saja
def admin_chat_daftar(_):
    rows = get_db().all(
        "SELECT u.id AS user_id, u.username, u.aktif, m.dari, m.isi, m.dibuat, "
        "(SELECT COUNT(*) FROM chat_pesan x WHERE x.user_id=u.id AND x.dari='customer' AND x.dibaca=0) AS belum "
        "FROM (SELECT user_id, MAX(id) AS mid FROM chat_pesan GROUP BY user_id) t "
        "JOIN chat_pesan m ON m.id=t.mid JOIN pengguna u ON u.id=t.user_id ORDER BY m.id DESC LIMIT 200")
    return ok([{'userId': r['user_id'], 'username': r['username'], 'aktif': bool(r['aktif']), 'dari': r['dari'],
                'terakhir': r['isi'][:80], 'dibuat': r['dibuat'], 'belum': r['belum']} for r in rows])


@api.get('/admin/chat/belum', tags=['Chat'])
@admin_saja
def admin_chat_belum(_):
    r = get_db().one("SELECT COUNT(*) AS n FROM chat_pesan WHERE dari='customer' AND dibaca=0")
    return ok({'belum': r['n']})


@api.get('/admin/chat/<int:uid>', tags=['Chat'])
@admin_saja
def admin_chat_baca(_, uid):
    db = get_db(); u = _pelanggan(db, uid)
    d = _ambil(db, uid, request.args, 'customer')
    if not request.args.get('sejak'): d['pelanggan'] = {'id': u['id'], 'username': u['username'], 'email': u['email'], 'aktif': bool(u['aktif'])}
    return ok(d)


@api.post('/admin/chat/<int:uid>', status_code=201, tags=['Chat'])
@admin_saja
def admin_chat_balas(adm, uid):
    b = badan(ChatIn)
    db = get_db()
    batasi_laju('chat-admin', 60, 60, siapa=f"a{adm['id']}")
    u = _pelanggan(db, uid)
    if not db.one('SELECT id FROM chat_pesan WHERE user_id=%s LIMIT 1', (uid,)):
        raise ApiError('Percakapan belum dimulai oleh pelanggan.', 404)       # admin hanya membalas, tidak memulai chat
    if not u['aktif']: raise ApiError('Akun pelanggan dinonaktifkan.', 409)
    return ok(_simpan(db, uid, 'admin', bersihkan_chat(b.isi), adm['id']))
