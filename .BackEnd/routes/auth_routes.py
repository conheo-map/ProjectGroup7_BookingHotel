import html as _html
from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection
from services.auth_tokens import create_api_token
from services.api_auth import require_token

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    customer_name = (data.get('customer_name') or data.get('full_name') or '').strip()
    if not email or not password:
        return jsonify({'success': False, 'message': 'Vui long nhap email va mat khau'}), 400
    password_hash = generate_password_hash(password)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO Customer_Accounts (email, password_hash, customer_name)
            VALUES (?, ?, ?)
        """, (email, password_hash, customer_name))
        new_account_id = cursor.lastrowid
        conn.commit()
        return jsonify({'success': True, 'message': 'Dang ky thanh cong', 'user_id': new_account_id})
    except Exception:
        return jsonify({'success': False, 'message': 'Email nay da duoc su dung'}), 409
    finally:
        conn.close()


@auth_bp.route('/api/profile/update', methods=['PUT'])
def api_update_profile():
    """Cap nhat ten va mat khau cho tai khoan khach hang."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    if g.api_account_type != 'customer':
        return jsonify({'success': False, 'message': 'Chi tai khoan khach hang moi duoc cap nhat ho so'}), 403

    data = request.get_json() or {}
    customer_name = _html.escape(data.get('customer_name', '').strip())[:100]
    old_password = data.get('old_password', '').strip()
    new_password = data.get('new_password', '').strip()

    if not customer_name:
        return jsonify({'success': False, 'message': 'Ten khong duoc de trong'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if new_password:
            if not old_password:
                return jsonify({'success': False, 'message': 'Vui long nhap mat khau hien tai de doi mat khau'}), 400
            cursor.execute("SELECT password_hash FROM Customer_Accounts WHERE account_id = ?", (g.api_user_id,))
            row = cursor.fetchone()
            if not row or not check_password_hash(row['password_hash'], old_password):
                return jsonify({'success': False, 'message': 'Mat khau hien tai khong dung'}), 400
            cursor.execute(
                "UPDATE Customer_Accounts SET customer_name = ?, password_hash = ? WHERE account_id = ?",
                (customer_name, generate_password_hash(new_password), g.api_user_id)
            )
        else:
            cursor.execute(
                "UPDATE Customer_Accounts SET customer_name = ? WHERE account_id = ?",
                (customer_name, g.api_user_id)
            )
        conn.commit()
        return jsonify({'success': True, 'message': 'Cap nhat ho so thanh cong', 'customer_name': customer_name})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()


@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    login_input = (data.get('username') or data.get('email') or '').strip()
    password = data.get('password', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Thu Customer_Accounts
    cursor.execute("""
        SELECT account_id, email, password_hash, customer_name, loyalty_points, membership_tier
        FROM Customer_Accounts WHERE email = ?
    """, (login_input,))
    customer_row = cursor.fetchone()
    if customer_row and check_password_hash(customer_row['password_hash'], password):
        conn.close()
        uid = customer_row['account_id']
        return jsonify({
            'success': True, 'user_id': uid,
            'username': customer_row['email'], 'email': customer_row['email'],
            'full_name': customer_row['customer_name'] or '', 'role': 'Guest',
            'account_type': 'customer',
            'token': create_api_token(uid, 'customer'),
        })
        
    # 2. Thu Users (staff)
    cursor.execute("""
        SELECT user_id, username, email, password_hash, full_name FROM Users WHERE username = ?
    """, (login_input,))
    staff_row = cursor.fetchone()
    if not staff_row or not check_password_hash(staff_row['password_hash'], password):
        conn.close()
        return jsonify({'success': False, 'message': 'Sai thong tin dang nhap'}), 401
        
    cursor.execute("""
        SELECT r.role_name FROM Roles r
        JOIN User_Roles ur ON r.role_id = ur.role_id
        WHERE ur.user_id = ?
        ORDER BY r.role_id DESC LIMIT 1
    """, (staff_row['user_id'],))
    role_row = cursor.fetchone()
    role_name = role_row['role_name'] if role_row else 'Guest'
    conn.close()
    
    sid = staff_row['user_id']
    return jsonify({
        'success': True, 'user_id': sid,
        'username': staff_row['username'], 'email': staff_row['email'],
        'full_name': staff_row['full_name'], 'role': role_name,
        'account_type': 'staff',
        'token': create_api_token(sid, 'staff'),
    })
