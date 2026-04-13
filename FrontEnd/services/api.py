import os
import requests
from flask import session

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://localhost:5000')
_TIMEOUT = 15


def _headers(token=None):
    t = token or session.get('token', '')
    h = {'Content-Type': 'application/json'}
    if t:
        h['Authorization'] = f'Bearer {t}'
    return h


def api_get(path, params=None, token=None):
    try:
        r = requests.get(
            f'{BACKEND_URL}{path}',
            params=params,
            headers=_headers(token),
            timeout=_TIMEOUT,
        )
        return r.json()
    except Exception as e:
        return {'success': False, 'message': str(e)}


def api_post(path, data=None, token=None):
    try:
        r = requests.post(
            f'{BACKEND_URL}{path}',
            json=data or {},
            headers=_headers(token),
            timeout=_TIMEOUT,
        )
        try:
            return r.json()
        except Exception:
            return {'success': False, 'message': f'Backend trả về lỗi (HTTP {r.status_code}): {r.text[:200]}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def api_put(path, data=None, token=None):
    try:
        r = requests.put(
            f'{BACKEND_URL}{path}',
            json=data or {},
            headers=_headers(token),
            timeout=_TIMEOUT,
        )
        try:
            return r.json()
        except Exception:
            return {'success': False, 'message': f'Backend trả về lỗi (HTTP {r.status_code}): {r.text[:200]}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def api_delete(path, token=None):
    try:
        r = requests.delete(
            f'{BACKEND_URL}{path}',
            headers=_headers(token),
            timeout=_TIMEOUT,
        )
        return r.json()
    except Exception as e:
        return {'success': False, 'message': str(e)}


def api_get_qs(path_with_qs, token=None):
    """GET với query string đã được build sẵn (hỗ trợ multi-value array params như star_ratings[])."""
    try:
        r = requests.get(
            f'{BACKEND_URL}{path_with_qs}',
            headers=_headers(token),
            timeout=_TIMEOUT,
        )
        return r.json()
    except Exception as e:
        return {'success': False, 'message': str(e)}


def api_upload(path, files, token=None):
    """Upload file qua multipart/form-data (không set Content-Type, để requests tự xử lý boundary)."""
    try:
        t = token or session.get('token', '')
        h = {}
        if t:
            h['Authorization'] = f'Bearer {t}'
        r = requests.post(
            f'{BACKEND_URL}{path}',
            files=files,
            headers=h,
            timeout=30,
        )
        try:
            return r.json()
        except Exception:
            return {'success': False, 'message': f'Backend trả về lỗi (HTTP {r.status_code}): {r.text[:200]}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

