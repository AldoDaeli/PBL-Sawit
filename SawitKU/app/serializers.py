"""Bentuk JSON sama dengan objek yang dipakai frontend (camelCase, waktu = epoch ms)."""
import json
from .uploads import url_keluar

def user_out(u):
    return {'id': u['id'], 'username': u['username'], 'email': u['email'], 'peran': u['peran'],
            'aktif': bool(u['aktif']), 'foto': url_keluar(u['foto']), 'dibuat': u['dibuat'],
            'telepon': u.get('telepon') or '', 'alamat': u.get('alamat') or '', 'kota': u.get('kota') or '', 'kodePos': u.get('kode_pos') or ''}

def produk_out(p):
    try: spek = json.loads(p['spesifikasi'] or '{}')
    except ValueError: spek = {}
    return {'id': p['id'], 'nama': p['nama'], 'kategori': p['kategori'], 'harga': p['harga'], 'stok': p['stok'],
            'terjual': p['terjual'], 'rating': float(p['rating']), 'bestSeller': bool(p['best_seller']),
            'gambar': url_keluar(p['gambar']), 'deskripsi': p['deskripsi'], 'spesifikasi': spek, 'dibuat': p['dibuat']}

def ulasan_out(r):
    return {'id': r['id'], 'produkId': r['produk_id'], 'userId': r['user_id'], 'nama': r['nama'],
            'rating': r['rating'], 'teks': r['teks'], 'dibuat': r['dibuat'],
            'balasan': {'teks': r['balasan_teks'], 'dibuat': r['balasan_dibuat']} if r['balasan_teks'] else None}

def pesanan_out(o, items):
    return {'id': o['id'], 'userId': o['user_id'], 'total': o['total'], 'status': o['status'],
            'bukti': url_keluar(o['bukti']), 'alasan': o['alasan'], 'dibuat': o['dibuat'], 'batasBayar': o['batas_bayar'],
            'pengiriman': ({'penerima': o['penerima'], 'telepon': o['telepon'], 'alamat': o['alamat'], 'kota': o['kota'], 'kodePos': o['kode_pos']}
                           if o.get('alamat') else None),
            'items': [{'produkId': i['produk_id'], 'nama': i['nama'], 'gambar': url_keluar(i['gambar']),
                       'harga': i['harga'], 'qty': i['qty']} for i in items]}


def chat_out(m):
    return {'id': m['id'], 'dari': m['dari'], 'isi': m['isi'], 'dibuat': m['dibuat'], 'dibaca': bool(m['dibaca'])}
