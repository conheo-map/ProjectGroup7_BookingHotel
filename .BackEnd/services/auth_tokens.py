"""Token API ký bằng SECRET_KEY (itsdangerous), không cần thêm dependency."""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import API_TOKEN_MAX_AGE, SECRET_KEY

_serializer = None


def _get_serializer():
    global _serializer
    if _serializer is None:
        _serializer = URLSafeTimedSerializer(SECRET_KEY, salt='hotel-booking-api-v1')
    return _serializer


def create_api_token(user_id: int, account_type: str) -> str:
    return _get_serializer().dumps({'uid': int(user_id), 'atype': str(account_type)})


def verify_api_token(token: str):
    if not token or not isinstance(token, str):
        return None
    try:
        return _get_serializer().loads(token, max_age=API_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
