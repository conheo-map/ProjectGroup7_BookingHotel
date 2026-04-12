from flask import Blueprint, request, jsonify, g
from database import get_db_connection
from services.api_auth import require_token
from services.booking_service import get_user_role_from_db
from datetime import datetime, timedelta, date
import sqlite3
import time

manager_bp = Blueprint('manager_bp', __name__)

# ─── IN-MEMORY TTL CACHE CHO ANALYTICS ────────────────────────────────────────
_analytics_cache = {}
_CACHE_TTL_SECONDS = 120  # cache 2 phút

def _get_cached(cache_key):
    """Trả về dữ liệu cache nếu còn hiệu lực, ngược lại None."""
    entry = _analytics_cache.get(cache_key)
    if entry and (time.time() - entry['ts']) < _CACHE_TTL_SECONDS:
        return entry['data']
    return None

def _set_cached(cache_key, data):
    """Lưu dữ liệu vào cache với timestamp hiện tại."""
    _analytics_cache[cache_key] = {'data': data, 'ts': time.time()}



# ─── INVENTORY & DIMENSION CRUD ──────────────────────────────────────────────

@manager_bp.route('/api/inventory/comprehensive', methods=['GET'])
def api_get_comprehensive_inventory():
    """Trả về danh sách Loại phòng lồng danh sách Phòng vật lý kèm lịch giá tuần."""
    hotel_id = request.args.get('hotel_id', type=int)
    room_name_search = request.args.get('room_name', '').strip()
    start_date_str = request.args.get('start_date')
    
    # 1. Tính toán danh sách 7 ngày
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except:
            start_date = date.today()
    else:
        start_date = date.today()
        
    date_list = [start_date + timedelta(days=i) for i in range(7)]
    date_strs = [d.strftime('%Y-%m-%d') for d in date_list]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    where_rt = "WHERE is_active = 1"
    params_rt = []
    if hotel_id:
        where_rt += " AND hotel_id = ?"
        params_rt.append(hotel_id)
        
    cursor.execute(f"SELECT * FROM Dim_RoomType {where_rt} ORDER BY room_type_code", params_rt)
    room_types = [dict(r) for r in cursor.fetchall()]
    
    for rt in room_types:
        rt_code = rt['room_type_code']
        base_price = rt['base_price']
        
        # 2. Lấy giá theo ngày (Room_Rates) - chỉ lấy loại phòng chung (physical_room_id IS NULL)
        placeholders = ','.join(['?'] * len(date_strs))
        cursor.execute(f"""
            SELECT valid_date, base_price, is_holiday 
            FROM Room_Rates 
            WHERE room_type_code = ? AND valid_date IN ({placeholders})
            AND (physical_room_id IS NULL)
        """, [rt_code] + date_strs)
        
        rates_map = {r['valid_date']: dict(r) for r in cursor.fetchall()}
        
        weekly_prices = []
        for d_str in date_strs:
            if d_str in rates_map:
                rate = rates_map[d_str]
                weekly_prices.append({
                    'date': d_str,
                    'price': rate['base_price'],
                    'is_holiday': rate['is_holiday']
                })
            else:
                weekly_prices.append({
                    'date': d_str,
                    'price': base_price,
                    'is_holiday': 0
                })
        rt['weekly_prices'] = weekly_prices
        print(f'>>> ADDED weekly_prices TO {rt_code}: {len(weekly_prices)}')
        
        # 3. Lấy danh sách phòng thực tế
        where_pr = "WHERE room_type_id = ?"
        params_pr = [rt['room_type_id']]
        if room_name_search:
            where_pr += " AND room_name LIKE ?"
            params_pr.append(f"%{room_name_search}%")
            
        cursor.execute(f"SELECT * FROM Physical_Room {where_pr} ORDER BY room_name", params_pr)
        physical_rooms = [dict(r) for r in cursor.fetchall()]
        
        for pr in physical_rooms:
            pr_id = pr['physical_room_id']
            # Lấy bảng giá ghi đè cho từng phòng cụ thể
            cursor.execute(f"""
                SELECT valid_date, base_price, is_holiday 
                FROM Room_Rates 
                WHERE physical_room_id = ? AND valid_date IN ({placeholders})
            """, [pr_id] + date_strs)
            pr_rates_map = {r['valid_date']: dict(r) for r in cursor.fetchall()}
            
            pr_weekly_prices = []
            for d_str in date_strs:
                if d_str in pr_rates_map:
                    # Hạng 1: Ghi đè theo phòng vật lý
                    rate = pr_rates_map[d_str]
                    pr_weekly_prices.append({
                        'date': d_str,
                        'price': rate['base_price'],
                        'is_holiday': rate['is_holiday']
                    })
                elif d_str in rates_map:
                    # Hạng 2: Ghi đè theo loại phòng
                    rate = rates_map[d_str]
                    pr_weekly_prices.append({
                        'date': d_str,
                        'price': rate['base_price'],
                        'is_holiday': rate['is_holiday']
                    })
                else:
                    # Hạng 3: Giá gốc
                    pr_weekly_prices.append({
                        'date': d_str,
                        'price': base_price,
                        'is_holiday': 0
                    })
            pr['weekly_prices'] = pr_weekly_prices
            
        rt['physical_rooms'] = physical_rooms
        
    conn.close()
    return jsonify({
        'success': True, 
        'inventory': room_types,
        'dates': date_strs
    })

