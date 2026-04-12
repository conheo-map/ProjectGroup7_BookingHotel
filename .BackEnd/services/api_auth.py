"""Ngữ cảnh xác thực từ header Authorization: Bearer <token>."""
from flask import g, jsonify

from services.booking_service import get_user_role_from_db


def init_auth_context():
    from services.auth_tokens import verify_api_token
    from flask import request

    g.api_user_id = None
    g.api_account_type = None
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        payload = verify_api_token(auth[7:].strip())
        if payload:
            g.api_user_id = payload['uid']
            g.api_account_type = payload['atype']


def require_token():
    if getattr(g, 'api_user_id', None) is None:
        return jsonify({'success': False, 'message': 'Can dang nhap hoac token khong hop le'}), 401
    return None


def get_caller_role():
    uid = getattr(g, 'api_user_id', None)
    atype = getattr(g, 'api_account_type', 'customer')
    if uid is None:
        return None
    return get_user_role_from_db(uid, atype)


def can_access_customer_booking(booking_user_id: int) -> bool:
    role = get_caller_role()
    if role in ('Admin', 'Manager', 'Receptionist'):
        return True
    if getattr(g, 'api_account_type', None) == 'customer' and getattr(g, 'api_user_id', None) == booking_user_id:
        return True
    return False
