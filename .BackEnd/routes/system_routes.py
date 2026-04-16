from flask import Blueprint, request, jsonify, g
import sqlite3
import os
import json
from database import get_db_connection
from datetime import datetime
from services.api_auth import require_token
from services.booking_service import get_user_role_from_db, cleanup_expired_locks, timedelta

system_bp = Blueprint('system_bp', __name__)

def invalidate_pricing_caches():
    """Dummy function to avoid NameError if no local cache is defined yet."""
    pass
@system_bp.route('/api/funnel/event', methods=['POST'])
def api_track_funnel_event():
    """Track hành vi conversion funnel (cho cả user chưa login)."""
    data = request.get_json() or {}
    event_name = (data.get('event_name') or '').strip()
    if not event_name:
        return jsonify({'success': False, 'message': 'Missing event_name'}), 400
    session_id = (data.get('session_id') or '').strip()
    source_channel = (data.get('source_channel') or 'direct').strip() or 'direct'
    utm_campaign = (data.get('utm_campaign') or '').strip()
    utm_medium = (data.get('utm_medium') or '').strip()
    user_id = getattr(g, 'api_user_id', None)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Funnel_Events
            (session_id, user_id, event_name, hotel_id, room_type_id, booking_id, metadata_json, source_channel, utm_campaign, utm_medium)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        user_id,
        event_name,
        data.get('hotel_id'),
        data.get('room_type_id'),
        data.get('booking_id'),
        json.dumps(data.get('metadata', {}), ensure_ascii=False),
        source_channel,
        utm_campaign,
        utm_medium,
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})



# ─── DIMENSION MANAGEMENT ENDPOINTS ──────────────────────────────────────────

@system_bp.route('/api/hotels', methods=['GET'])
def api_get_hotels():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT hotel_id, hotel AS hotel_name,
               COALESCE(star_rating, 3) AS star_rating,
               COALESCE(hotel_type, 'City Hotel') AS hotel_type
        FROM Dim_Hotel ORDER BY hotel
    """)
    hotels_list = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'hotels': hotels_list})


@system_bp.route('/api/dimensions/hotels', methods=['GET'])
def api_get_hotels_dim():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT hotel_id, hotel AS hotel_name FROM Dim_Hotel ORDER BY hotel_id")
    hotels_list = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'hotels': hotels_list})


@system_bp.route('/api/dimensions/room-types', methods=['GET'])
def api_get_room_types_dim():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT drt.room_type_id, drt.room_type_code, drt.max_adults, drt.max_children,
               drt.base_price, drt.description, drt.amenities, drt.is_active, drt.hotel_id,
               COALESCE(drt.allow_child_sharing, 1) AS allow_child_sharing,
               COALESCE(drt.extra_bed_capacity, 0) AS extra_bed_capacity,
               COALESCE(drt.extra_adult_fee, 0.0) AS extra_adult_fee,
               COALESCE(drt.child_breakfast_fee, 0.0) AS child_breakfast_fee,
               drt.main_image, drt.images,
               dh.hotel as hotel_name
        FROM Dim_RoomType drt
        LEFT JOIN Dim_Hotel dh ON drt.hotel_id = dh.hotel_id
        ORDER BY drt.room_type_code
    """)
    room_types_list = []
    import json
    for r in cursor.fetchall():
        rd = dict(r)
        try:
            rd['images'] = json.loads(rd.get('images') or '[]')
        except:
            rd['images'] = []
        room_types_list.append(rd)
    conn.close()
    return jsonify({'success': True, 'room_types': room_types_list})