@manager_bp.route('/api/dimensions/room-types', methods=['GET'])
def api_get_room_types():
    hotel_id = request.args.get('hotel_id', type=int)
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM Dim_RoomType WHERE is_active = 1"
    params = []
    if hotel_id:
        query += " AND hotel_id = ?"
        params.append(hotel_id)
    cursor.execute(query, params)
    room_types = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'room_types': room_types})



@manager_bp.route('/api/physical-rooms/bulk-delete', methods=['POST'])
def api_bulk_delete_rooms():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    room_ids = data.get('room_ids', [])
    if not room_ids:
        return jsonify({'success': False, 'message': 'Khong co phong de xoa'}), 400
    conn = get_db_connection()
    placeholders = ','.join(['?'] * len(room_ids))
    conn.execute(f"UPDATE Physical_Room SET is_active = 0 WHERE physical_room_id IN ({placeholders})", room_ids)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Da an {len(room_ids)} phong (soft-delete)'})


# ─── PHYSICAL ROOM DETAIL CRUD ───────────────────────────────────────────────

import json as _json
import os as _os
import uuid as _uuid

_UPLOAD_DIR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..', 'FrontEnd', 'static', 'uploads', 'rooms'))
_MAX_IMAGES = 8
_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
_ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in _ALLOWED_EXT


