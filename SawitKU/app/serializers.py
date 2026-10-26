"""Bentuk JSON sama dengan objek yang dipakai frontend (camelCase, waktu = epoch ms)."""
import json

from .config import cfg
from .uploads import url_keluar


def baca_json(teks, bawaan):
    try: return json.loads(teks) if teks else bawaan
    except ValueError: return bawaan


def user_out(u):
    return {'id': u['id'], 'username': u['username'], 'email': u['email'], 'peran': u['peran'],
            'aktif': bool(u['aktif']), 'foto': url_keluar(u['foto']), 'dibuat': u['dibuat'],
            'telepon': u.get('telepon') or '', 'alamat': u.get('alamat') or '', 'kota': u.get('kota') or '', 'kodePos': u.get('kode_pos') or ''}


def produk_out(p):
    return {'id': p['id'], 'nama': p['nama'], 'kategori': p['kategori'], 'harga': p['harga'], 'stok': p['stok'],
            'terjual': p['terjual'], 'rating': float(p['rating']), 'jumlahUlasan': p.get('n_ulasan') or 0, 'bestSeller': bool(p['best_seller']),
            'gambar': url_keluar(p['gambar']), 'deskripsi': p['deskripsi'], 'spesifikasi': baca_json(p['spesifikasi'], {}), 'dibuat': p['dibuat']}


def ulasan_out(r, lanjutan=None):
    """lanjutan = balasan lanjutan (admin <-> pemilik ulasan) berurutan; balasan pertama admin tetap di `balasan`."""
    return {'id': r['id'], 'produkId': r['produk_id'], 'userId': r['user_id'], 'nama': r['nama'],
            'rating': r['rating'], 'teks': r['teks'], 'dibuat': r['dibuat'],
            'balasan': {'teks': r['balasan_teks'], 'dibuat': r['balasan_dibuat']} if r['balasan_teks'] else None,
            'lanjutan': [{'dari': x['dari'], 'teks': x['teks'], 'dibuat': x['dibuat']} for x in (lanjutan or [])]}


def pesanan_out(o, items):
    batas_terima = (o['t_sampai'] + cfg['AUTO_TERIMA_JAM'] * 3600000) if o.get('t_sampai') and o['status'] == 'dikirim' else None
    return {'id': o['id'], 'userId': o['user_id'], 'total': o['total'], 'status': o['status'],
            'bukti': url_keluar(o['bukti']), 'alasan': o['alasan'], 'dibuat': o['dibuat'], 'batasBayar': o['batas_bayar'],
            'ditolak': o.get('ditolak') or 0, 'kurir': o.get('kurir') or '', 'resi': o.get('resi') or '', 'metode': o.get('metode') or '',
            # Tagihan Midtrans (QR / nomor VA) + status terakhir dari Midtrans; hanya bahan verifikasi, bukan persetujuan
            'midtrans': {'status': o.get('midtrans_status') or '', 'data': baca_json(o.get('midtrans_data'), {})} if o.get('midtrans_id') else None,
            'fotoTerima': url_keluar(o.get('foto_terima')), 'otomatis': bool(o.get('otomatis')), 'batasTerima': batas_terima,
            'waktu': {'bayar': o.get('t_bayar'), 'proses': o.get('t_proses'), 'kirim': o.get('t_kirim'), 'sampai': o.get('t_sampai'), 'selesai': o.get('t_selesai')},
            'pengiriman': ({'penerima': o['penerima'], 'telepon': o['telepon'], 'alamat': o['alamat'], 'kota': o['kota'], 'kodePos': o['kode_pos']}
                           if o.get('alamat') else None),
            'items': [{'produkId': i['produk_id'], 'nama': i['nama'], 'gambar': url_keluar(i['gambar']),
                       'harga': i['harga'], 'qty': i['qty']} for i in items]}


def chat_out(m):
    return {'id': m['id'], 'dari': m['dari'], 'isi': m['isi'], 'dibuat': m['dibuat'], 'dibaca': bool(m['dibaca'])}
