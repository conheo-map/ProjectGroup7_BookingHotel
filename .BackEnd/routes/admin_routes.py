from flask import Blueprint, request, jsonify, g
from database import get_db_connection
from services.api_auth import require_token
from services.booking_service import get_user_role_from_db

admin_bp = Blueprint('admin_bp', __name__)


# ─── USER MANAGEMENT ENDPOINTS ───────────────────────────────────────────────

@admin_bp.route('/api/users', methods=['GET'])
def api_get_users():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role != 'Admin':
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.user_id, u.username, u.email, u.full_name, u.created_at,
               GROUP_CONCAT(r.role_name, ', ') as roles
        FROM Users u
        LEFT JOIN User_Roles ur ON u.user_id = ur.user_id
        LEFT JOIN Roles r ON ur.role_id = r.role_id
        GROUP BY u.user_id ORDER BY u.created_at DESC
    """)
    users_list = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'users': users_list})


@admin_bp.route('/api/users/<int:target_user_id>/role', methods=['PUT'])
def api_update_user_role(target_user_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role != 'Admin':
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    new_role_name = data.get('new_role_name')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role_id FROM Roles WHERE role_name = ?", (new_role_name,))
    role_row = cursor.fetchone()
    if not role_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Vai tro khong ton tai'}), 404
    cursor.execute("DELETE FROM User_Roles WHERE user_id = ?", (target_user_id,))
    cursor.execute("INSERT INTO User_Roles (user_id, role_id) VALUES (?, ?)", (target_user_id, role_row['role_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cap nhat vai tro thanh cong'})


@admin_bp.route('/api/users/<int:target_user_id>', methods=['DELETE'])
def api_delete_user(target_user_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role != 'Admin':
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM User_Roles WHERE user_id = ?", (target_user_id,))
    cursor.execute("DELETE FROM Users WHERE user_id = ?", (target_user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Xoa thanh cong'})