@manager_bp.route('/api/room-detail/<int:pr_id>', methods=['GET', 'PUT', 'DELETE'])
def api_physical_room_detail(pr_id):
    """GET/PUT/DELETE cho phòng thực tế."""

    # ── GET: chi tiết 1 phòng ──
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pr.*, drt.room_type_code, drt.base_price, drt.max_adults, drt.max_children,
                   drt.description AS rt_description, drt.amenities AS rt_amenities,
                   dh.hotel AS hotel_name
            FROM Physical_Room pr
            JOIN Dim_RoomType drt ON pr.room_type_id = drt.room_type_id
            LEFT JOIN Dim_Hotel dh ON drt.hotel_id = dh.hotel_id
            WHERE pr.physical_room_id = ?
        """, (pr_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return jsonify({'success': False, 'message': 'Khong tim thay phong'}), 404
        room = dict(row)
        try:
            room['images'] = _json.loads(room.get('images') or '[]')
        except Exception:
            room['images'] = []
        return jsonify({'success': True, 'room': room})

    # ── DELETE: soft-delete ──
    if request.method == 'DELETE':
        auth_err = require_token()
        if auth_err is not None:
            return auth_err
        caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
        if caller_role not in ('Manager', 'Admin'):
            return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
        conn = get_db_connection()
        conn.execute("UPDATE Physical_Room SET is_active = 0 WHERE physical_room_id = ?", (pr_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Da an phong (soft-delete)'})

    # ── PUT: cập nhật thông tin ──
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    conn = get_db_connection()

    sets = []
    params = []
    for field in ['room_name', 'description', 'amenities', 'housekeeping_status']:
        if field in data:
            sets.append(f"{field} = ?")
            params.append(data[field])
    if 'is_active' in data:
        sets.append("is_active = ?")
        params.append(1 if data['is_active'] else 0)
    if 'room_type_id' in data:
        sets.append("room_type_id = ?")
        params.append(data['room_type_id'])

    if not sets:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong co truong nao de cap nhat'}), 400

    params.append(pr_id)
    conn.execute(f"UPDATE Physical_Room SET {', '.join(sets)} WHERE physical_room_id = ?", params)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cap nhat phong thanh cong'})


@manager_bp.route('/api/room-detail/<int:pr_id>/upload-image', methods=['POST'])
def api_upload_physical_room_image(pr_id):
    """Upload ảnh cho phòng thực tế."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'Khong co file anh'}), 400
    file = request.files['image']
    if not file.filename or not _allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Dinh dang file khong hop le (JPG/PNG/WebP)'}), 400

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > _MAX_FILE_SIZE:
        return jsonify({'success': False, 'message': 'File qua lon (toi da 5MB)'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT images FROM Physical_Room WHERE physical_room_id = ?", (pr_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay phong'}), 404

    try:
        current_images = _json.loads(row['images'] or '[]')
    except Exception:
        current_images = []

    if len(current_images) >= _MAX_IMAGES:
        conn.close()
        return jsonify({'success': False, 'message': f'Toi da {_MAX_IMAGES} anh'}), 400

    _os.makedirs(_UPLOAD_DIR, exist_ok=True)
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f"pr_{pr_id}_{_uuid.uuid4().hex[:8]}.{ext}"
    filepath = _os.path.join(_UPLOAD_DIR, unique_name)
    file.save(filepath)

    web_path = f"/static/uploads/rooms/{unique_name}"
    current_images.append(web_path)

    cursor.execute("UPDATE Physical_Room SET images = ? WHERE physical_room_id = ?",
                   (_json.dumps(current_images, ensure_ascii=False), pr_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'image_url': web_path, 'images': current_images})


@manager_bp.route('/api/room-detail/<int:pr_id>/delete-image', methods=['POST'])
def api_delete_physical_room_image(pr_id):
    """Xóa 1 ảnh cụ thể khỏi phòng thực tế."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    data = request.get_json() or {}
    image_url = data.get('image_url', '').strip()
    if not image_url:
        return jsonify({'success': False, 'message': 'Thieu image_url'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT images FROM Physical_Room WHERE physical_room_id = ?", (pr_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay phong'}), 404

    try:
        current_images = _json.loads(row['images'] or '[]')
    except Exception:
        current_images = []

    if image_url not in current_images:
        conn.close()
        return jsonify({'success': False, 'message': 'Anh khong ton tai trong danh sach'}), 404

    current_images.remove(image_url)
    cursor.execute("UPDATE Physical_Room SET images = ? WHERE physical_room_id = ?",
                   (_json.dumps(current_images, ensure_ascii=False), pr_id))
    conn.commit()
    conn.close()

    if image_url.startswith('/static/uploads/rooms/'):
        disk_path = _os.path.join(_UPLOAD_DIR, _os.path.basename(image_url))
        if _os.path.exists(disk_path):
            try:
                _os.remove(disk_path)
            except Exception:
                pass

    return jsonify({'success': True, 'images': current_images})


# ─── ROOM TYPE IMAGE MANAGEMENT ──────────────────────────────────────────────

@manager_bp.route('/api/room-types/<int:room_type_id>/upload-image', methods=['POST'])
def api_upload_room_image(room_type_id):
    """Upload ảnh cho loại phòng. Nhận multipart/form-data."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'Khong co file anh'}), 400
    file = request.files['image']
    if not file.filename or not _allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Dinh dang file khong hop le (JPG/PNG/WebP)'}), 400

    # Check file size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > _MAX_FILE_SIZE:
        return jsonify({'success': False, 'message': 'File qua lon (toi da 5MB)'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT images FROM Dim_RoomType WHERE room_type_id = ?", (room_type_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay loai phong'}), 404

    try:
        current_images = _json.loads(row['images'] or '[]')
    except Exception:
        current_images = []

    if len(current_images) >= _MAX_IMAGES:
        conn.close()
        return jsonify({'success': False, 'message': f'Toi da {_MAX_IMAGES} anh'}), 400

    # Save file
    _os.makedirs(_UPLOAD_DIR, exist_ok=True)
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{room_type_id}_{_uuid.uuid4().hex[:8]}.{ext}"
    filepath = _os.path.join(_UPLOAD_DIR, unique_name)
    file.save(filepath)

    web_path = f"/static/uploads/rooms/{unique_name}"
    current_images.append(web_path)

    cursor.execute("UPDATE Dim_RoomType SET images = ? WHERE room_type_id = ?",
                   (_json.dumps(current_images, ensure_ascii=False), room_type_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'image_url': web_path, 'images': current_images})


@manager_bp.route('/api/room-types/<int:room_type_id>/delete-image', methods=['POST'])
def api_delete_room_image(room_type_id):
    """Xóa 1 ảnh cụ thể khỏi loại phòng."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    data = request.get_json() or {}
    image_url = data.get('image_url', '').strip()
    if not image_url:
        return jsonify({'success': False, 'message': 'Thieu image_url'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT images FROM Dim_RoomType WHERE room_type_id = ?", (room_type_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay loai phong'}), 404

    try:
        current_images = _json.loads(row['images'] or '[]')
    except Exception:
        current_images = []

    if image_url not in current_images:
        conn.close()
        return jsonify({'success': False, 'message': 'Anh khong ton tai trong danh sach'}), 404

    current_images.remove(image_url)
    cursor.execute("UPDATE Dim_RoomType SET images = ? WHERE room_type_id = ?",
                   (_json.dumps(current_images, ensure_ascii=False), room_type_id))
    conn.commit()
    conn.close()

    # Delete file from disk
    if image_url.startswith('/static/uploads/rooms/'):
        disk_path = _os.path.join(_UPLOAD_DIR, _os.path.basename(image_url))
        if _os.path.exists(disk_path):
            try:
                _os.remove(disk_path)
            except Exception:
                pass

    return jsonify({'success': True, 'images': current_images})


# ─── UPDATED PRICING ENDPOINTS ───────────────────────────────────────────────

@manager_bp.route('/api/room-rates', methods=['GET'])
def api_get_room_rates():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if role not in ('Manager', 'Admin', 'Receptionist'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    room_type_code = request.args.get('room_type_code', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    where_clause = "WHERE 1=1"
    query_params = []
    if room_type_code:
        where_clause += " AND room_type_code = ?"
        query_params.append(room_type_code)
    if start_date:
        where_clause += " AND valid_date >= ?"
        query_params.append(start_date)
    if end_date:
        where_clause += " AND valid_date <= ?"
        query_params.append(end_date)
    cursor.execute(
        f"SELECT rate_id, room_type_code, valid_date, base_price, is_holiday FROM Room_Rates {where_clause} ORDER BY valid_date LIMIT 365",
        query_params,
    )
    rates = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'rates': rates})


@manager_bp.route('/api/room-rates/comprehensive', methods=['POST'])
def api_apply_flexible_pricing():
    """Áp dụng giá linh hoạt: Hạng phòng, Nhóm phòng, hoặc Phòng đơn lẻ."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    if get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff') not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    mode = data.get('mode') # 'type', 'group', 'single'
    target_id = data.get('target_id') # room_type_code if 'type', item_id if 'single'
    room_ids = data.get('room_ids', []) # list of physical_room_id if 'group'
    
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    base_price = data.get('new_price')
    is_holiday = data.get('is_holiday', 0)
    
    if not all([start_date, end_date, base_price]):
        return jsonify({'success': False, 'message': 'Thieu thong tin gia hoac ngay'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    targets = []
    if mode == 'type':
        # target_id can be room_type_code (string) or room_type_id (numeric)
        # We need the code for the DB
        cursor.execute("SELECT room_type_code FROM Dim_RoomType WHERE room_type_code = ? OR room_type_id = ?", (target_id, target_id))
        row = cursor.fetchone()
        if row:
            targets.append({'type_code': row['room_type_code'], 'room_id': None})
        else:
            conn.close()
            return jsonify({'success': False, 'message': f'Loại phòng không hợp lệ: {target_id}'}), 400
    elif mode == 'single' or mode == 'room': # 'room' for compat with some templates
        # target_id is physical_room_id.
        cursor.execute("SELECT drt.room_type_code FROM Physical_Room pr JOIN Dim_RoomType drt ON pr.room_type_id = drt.room_type_id WHERE pr.physical_room_id = ?", (target_id,))
        row = cursor.fetchone()
        if row: 
            targets.append({'type_code': row['room_type_code'], 'room_id': target_id})
        else:
            conn.close()
            return jsonify({'success': False, 'message': f'Phòng không hợp lệ: {target_id}'}), 400
    elif mode == 'group':
        for rid in room_ids:
            cursor.execute("SELECT drt.room_type_code FROM Physical_Room pr JOIN Dim_RoomType drt ON pr.room_type_id = drt.room_type_id WHERE pr.physical_room_id = ?", (rid,))
            row = cursor.fetchone()
            if row: targets.append({'type_code': row['room_type_code'], 'room_id': rid})

    for t in targets:
        curr = start_dt
        while curr <= end_dt:
            d_str = curr.strftime('%Y-%m-%d')
            # Calculate base_price_cents for consistency
            base_price_cents = int(float(base_price) * 100)
            
            # Use DELETE then INSERT to avoid NULL conflict issues with UPSERT
            if t['room_id'] is None:
                cursor.execute("DELETE FROM Room_Rates WHERE room_type_code = ? AND valid_date = ? AND physical_room_id IS NULL", (t['type_code'], d_str))
            else:
                cursor.execute("DELETE FROM Room_Rates WHERE room_type_code = ? AND valid_date = ? AND physical_room_id = ?", (t['type_code'], d_str, t['room_id']))
                
            cursor.execute("""
                INSERT INTO Room_Rates (room_type_code, physical_room_id, valid_date, base_price, base_price_cents, is_holiday)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (t['type_code'], t['room_id'], d_str, base_price, base_price_cents, is_holiday))
            curr += timedelta(days=1)
            
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cập nhật giá thành công (Dữ liệu đã được đồng bộ)'})


# ─── PROMOTIONS ENDPOINTS ─────────────────────────────────────────────────────

@manager_bp.route('/api/promotions', methods=['GET'])
def api_get_promotions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT promotion_id AS promo_id, code AS promo_code, discount_percent, discount_type,
               start_date, end_date, description, active AS is_active, apply_scope, scope_value
        FROM Promotions ORDER BY promotion_id DESC
    """)
    promotions_list = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'promotions': promotions_list})


@manager_bp.route('/api/promotions', methods=['POST'])
def api_create_promotion():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_user_id = g.api_user_id
    caller_role = get_user_role_from_db(caller_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    promo_code = data.get('promo_code', '').strip().upper()
    discount_percent = data.get('discount_percent', 0)
    discount_type = data.get('discount_type', 'percent')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    description = data.get('description', '')
    apply_scope = data.get('apply_scope', 'all')
    scope_value = data.get('scope_value', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO Promotions (code, discount_percent, discount_type, start_date, end_date,
                                   description, apply_scope, scope_value, active, created_by_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (promo_code, discount_percent, discount_type, start_date, end_date,
              description, apply_scope, scope_value, caller_user_id))
        new_promo_id = cursor.lastrowid
        conn.commit()
        invalidate_pricing_caches()
        return jsonify({'success': True, 'promo_id': new_promo_id})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Ma khuyen mai da ton tai'}), 409
    finally:
        conn.close()


@manager_bp.route('/api/promotions/<int:promo_id>', methods=['PUT'])
def api_update_promotion(promo_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    conn = get_db_connection()
    conn.execute("""
        UPDATE Promotions SET discount_percent = ?, discount_type = ?, start_date = ?,
               end_date = ?, description = ?, apply_scope = ?, scope_value = ?, active = ?
        WHERE promotion_id = ?
    """, (data.get('discount_percent'), data.get('discount_type', 'percent'),
          data.get('start_date'), data.get('end_date'), data.get('description', ''),
          data.get('apply_scope', 'all'), data.get('scope_value', ''),
          1 if data.get('is_active', 1) else 0, promo_id))
    conn.commit()
    conn.close()
    invalidate_pricing_caches()
    return jsonify({'success': True, 'message': 'Cap nhat thanh cong'})


@manager_bp.route('/api/promotions/<int:promo_id>', methods=['DELETE'])
def api_delete_promotion(promo_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    conn = get_db_connection()
    conn.execute("DELETE FROM Promotions WHERE promotion_id = ?", (promo_id,))
    conn.commit()
    conn.close()
    invalidate_pricing_caches()
    return jsonify({'success': True, 'message': 'Xoa thanh cong'})


@manager_bp.route('/api/promotions/validate', methods=['POST'])
def api_validate_promotion():
    """Kiem tra ma khuyen mai co hop le va con hieu luc khong."""
    data = request.get_json()
    promo_code = data.get('promo_code', '').strip().upper()
    checkin_date_str = data.get('checkin_date', date.today().strftime('%Y-%m-%d'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT code AS promo_code, discount_percent, discount_type, apply_scope, description
        FROM Promotions
        WHERE code = ? AND active = 1
          AND (start_date IS NULL OR start_date <= ?)
          AND (end_date IS NULL OR end_date >= ?)
    """, (promo_code, checkin_date_str, checkin_date_str))
    promo_row = cursor.fetchone()
    conn.close()
    if promo_row:
        return jsonify({'success': True, 'valid': True, 'promo': dict(promo_row)})
    return jsonify({'success': True, 'valid': False, 'message': 'Ma khong hop le hoac het han'})


# ─── ANALYTICS ENDPOINTS ─────────────────────────────────────────────────────

@manager_bp.route('/api/analytics/summary', methods=['GET'])
def api_analytics_summary():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin', 'Receptionist'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    # Kiểm tra cache trước khi query DB nặng
    cache_key = 'analytics_summary'
    cached = _get_cached(cache_key)
    if cached:
        return jsonify(cached)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Global Summary
    cursor.execute("""
        SELECT COUNT(*) as total_bookings,
               SUM(CASE WHEN is_canceled = 1 THEN 1 ELSE 0 END) as total_canceled,
               ROUND(AVG(total_price / NULLIF(nights, 0)), 2) as avg_daily_rate
        FROM New_Bookings
    """)
    row = cursor.fetchone()
    total = row['total_bookings'] or 0
    canceled = row['total_canceled'] or 0
    summary = {
        'total_bookings': total,
        'total_canceled': canceled,
        'cancel_rate': round(100.0 * canceled / total, 2) if total > 0 else 0,
        'avg_daily_rate': row['avg_daily_rate'] or 0
    }

    # 2. By Hotel
    cursor.execute("""
        SELECT dh.hotel AS hotel_name, COUNT(*) as total_bookings,
               ROUND(AVG(nb.total_price / NULLIF(nb.nights, 0)), 2) as avg_adr
        FROM New_Bookings nb
        JOIN Dim_Hotel dh ON nb.hotel_id = dh.hotel_id
        GROUP BY dh.hotel
    """)
    by_hotel = [dict(r) for r in cursor.fetchall()]

    # 3. By Segment (Placeholder, as market_segment info is not in New_Bookings yet)
    # Returning empty list as expected by frontend
    by_segment = []

    conn.close()
    result = {
        'success': True,
        'summary': summary,
        'by_hotel': by_hotel,
        'by_segment': by_segment
    }
    _set_cached(cache_key, result)
    return jsonify(result)


@manager_bp.route('/api/analytics/monthly', methods=['GET'])
def api_analytics_monthly():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin', 'Receptionist'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    year = request.args.get('year', 2025, type=int)
    conn = get_db_connection()
    cursor = conn.cursor()

    # Mapping numeric month to name in SQL via a CASE (since strftime returns numbers)
    cursor.execute("""
        SELECT strftime('%m', arrival_date) as month_num,
               COUNT(*) as total_bookings,
               SUM(CASE WHEN is_canceled = 1 THEN 1 ELSE 0 END) as canceled,
               ROUND(AVG(total_price / NULLIF(nights, 0)), 2) as avg_adr
        FROM New_Bookings
        WHERE strftime('%Y', arrival_date) = ?
        GROUP BY month_num
        ORDER BY month_num
    """, (str(year),))
    
    rows = cursor.fetchall()
    
    month_names = {
        '01': 'January', '02': 'February', '03': 'March', '04': 'April',
        '05': 'May', '06': 'June', '07': 'July', '08': 'August',
        '09': 'September', '10': 'October', '11': 'November', '12': 'December'
    }
    
    monthly_data = []
    for r in rows:
        monthly_data.append({
            'month_num': int(r['month_num']),
            'month_name': month_names.get(r['month_num'], 'Unknown'),
            'total_bookings': r['total_bookings'],
            'canceled': r['canceled'],
            'avg_adr': r['avg_adr'] or 0
        })

    conn.close()
    return jsonify({'success': True, 'year': year, 'monthly_data': monthly_data})


@manager_bp.route('/api/analytics/advanced', methods=['GET'])
def api_analytics_advanced():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    group_by = request.args.get('group_by', 'month') # day, week, month, quarter, year
    year_filter = request.args.get('year', datetime.now().year, type=int)
    hotel_id = request.args.get('hotel_id', type=int)

    # Kiểm tra cache
    cache_key = f'analytics_advanced_{group_by}_{year_filter}_{hotel_id}'
    cached = _get_cached(cache_key)
    if cached:
        return jsonify(cached)

    # SQL logic for grouping (using arrival_date as base)
    if group_by == 'day':
        sql_group = "arrival_date"
    elif group_by == 'week':
        sql_group = "strftime('%Y-W%W', arrival_date)"
    elif group_by == 'quarter':
        sql_group = "strftime('%Y', arrival_date) || '-Q' || ((CAST(strftime('%m', arrival_date) AS INT) + 2) / 3)"
    elif group_by == 'year':
        sql_group = "strftime('%Y', arrival_date)"
    else: # month
        sql_group = "strftime('%Y-%m', arrival_date)"

    where_clause = "WHERE arrival_date_year = ?"
    params = [year_filter]
    if hotel_id:
        where_clause += " AND hotel_id = ?"
        params.append(hotel_id)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = f"""
        SELECT {sql_group} as time_label,
               COUNT(*) as total_bookings,
               SUM(CASE WHEN is_canceled = 1 THEN 1 ELSE 0 END) as total_canceled,
               ROUND(AVG(total_price / nights), 2) as avg_adr,
               SUM(total_price) as revenue
        FROM New_Bookings
        {where_clause.replace('arrival_date_year', "strftime('%Y', arrival_date)")}
        GROUP BY time_label
        ORDER BY time_label ASC
    """
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    data = [dict(r) for r in rows]
    conn.close()
    
    result = {'success': True, 'data': data, 'group_by': group_by}
    _set_cached(cache_key, result)
    return jsonify(result)


@manager_bp.route('/api/analytics/conversion', methods=['GET'])
def api_analytics_conversion():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    days = request.args.get('days', 30, type=int)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT event_name, COUNT(*) as cnt
        FROM Funnel_Events
        WHERE created_at >= datetime('now', ?)
        GROUP BY event_name
    """, (f'-{max(1, days)} days',))
    stats = {r['event_name']: r['cnt'] for r in cursor.fetchall()}
    search_cnt = stats.get('search_performed', 0)
    add_cart_cnt = stats.get('add_to_cart', 0)
    checkout_success_cnt = stats.get('checkout_success', 0)
    booking_success_cnt = stats.get('booking_success', 0)
    conn.close()
    return jsonify({
        'success': True,
        'days': days,
        'counts': {
            'search': search_cnt,
            'add_to_cart': add_cart_cnt,
            'checkout_success': checkout_success_cnt,
            'booking_success': booking_success_cnt,
        },
        'rates': {
            'search_to_cart': round(100 * add_cart_cnt / search_cnt, 2) if search_cnt else 0,
            'search_to_checkout': round(100 * checkout_success_cnt / search_cnt, 2) if search_cnt else 0,
            'search_to_booking': round(100 * booking_success_cnt / search_cnt, 2) if search_cnt else 0,
        }
    })


@manager_bp.route('/api/operations/realtime', methods=['GET'])
def api_operations_realtime():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if role not in ('Manager', 'Admin', 'Receptionist'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM New_Bookings WHERE arrival_date = ? AND status_detail = 'Confirmed'", (today,))
    checkins_due = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM New_Bookings WHERE departure_date = ? AND status_detail = 'Checked-In'", (today,))
    checkouts_due = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM Physical_Room WHERE housekeeping_status = 'Dirty'")
    dirty_rooms = cursor.fetchone()['c']
    cursor.execute("SELECT COUNT(*) as c FROM Physical_Room WHERE housekeeping_status = 'Maintenance'")
    maintenance_rooms = cursor.fetchone()['c']
    conn.close()
    return jsonify({
        'success': True,
        'today': today,
        'checkins_due': checkins_due,
        'checkouts_due': checkouts_due,
        'dirty_rooms': dirty_rooms,
        'maintenance_rooms': maintenance_rooms,
    })


# ─── LOYALTY ENDPOINTS ───────────────────────────────────────────────────────

@manager_bp.route('/api/loyalty/<int:user_id>', methods=['GET'])
def api_get_loyalty(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT account_id as user_id, email as username, customer_name as full_name,
               loyalty_points as points, membership_tier as tier, (loyalty_points / 10) as total_nights
        FROM Customer_Accounts WHERE account_id = ?
    """, (user_id,))
    loyalty_row = cursor.fetchone()
    conn.close()
    if loyalty_row:
        return jsonify({'success': True, 'loyalty': dict(loyalty_row)})
    return jsonify({'success': False, 'message': 'Khong tim thay'}), 404


# ─── REVIEWS ENDPOINTS ───────────────────────────────────────────────────────

@manager_bp.route('/api/reviews', methods=['GET'])
def api_get_reviews():
    hotel_id = request.args.get('hotel_id', type=int)
    conn = get_db_connection()
    cursor = conn.cursor()
    where_clause = "WHERE 1=1"
    query_params = []
    if hotel_id:
        where_clause += " AND r.hotel_id = ?"
        query_params.append(hotel_id)
    cursor.execute(f"""
        SELECT r.review_id, r.hotel_id, dh.hotel AS hotel_name,
               r.user_id, COALESCE(ca.customer_name, 'Khach hang') as username,
               r.booking_id, r.rating, r.comment, r.review_date
        FROM Reviews r
        LEFT JOIN Customer_Accounts ca ON r.user_id = ca.account_id
        LEFT JOIN Dim_Hotel dh ON r.hotel_id = dh.hotel_id
        {where_clause} ORDER BY r.review_date DESC LIMIT 100
    """, query_params)
    reviews_list = [dict(r) for r in cursor.fetchall()]
    avg_rating = None
    if hotel_id:
        cursor.execute("SELECT ROUND(AVG(rating), 2) as avg_rating FROM Reviews WHERE hotel_id = ?", (hotel_id,))
        avg_row = cursor.fetchone()
        avg_rating = avg_row['avg_rating'] if avg_row else None
    conn.close()
    return jsonify({'success': True, 'reviews': reviews_list, 'avg_rating': avg_rating})


@manager_bp.route('/api/reviews', methods=['POST'])
def api_create_review():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    if (g.api_account_type or '') != 'customer':
        return jsonify({'success': False, 'message': 'Chi khach hang danh gia'}), 403
    user_id = g.api_user_id
    data = request.get_json()
    hotel_id = data.get('hotel_id')
    booking_id = data.get('booking_id')
    rating = data.get('rating')
    comment = data.get('comment', '')
    if not all([user_id, hotel_id, booking_id, rating]):
        return jsonify({'success': False, 'message': 'Thieu thong tin'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM New_Bookings WHERE booking_id = ? AND user_id = ? AND status_detail = 'Checked-Out'", (booking_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Chi co the danh gia sau khi da luu tru'}), 403
    cursor.execute("SELECT 1 FROM Reviews WHERE booking_id = ? AND user_id = ?", (booking_id, user_id))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Ban da danh gia roi'}), 409
    cursor.execute("""
        INSERT INTO Reviews (user_id, hotel_id, booking_id, rating, comment, review_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, hotel_id, booking_id, rating, comment, datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Gui danh gia thanh cong'})


