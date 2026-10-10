from flask import Blueprint, request, jsonify
from ..errors import ApiError

bp = Blueprint('api', __name__)

def body():
    b = request.get_json(silent=True)
    if not isinstance(b, dict): raise ApiError('Format data tidak valid.')
    return b

def ok(data=None, status=200):
    return jsonify({'data': data}), status

from . import publik, customer, admin, chat  # noqa: E402,F401  (mendaftarkan rute ke bp)