@system_bp.route('/api/dimensions/room-types', methods=['POST'])
def api_create_room_type():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role != 'Admin':
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    room_type_code = data.get('room_type_code', '').strip().upper()
    hotel_id = data.get('hotel_id', 1)
    max_adults = data.get('max_adults', 2)
    max_children = data.get('max_children', 1)
    base_price = data.get('base_price', 100.0)
    allow_child_sharing = 1 if data.get('allow_child_sharing', 1) else 0
    extra_bed_capacity = data.get('extra_bed_capacity', 0)
    extra_adult_fee = data.get('extra_adult_fee', 0.0)
    child_breakfast_fee = data.get('child_breakfast_fee', 0.0)
    description = data.get('description', '')
    amenities = data.get('amenities', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT room_type_id FROM Dim_RoomType WHERE room_type_code = ? AND hotel_id = ?", (room_type_code, hotel_id))
        if cursor.fetchone():
            raise ValueError("Ký hiệu mã loại phòng này đã tồn tại trong cùng khách sạn đó.")
            
        cursor.execute("""
            INSERT INTO Dim_RoomType (
                room_type_code, hotel_id, max_adults, max_children, base_price, description, amenities, is_active,
                allow_child_sharing, extra_bed_capacity, extra_adult_fee, child_breakfast_fee
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """, (
            room_type_code, hotel_id, max_adults, max_children, base_price, description, amenities,
            allow_child_sharing, extra_bed_capacity, extra_adult_fee, child_breakfast_fee
        ))
        conn.commit()
        invalidate_pricing_caches()
        return jsonify({'success': True, 'room_type_id': cursor.lastrowid})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Loai phong da ton tai'}), 409
    finally:
        conn.close()


@system_bp.route('/api/dimensions/room-types/<int:room_type_id>', methods=['GET'])
def api_get_single_room_type(room_type_id):
    """Trả về chi tiết 1 loại phòng (bao gồm images)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT drt.*, dh.hotel as hotel_name
        FROM Dim_RoomType drt
        LEFT JOIN Dim_Hotel dh ON drt.hotel_id = dh.hotel_id
        WHERE drt.room_type_id = ?
    """, (room_type_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'success': False, 'message': 'Khong tim thay loai phong'}), 404
    rt = dict(row)
    # Parse images JSON
    try:
        rt['images'] = json.loads(rt.get('images') or '[]')
    except Exception:
        rt['images'] = []
    return jsonify({'success': True, 'room_type': rt})


