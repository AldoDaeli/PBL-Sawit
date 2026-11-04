"""Akses data produk lewat ORM SQLAlchemy (katalog + CRUD admin). Semua query produk lewat kelas ini."""
from sqlalchemy import func, select

from .extensions import db
from .models import Produk, Ulasan


class ProdukService:
    @staticmethod
    def _n_ulasan():
        return select(func.count(Ulasan.id)).where(Ulasan.produk_id == Produk.id).correlate(Produk).scalar_subquery()

    @classmethod
    def daftar(cls):
        """Seluruh produk (urut id) + jumlah ulasan, sebagai list dict siap untuk serializers.produk_out."""
        q = select(Produk, cls._n_ulasan().label('n_ulasan')).order_by(Produk.id)
        return [p.sebagai_baris(n) for p, n in db.session.execute(q).all()]

    @classmethod
    def baris(cls, pid):
        """Satu produk + jumlah ulasan sebagai dict, atau None bila tidak ada."""
        hasil = db.session.execute(select(Produk, cls._n_ulasan().label('n_ulasan')).where(Produk.id == pid)).first()
        return hasil[0].sebagai_baris(hasil[1]) if hasil else None

    @staticmethod
    def ambil(pid, kunci=False):
        """Objek Produk (kunci=True -> SELECT ... FOR UPDATE di MariaDB) atau None."""
        return db.session.get(Produk, pid, with_for_update=kunci)

    @staticmethod
    def buat(d, waktu):
        p = Produk(nama=d['nama'], kategori=d['kategori'], harga=d['harga'], stok=d['stok'], terjual=0, rating=0,
                   best_seller=d['best_seller'], gambar=d['gambar'], deskripsi=d['deskripsi'], spesifikasi=d['spesifikasi'], dibuat=waktu)
        db.session.add(p); db.session.commit()
        return p

    @staticmethod
    def ubah(p, d):
        for k in ('nama', 'kategori', 'harga', 'stok', 'best_seller', 'gambar', 'deskripsi', 'spesifikasi'): setattr(p, k, d[k])
        db.session.commit()
        return p

    @staticmethod
    def hapus(p):
        """Keranjang/favorit/ulasan ikut terhapus (ON DELETE CASCADE); riwayat pesanan tetap (produk_id jadi NULL)."""
        db.session.delete(p); db.session.commit()
