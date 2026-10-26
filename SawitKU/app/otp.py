"""OTP email: pembuatan kode, hash, dan pengiriman lewat SMTP (pendaftaran dan penggantian email)."""
import hashlib, hmac, logging, secrets, smtplib, ssl
from email.message import EmailMessage
from .config import cfg
from .errors import ApiError

log = logging.getLogger('sawitku')


def buat_kode():
    return f'{secrets.randbelow(10 ** 6):06d}'          # 6 angka, acak kriptografis


def hash_kode(email, kode, garam):
    return hashlib.sha256(f'{garam}:{email}:{kode}'.encode()).hexdigest()


def cocok(a, b):
    return hmac.compare_digest(a, b)


def _kirim(m, catatan_dev):
    """Kirim lewat SMTP. Tanpa SMTP_HOST: hanya boleh di mode pengembangan (OTP_CETAK_KODE=1 atau --debug), selain itu
    DITOLAK agar produksi tidak diam-diam gagal dan kode tidak bocor ke log."""
    c = cfg
    if not c['SMTP_HOST']:
        if c['OTP_CETAK_KODE'] or c['DEBUG']:
            log.warning('[MODE PENGEMBANGAN: email TIDAK dikirim] %s', catatan_dev)
            return
        log.error('SMTP_HOST belum diisi: email tidak dapat dikirim.')
        raise ApiError('Layanan email belum dikonfigurasi. Hubungi admin.', 503)
    m['From'] = c['SMTP_FROM'] or c['SMTP_USER']
    try:
        if c['SMTP_MODE'] == 'ssl':
            s = smtplib.SMTP_SSL(c['SMTP_HOST'], c['SMTP_PORT'], timeout=10, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(c['SMTP_HOST'], c['SMTP_PORT'], timeout=10)
        with s:
            if c['SMTP_MODE'] == 'starttls':
                s.starttls(context=ssl.create_default_context())
            if c['SMTP_USER']:
                s.login(c['SMTP_USER'], c['SMTP_PASSWORD'])
            s.send_message(m)
    except (smtplib.SMTPException, OSError):
        log.exception('Gagal mengirim email ke %s', m['To'])
        raise ApiError('Gagal mengirim email kode OTP. Periksa alamat email atau coba lagi nanti.', 502)


def kirim_kode(email, username, kode, perihal='pendaftaran'):
    """Kirim kode OTP ke `email`. perihal: 'pendaftaran' atau 'penggantian email'."""
    m = EmailMessage()
    m['Subject'] = f'Kode verifikasi SawitKu: {kode}'
    m['To'] = email
    m.set_content(
        f"Halo {username},\n\n"
        f"Kode verifikasi {perihal} SawitKu kamu:\n\n    {kode}\n\n"
        f"Kode berlaku {cfg['OTP_MENIT']} menit. Jangan bagikan kode ini kepada siapa pun, termasuk pihak yang mengaku dari SawitKu.\n\n"
        f"Jika kamu tidak merasa memintanya, abaikan email ini.\n\nSawitKu")
    _kirim(m, f'{email} -> kode {kode} ({perihal})')


def kirim_reset(email, username, kode):
    """Kode OTP untuk mengatur ulang password."""
    m = EmailMessage()
    m['Subject'] = f'Kode reset password SawitKu: {kode}'
    m['To'] = email
    m.set_content(
        f"Halo {username},\n\nKami menerima permintaan mengatur ulang password akun SawitKu kamu. Kode verifikasinya:\n\n    {kode}\n\n"
        f"Kode berlaku {cfg['OTP_MENIT']} menit. Jangan bagikan kode ini kepada siapa pun.\n\n"
        f"Jika bukan kamu yang memintanya, abaikan email ini; password kamu tidak berubah.\n\nSawitKu")
    _kirim(m, f'{email} -> kode {kode} (reset password)')


def kirim_info_password_diubah(email, username):
    """Pemberitahuan password berhasil diubah (upaya terbaik)."""
    m = EmailMessage()
    m['Subject'] = 'Password akun SawitKu kamu diubah'
    m['To'] = email
    m.set_content(f"Halo {username},\n\nPassword akun SawitKu kamu baru saja diubah lewat fitur lupa password. Semua sesi login lama sudah dikeluarkan.\n\n"
                  f"Jika ini bukan kamu, segera hubungi admin SawitKu.\n\nSawitKu")
    try: _kirim(m, f'{email}: password diubah')
    except ApiError: pass


def kirim_info_email_diganti(email_lama, username, email_baru):
    """Pemberitahuan ke email LAMA bahwa email akun diganti (upaya terbaik: gagal kirim tidak membatalkan penggantian)."""
    m = EmailMessage()
    m['Subject'] = 'Email akun SawitKu kamu diganti'
    m['To'] = email_lama
    m.set_content(f"Halo {username},\n\nEmail akun SawitKu kamu baru saja diganti menjadi {email_baru}.\n\n"
                  f"Jika ini bukan kamu, segera hubungi admin SawitKu.\n\nSawitKu")
    try:
        _kirim(m, f'{email_lama}: email akun diganti menjadi {email_baru}')
    except ApiError:
        pass