@system_bp.route('/api/dimensions/room-types/<int:room_type_id>', methods=['PUT'])
def api_update_room_type(room_type_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Admin', 'Manager'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    conn = get_db_connection()
    # Build images JSON if provided
    images_json = None
    if 'images' in data:
        images_json = json.dumps(data['images'], ensure_ascii=False) if isinstance(data['images'], list) else data['images']
    sql = """
        UPDATE Dim_RoomType SET room_type_code = ?, hotel_id = ?, max_adults = ?, max_children = ?,
               base_price = ?, description = ?, amenities = ?, is_active = ?,
               allow_child_sharing = ?, extra_bed_capacity = ?, extra_adult_fee = ?, child_breakfast_fee = ?
    """
    params = [
        data.get('room_type_code', '').strip().upper(), data.get('hotel_id', 1), data.get('max_adults', 2),
        data.get('max_children', 1), data.get('base_price', 100.0),
        data.get('description', ''), data.get('amenities', ''),
        1 if data.get('is_active', 1) else 0,
        1 if data.get('allow_child_sharing', 1) else 0,
        data.get('extra_bed_capacity', 0),
        data.get('extra_adult_fee', 0.0),
        data.get('child_breakfast_fee', 0.0),
    ]
    if images_json is not None:
        sql += ", images = ?"
        params.append(images_json)
    sql += " WHERE room_type_id = ?"
    params.append(room_type_id)
    conn.execute(sql, params)
    conn.commit()
    conn.close()
    invalidate_pricing_caches()
    return jsonify({'success': True, 'message': 'Cap nhat thanh cong'})


@system_bp.route('/api/dimensions/room-types/<int:room_type_id>', methods=['DELETE'])
def api_delete_room_type(room_type_id):
    """Soft delete: vo hieu hoa loai phong thay vi xoa cung."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role != 'Admin':
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM New_Bookings WHERE room_type_id = ?", (room_type_id,))
    has_bookings = cursor.fetchone()['cnt'] > 0
    if has_bookings:
        cursor.execute("UPDATE Dim_RoomType SET is_active = 0 WHERE room_type_id = ?", (room_type_id,))
        conn.commit()
        conn.close()
        invalidate_pricing_caches()
        return jsonify({'success': True, 'message': 'Da vo hieu hoa loai phong (co lich su dat phong)'})
    cursor.execute("DELETE FROM Dim_RoomType WHERE room_type_id = ?", (room_type_id,))
    conn.commit()
    conn.close()
    invalidate_pricing_caches()
    return jsonify({'success': True, 'message': 'Xoa loai phong thanh cong'})


@system_bp.route('/api/dimensions/market-segments', methods=['GET'])
def api_get_market_segments():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT segment_id AS market_segment_id, market_segment AS segment_name FROM Dim_MarketSegment ORDER BY market_segment")
    segments_list = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'segments': segments_list})


# ─── CUSTOMER INFO ENDPOINTS ─────────────────────────────────────────────────

@system_bp.route('/api/customer-info/by-email', methods=['GET'])
def api_get_customer_by_email():
    """Tim kiem thong tin khach hang bang email (cho le tan su dung)."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    customer_email = request.args.get('email', '').strip()
    if not customer_email:
        return jsonify({'success': False, 'message': 'Vui long nhap email'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT account_id as user_id, email, customer_name as full_name,
               loyalty_points as points, membership_tier as tier,
               (loyalty_points / 10) as total_nights
        FROM Customer_Accounts WHERE email = ?
    """, (customer_email,))
    customer_row = cursor.fetchone()
    conn.close()
    if customer_row:
        return jsonify({'success': True, 'customer': dict(customer_row)})
    return jsonify({'success': False, 'message': 'Khong tim thay khach hang'}), 404


@system_bp.route('/api/customer-info/<int:user_id>', methods=['GET'])
def api_get_customer_info(user_id):
    """Lay thong tin khach hang theo ID."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_user_id = g.api_user_id
    caller_role = get_user_role_from_db(caller_user_id, g.api_account_type or 'customer')
    if caller_role not in ('Receptionist', 'Manager', 'Admin') and caller_user_id != user_id:
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT account_id as user_id, email, customer_name as full_name,
               loyalty_points as points, membership_tier as tier,
               (loyalty_points / 10) as total_nights
        FROM Customer_Accounts WHERE account_id = ?
    """, (user_id,))
    customer_row = cursor.fetchone()
    conn.close()
    if customer_row:
        return jsonify({'success': True, 'customer': dict(customer_row)})
    return jsonify({'success': False, 'message': 'Khong tim thay'}), 404

# ─── API GÓI BỔ SUNG (PHASE 4) ────────────────────────────────────────────────

@system_bp.route('/api/service-catalog', methods=['GET'])
def api_get_service_catalog():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT catalog_id, item_name, default_price, category FROM Service_Catalog ORDER BY category")
    catalog = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'catalog': catalog})

@system_bp.route('/api/housekeeping/rooms', methods=['GET'])
def api_housekeeping_rooms():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pr.physical_room_id, pr.room_name, pr.housekeeping_status, 
               rt.room_type_code, dh.hotel as hotel_name
        FROM Physical_Room pr
        JOIN Dim_RoomType rt ON pr.room_type_id = rt.room_type_id
        LEFT JOIN Dim_Hotel dh ON rt.hotel_id = dh.hotel_id
        WHERE pr.housekeeping_status != 'Clean'
        ORDER BY dh.hotel, pr.room_name
    """)
    rooms = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'rooms': rooms})

