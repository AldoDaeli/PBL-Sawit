"""Titik masuk WSGI (Flask).
Pengembangan : flask --app main run --debug --port 5000      (atau: python main.py)
Produksi     : gunicorn -w 2 -b 127.0.0.1:5000 main:app      (Windows: waitress-serve --listen=127.0.0.1:5000 main:app)
Dokumentasi API: http://localhost:5000/api/docs"""
from app import create_app
from app.config import cfg

app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=cfg['DEBUG'])