@system_bp.route('/api/housekeeping/rooms/<int:room_id>/clean', methods=['POST'])
def api_housekeeping_clean(room_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    hk_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if hk_role not in ('Housekeeper', 'Manager', 'Admin', 'Receptionist'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Physical_Room SET housekeeping_status = 'Clean' WHERE physical_room_id = ?", (room_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã cập nhật trạng thái Clean'})


@system_bp.route('/api/cart', methods=['GET'])
def api_get_cart():
    session_id = request.args.get('session_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ci.*, pr.room_name, pr.housekeeping_status, rt.room_type_code, dh.hotel as hotel_name, rl.locked_until
        FROM Cart_Items ci
        JOIN Physical_Room pr ON ci.physical_room_id = pr.physical_room_id
        JOIN Dim_RoomType rt ON ci.room_type_id = rt.room_type_id
        LEFT JOIN Dim_Hotel dh ON rt.hotel_id = dh.hotel_id
        LEFT JOIN Room_Lock rl ON ci.physical_room_id = rl.physical_room_id AND ci.session_id = rl.session_id
        WHERE ci.session_id = ?
    """, (session_id,))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'items': items})

@system_bp.route('/api/cart/add', methods=['POST'])
def api_add_to_cart():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Cart_Items (session_id, room_type_id, physical_room_id, arrival_date, departure_date, adults, children, babies, booking_type, selected_nights, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data['session_id'], data['room_type_id'], data['physical_room_id'], data['checkin_date'], data['checkout_date'], data.get('adults', 1), data.get('children', 0), data.get('babies', 0), data['booking_type'], data.get('selected_nights', ''), data['total_price']))
    # attribution write-through
    try:
        cursor.execute(
            "UPDATE Cart_Items SET source_channel = ?, utm_campaign = ?, utm_medium = ? WHERE cart_item_id = ?",
            (
                (data.get('source_channel') or 'direct'),
                (data.get('utm_campaign') or ''),
                (data.get('utm_medium') or ''),
                cursor.lastrowid,
            ),
        )
    except Exception:
        pass
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã thêm vào giỏ'})

@system_bp.route('/api/cart/remove/<int:item_id>', methods=['DELETE'])
def api_remove_from_cart(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Cart_Items WHERE cart_item_id = ?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@system_bp.route('/api/cart/checkout', methods=['POST'])
def api_checkout_cart():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    if (g.api_account_type or '') != 'customer':
        return jsonify({'success': False, 'message': 'Chi khach hang duoc thanh toan gio'}), 403
    data = request.get_json()
    session_id = data.get('session_id')
    user_id = g.api_user_id
    special_requests = data.get('special_requests', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM New_Bookings WHERE group_order_id = ?", (session_id,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Giỏ hàng này đã được thanh toán. Tránh double-click!'})

    cursor.execute("SELECT * FROM Cart_Items WHERE session_id = ?", (session_id,))
    items = cursor.fetchall()
    
    if not items:
        conn.close()
        return jsonify({'success': False, 'message': 'Giỏ hàng trống'})
    
    try:
        for item in items:
            booking_type = item['booking_type'] or 'continuous'
            selected_nights = item['selected_nights'] or ''
            arrival_date = item['arrival_date']
            departure_date = item['departure_date']

            if booking_type == 'fragmented':
                nights_list = [n.strip() for n in selected_nights.split(',') if n.strip()]
                nights_list.sort()
                nights = len(nights_list)
            else:
                try:
                    ad = datetime.strptime(arrival_date, '%Y-%m-%d').date()
                    dd = datetime.strptime(departure_date, '%Y-%m-%d').date()
                except Exception:
                    ad = None
                    dd = None
                nights_list = []
                if ad and dd:
                    cur = ad
                    while cur < dd:
                        nights_list.append(cur.strftime('%Y-%m-%d'))
                        cur += timedelta(days=1)
                nights = len(nights_list) if nights_list else 1

            cursor.execute("""
                INSERT INTO New_Bookings
                (user_id, hotel_id, room_type_id, physical_room_id, booking_type, selected_nights, arrival_date, departure_date, nights, total_price, status_detail, is_canceled, group_order_id, special_requests, source_channel, utm_campaign, utm_medium)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'Confirmed', 0, ?, ?, ?, ?, ?)
            """, (user_id, item['room_type_id'], item['physical_room_id'], booking_type, selected_nights, arrival_date, departure_date, nights, item['total_price'], session_id, special_requests, item['source_channel'] or 'direct', item['utm_campaign'] or '', item['utm_medium'] or ''))
            new_booking_id = cursor.lastrowid
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{new_booking_id:06d}"
            cursor.execute("UPDATE New_Bookings SET invoice_number = ?, invoice_issued_at = datetime('now') WHERE booking_id = ?", (invoice_number, new_booking_id))
            if nights_list:
                cursor.executemany(
                    "INSERT OR IGNORE INTO Booking_Nights (booking_id, physical_room_id, night_date) VALUES (?, ?, ?)",
                    [(new_booking_id, item['physical_room_id'], d) for d in nights_list],
                )
            
        cursor.execute("DELETE FROM Cart_Items WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM Room_Lock WHERE session_id = ?", (session_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR Checkout] {e}")
        return jsonify({'success': False, 'message': 'Lỗi logic tính toán. Giao dịch đã bị hoàn tác! Đảm bảo không mất tiền.'}), 500
    finally:
        conn.close()
    
    return jsonify({'success': True, 'group_order_id': session_id, 'message': 'Checkout giỏ hàng thành công!'})

# ─── REFUND POLICY ENDPOINTS ──────────────────────────────────────────────────

@system_bp.route('/api/refund-policy', methods=['GET'])
def api_get_refund_policies():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT policy_id, days_before_arrival, hours_before_checkin, refund_percent, description FROM Refund_Policy ORDER BY days_before_arrival DESC")
    policies = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'policies': policies})

@system_bp.route('/api/refund-policy', methods=['POST'])
def api_create_refund_policy():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    if get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff') not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO Refund_Policy (days_before_arrival, hours_before_checkin, refund_percent, description)
            VALUES (?, ?, ?, ?)
        """, (data.get('days_before_arrival', 0), data.get('hours_before_checkin', 0),
              data.get('refund_percent', 0.0), data.get('description', '')))
        conn.commit()
        return jsonify({'success': True, 'message': 'Tao chinh sach thanh cong'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@system_bp.route('/api/refund-policy/<int:policy_id>', methods=['PUT'])
def api_update_refund_policy(policy_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    if get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff') not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()
    conn = get_db_connection()
    conn.execute("""
        UPDATE Refund_Policy SET days_before_arrival = ?, hours_before_checkin = ?,
               refund_percent = ?, description = ?
        WHERE policy_id = ?
    """, (data.get('days_before_arrival'), data.get('hours_before_checkin'),
          data.get('refund_percent'), data.get('description'), policy_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cap nhat thanh cong'})

@system_bp.route('/api/refund-policy/<int:policy_id>', methods=['DELETE'])
def api_delete_refund_policy(policy_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    if get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff') not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    conn = get_db_connection()
    conn.execute("DELETE FROM Refund_Policy WHERE policy_id = ?", (policy_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Xoa thanh cong'})

# ─── STARTUP ──────────────────────────────────────────────────────────────────

def cleanup_locks_job():
    """Chạy ngầm mỗi 60 giây để dọn dẹp các khóa phòng hết hạn (Dùng cho cách chạy truyền thống)"""
    import time
    while True:
        try:
            conn = get_db_connection()
            cleanup_expired_locks(conn)
            conn.close()
        except Exception as e:
            print(f"[CRON] Lỗi dọn dẹp khóa phòng: {e}")
        time.sleep(60)

# Khối cleanup_locks_job có thể được gọi từ app.py if needed, 
# nhưng không nên để app.run ở đây vì đây là Blueprint.

