from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta, date
from database import get_db_connection
from services.api_auth import require_token
from services.booking_service import (
    cleanup_expired_locks, get_user_role_from_db, get_room_availability,
    get_effective_price_for_date, get_promo_price_for_date, is_night_occupied,
    evaluate_occupancy_policy
)
import sqlite3

room_bp = Blueprint('room_bp', __name__)

@room_bp.route('/api/rooms/search', methods=['GET'])
def api_search_rooms():
    checkin_date_str = request.args.get('checkin_date', '')
    checkout_date_str = request.args.get('checkout_date', '')
    number_of_adults = request.args.get('adults', 1, type=int)
    number_of_children = request.args.get('children', 0, type=int)
    # Legacy single-value filters
    filter_hotel_type = request.args.get('hotel_type', '')
    filter_hotel_id = request.args.get('hotel_id', '', type=str)
    filter_room_type_code = request.args.get('room_type_code', '')
    filter_availability = request.args.get('availability', '')  # 'continuous', 'fragmented', ''
    filter_min_price = request.args.get('min_price', 0.0, type=float)
    filter_max_price = request.args.get('max_price', 9999999.0, type=float)
    filter_min_rating = request.args.get('min_rating', 0.0, type=float)
    # Multi-value array filters (OTA sidebar checkboxes)
    filter_star_ratings = request.args.getlist('star_ratings[]', type=int)  # e.g. [4, 5]
    filter_hotel_types = request.args.getlist('hotel_types[]')              # e.g. ['City Hotel', 'Resort Hotel']
    filter_room_type_codes = request.args.getlist('room_type_codes[]')      # e.g. ['A', 'B']
    sort_by = request.args.get('sort_by', 'price_asc')  # 'price_asc', 'price_desc', 'rating_desc'

    if not checkin_date_str or not checkout_date_str:
        return jsonify({'success': False, 'message': 'Vui long chon ngay check-in va check-out'}), 400

    try:
        checkin_date_obj = datetime.strptime(checkin_date_str, '%Y-%m-%d').date()
        checkout_date_obj = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Định dạng ngày không hợp lệ (YYYY-MM-DD)'}), 400
    if checkin_date_obj < date.today():
        return jsonify({'success': False, 'message': 'Ngay check-in khong duoc o qua khu'}), 400
    if checkout_date_obj <= checkin_date_obj:
        return jsonify({'success': False, 'message': 'Ngay check-out phai sau check-in it nhat 1 ngay'}), 400

    user_id = None
    if getattr(g, 'api_account_type', None) == 'customer' and getattr(g, 'api_user_id', None):
        user_id = g.api_user_id
    manual_promo_code = request.args.get('promo_code', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cleanup_expired_locks(conn)

    is_gold = False
    membership_tier = 'Newbie'
    if user_id:
        cursor.execute("SELECT membership_tier FROM Customer_Accounts WHERE account_id = ?", (user_id,))
        acc = cursor.fetchone()
        if acc and acc['membership_tier']:
            membership_tier = acc['membership_tier']
        if membership_tier == 'Gold':
            is_gold = True

    current_promo = None
    if manual_promo_code:
        cursor.execute("SELECT discount_percent, discount_type, code FROM Promotions WHERE code = ? AND active = 1", (manual_promo_code,))
        current_promo = cursor.fetchone()

    where_clause = "WHERE drt.is_active = 1"
    query_params = []
    # Legacy hotel_type string filter (from dropdown)
    if filter_hotel_type:
        where_clause += " AND dh.hotel = ?"
        query_params.append(filter_hotel_type)
    if filter_hotel_id:
        try:
            where_clause += " AND dh.hotel_id = ?"
            query_params.append(int(filter_hotel_id))
        except ValueError:
            pass

    # Multi-value array filters (OTA sidebar checkboxes)
    if filter_star_ratings:
        placeholders = ','.join('?' * len(filter_star_ratings))
        where_clause += f" AND dh.star_rating IN ({placeholders})"
        query_params.extend(filter_star_ratings)
    if filter_hotel_types:
        placeholders = ','.join('?' * len(filter_hotel_types))
        where_clause += f" AND dh.hotel_type IN ({placeholders})"
        query_params.extend(filter_hotel_types)
    if filter_room_type_codes:
        # Multi-value list from sidebar checkboxes
        placeholders = ','.join('?' * len(filter_room_type_codes))
        where_clause += f" AND drt.room_type_code IN ({placeholders})"
        query_params.extend(filter_room_type_codes)
    elif filter_room_type_code:
        # Legacy single-value from old dropdown
        where_clause += " AND drt.room_type_code = ?"
        query_params.append(filter_room_type_code)

    # Determine sort order
    sort_sql = "drt.room_type_code"
    if sort_by == 'price_desc':
        sort_sql = "drt.base_price DESC"
    elif sort_by == 'rating_desc':
        sort_sql = "avg_rating DESC"

    cursor.execute(f"""
        SELECT drt.room_type_id, drt.room_type_code, drt.max_adults, drt.max_children,
               drt.base_price, drt.description, drt.amenities,
               COALESCE(drt.allow_child_sharing, 1) AS allow_child_sharing,
               COALESCE(drt.extra_bed_capacity, 0) AS extra_bed_capacity,
               COALESCE(drt.extra_adult_fee, 0.0) AS extra_adult_fee,
               COALESCE(drt.child_breakfast_fee, 0.0) AS child_breakfast_fee,
               drt.images, drt.main_image,
               dh.hotel_id, dh.hotel AS hotel_name,
               COALESCE(dh.star_rating, 3) AS star_rating,
               COALESCE(dh.hotel_type, 'City Hotel') AS hotel_type,
               COALESCE(AVG(rv.rating), 0) AS avg_rating,
               COUNT(DISTINCT rv.review_id) AS review_count
        FROM Dim_RoomType drt
        JOIN Dim_Hotel dh ON drt.hotel_id = dh.hotel_id
        LEFT JOIN Reviews rv ON rv.hotel_id = dh.hotel_id
        {where_clause}
        GROUP BY drt.room_type_id
        HAVING avg_rating >= ?
        ORDER BY {sort_sql}
    """, query_params + [filter_min_rating])
    all_room_type_rows = cursor.fetchall()

    all_rooms = []
    seen_room_types = {}
    seen_hotels = {}

    for room_type_row in all_room_type_rows:
        room_type_id = room_type_row['room_type_id']
        room_type_code = room_type_row['room_type_code']
        occupancy_eval = evaluate_occupancy_policy(cursor, room_type_id, number_of_adults, number_of_children)
        if not occupancy_eval.get('allowed'):
            continue
        surcharge_per_night = occupancy_eval.get('surcharge_per_night', 0.0)

        continuous_rooms, fragmented_rooms = get_room_availability(
            cursor, room_type_id, checkin_date_obj, checkout_date_obj
        )

        if not continuous_rooms and not fragmented_rooms:
            continue

        # Skip room type entirely if availability filter doesn't match
        if filter_availability == 'continuous' and not continuous_rooms:
            continue
        if filter_availability == 'fragmented' and not fragmented_rooms:
            continue

        list_of_nights = []
        current_night = checkin_date_obj
        while current_night < checkout_date_obj:
            list_of_nights.append(current_night.strftime('%Y-%m-%d'))
            current_night += timedelta(days=1)

        effective_prices = [get_effective_price_for_date(cursor, room_type_id, room_type_code, d) + surcharge_per_night for d in list_of_nights]

        if is_gold:
            effective_prices = [ep * 0.95 for ep in effective_prices]

        if current_promo:
            promo_prices = []
            for ep in effective_prices:
                if current_promo['discount_type'] == 'fixed':
                    promo_prices.append(max(0.0, ep - current_promo['discount_percent']))
                else:
                    promo_prices.append(round(ep * (1 - current_promo['discount_percent'] / 100), 2))
        else:
            promo_prices = [get_promo_price_for_date(cursor, ep, room_type_code, d, membership_tier, room_type_row['hotel_id'])[0] for ep, d in zip(effective_prices, list_of_nights)]

        effective_price_max = max(effective_prices) if effective_prices else 0
        promo_price_min = min(promo_prices) if promo_prices else 0
        promo_price_max = max(promo_prices) if promo_prices else 0

        if promo_price_min > filter_max_price or promo_price_max < filter_min_price:
            continue

        shared_info = {
            'room_type_id': room_type_id,
            'room_type_code': room_type_code,
            'hotel_id': room_type_row['hotel_id'],
            'hotel_name': room_type_row['hotel_name'],
            'star_rating': room_type_row['star_rating'] or 3,
            'hotel_type': room_type_row['hotel_type'] or 'City Hotel',
            'max_adults': room_type_row['max_adults'],
            'max_children': room_type_row['max_children'],
            'allow_child_sharing': room_type_row['allow_child_sharing'],
            'extra_bed_capacity': room_type_row['extra_bed_capacity'],
            'extra_adult_fee': room_type_row['extra_adult_fee'],
            'child_breakfast_fee': room_type_row['child_breakfast_fee'],
            'extra_adults_applied': occupancy_eval.get('extra_adults', 0),
            'shared_children_applied': occupancy_eval.get('shared_children', 0),
            'occupancy_surcharge_per_night': surcharge_per_night,
            'description': room_type_row['description'] or '',
            'amenities': room_type_row['amenities'] or '',
            'avg_rating': round(room_type_row['avg_rating'] or 0, 1),
            'review_count': room_type_row['review_count'] or 0,
            'effective_price_max': round(effective_price_max, 2),
            'promo_price_min': round(promo_price_min, 2),
            'promo_price_max': round(promo_price_max, 2),
            'checkin_date': checkin_date_str,
            'checkout_date': checkout_date_str,
            'main_image': room_type_row['main_image'],
            'images': room_type_row['images'],
        }

        # Expand each physical room into its own result entry
        if filter_availability != 'fragmented':
            for phys in continuous_rooms:
                import json
                try:
                    p_images = json.loads(phys.get('images') or '[]')
                except:
                    p_images = []
                all_rooms.append({
                    **shared_info,
                    'physical_room_id': phys['physical_room_id'],
                    'room_name': phys['room_name'],
                    'housekeeping_status': phys.get('housekeeping_status', 'Clean'),
                    'availability_type': 'continuous',
                    'free_nights': phys.get('free_nights', []),
                    'main_image': phys.get('main_image') or shared_info['main_image'],
                    'images': p_images if p_images else (json.loads(shared_info['images']) if isinstance(shared_info['images'], str) else shared_info['images'])
                })

        if filter_availability != 'continuous':
            for phys in fragmented_rooms:
                import json
                try:
                    p_images = json.loads(phys.get('images') or '[]')
                except:
                    p_images = []
                all_rooms.append({
                    **shared_info,
                    'physical_room_id': phys['physical_room_id'],
                    'room_name': phys['room_name'],
                    'housekeeping_status': phys.get('housekeeping_status', 'Clean'),
                    'availability_type': 'fragmented',
                    'free_nights': phys.get('free_nights', []),
                    'main_image': phys.get('main_image') or shared_info['main_image'],
                    'images': p_images if p_images else (json.loads(shared_info['images']) if isinstance(shared_info['images'], str) else shared_info['images'])
                })

        seen_room_types[room_type_code] = True
        seen_hotels[room_type_row['hotel_id']] = room_type_row['hotel_name']

    # Sort: continuous first, then by sort_by param
    if sort_by == 'price_desc':
        all_rooms.sort(key=lambda r: (0 if r['availability_type'] == 'continuous' else 1, -r['promo_price_min']))
    elif sort_by == 'rating_desc':
        all_rooms.sort(key=lambda r: (0 if r['availability_type'] == 'continuous' else 1, -r['avg_rating']))
    else:  # default price_asc
        all_rooms.sort(key=lambda r: (0 if r['availability_type'] == 'continuous' else 1, r['promo_price_min']))

    conn.close()
    return jsonify({
        'success': True,
        'rooms': all_rooms,
        'total': len(all_rooms),
        'filter_options': {
            'room_types': sorted(seen_room_types.keys()),
            'hotels': [{'id': k, 'name': v} for k, v in sorted(seen_hotels.items(), key=lambda x: x[0])],
        },
    })


@room_bp.route('/api/room-types', methods=['GET'])
def api_get_room_types():
    filter_hotel_id = request.args.get('hotel_id', type=int)
    conn = get_db_connection()
    cursor = conn.cursor()
    where = "WHERE drt.is_active = 1"
    params = []
    if filter_hotel_id:
        where += " AND drt.hotel_id = ?"
        params.append(filter_hotel_id)
    cursor.execute(f"""
        SELECT drt.room_type_id, drt.room_type_code, dh.hotel_id, dh.hotel AS hotel_name
        FROM Dim_RoomType drt
        JOIN Dim_Hotel dh ON drt.hotel_id = dh.hotel_id
        {where}
        ORDER BY drt.room_type_code
    """, params)
    room_types = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'room_types': room_types})

@room_bp.route('/api/rooms/detail', methods=['GET'])
def api_room_detail():
    room_type_id = request.args.get('room_type_id', type=int)
    checkin_date_str = request.args.get('checkin_date', '')
    checkout_date_str = request.args.get('checkout_date', '')

    if not room_type_id:
        return jsonify({'success': False, 'message': 'Thieu room_type_id'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cleanup_expired_locks(conn)

    cursor.execute("""
        SELECT drt.room_type_id, drt.room_type_code, drt.max_adults, drt.max_children,
               drt.base_price, drt.description, drt.amenities, drt.images, drt.main_image,
               dh.hotel_id, dh.hotel AS hotel_name
        FROM Dim_RoomType drt
        JOIN Dim_Hotel dh ON dh.hotel_id = drt.hotel_id
        WHERE drt.room_type_id = ?
    """, (room_type_id,))
    room_type_row = cursor.fetchone()
    if not room_type_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay loai phong'}), 404
    
    rt_data = dict(room_type_row)
    import json
    try:
        rt_data['images'] = json.loads(rt_data.get('images') or '[]')
    except:
        rt_data['images'] = []

    cursor.execute("""
        SELECT rv.review_id, rv.rating, rv.comment, rv.review_date,
               COALESCE(ca.customer_name, 'Khach hang') AS reviewer_name
        FROM Reviews rv
        LEFT JOIN Customer_Accounts ca ON rv.user_id = ca.account_id
        WHERE rv.hotel_id = ?
        ORDER BY rv.review_date DESC
        LIMIT 20
    """, (room_type_row['hotel_id'],))
    reviews_list = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT AVG(rating) as avg_rating, COUNT(*) as total FROM Reviews WHERE hotel_id = ?",
                   (room_type_row['hotel_id'],))
    rating_summary = cursor.fetchone()

    continuous_rooms = []
    fragmented_rooms = []
    if checkin_date_str and checkout_date_str:
        checkin_date_obj = datetime.strptime(checkin_date_str, '%Y-%m-%d').date()
        checkout_date_obj = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
        continuous_rooms, fragmented_rooms = get_room_availability(
            cursor, room_type_id, checkin_date_obj, checkout_date_obj
        )

    conn.close()
    return jsonify({
        'success': True,
        'room_type': rt_data,
        'reviews': reviews_list,
        'avg_rating': round(rating_summary['avg_rating'] or 0, 1),
        'review_count': rating_summary['total'] or 0,
        'continuous_rooms': continuous_rooms,
        'fragmented_rooms': fragmented_rooms,
        'checkin_date': checkin_date_str,
        'checkout_date': checkout_date_str
    })

@room_bp.route('/api/rooms/lock', methods=['GET', 'POST'])
@room_bp.route('/booking/lock', methods=['GET', 'POST'])
def api_lock_room():
    if request.method == 'GET':
        data = request.args
        list_of_night_dates = request.args.getlist('nights')
    else:
        data = request.get_json() or {}
        list_of_night_dates = data.get('nights', [])
    physical_room_id = data.get('physical_room_id')
    session_id = data.get('session_id', '')

    if not physical_room_id or not session_id or not list_of_night_dates:
        return jsonify({'success': False, 'message': 'Thieu thong tin de giu phong'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cleanup_expired_locks(conn)

    locked_until_datetime = datetime.now() + timedelta(minutes=10)
    locked_until_str = locked_until_datetime.strftime('%Y-%m-%d %H:%M:%S')
    booking_temp_ref = f"TEMP_{session_id}_{physical_room_id}"

    inserted_lock_ids = []
    for night_date_str in list_of_night_dates:
        if is_night_occupied(cursor, physical_room_id, night_date_str):
            conn.close()
            return jsonify({'success': False, 'message': f'Phong da bi dat vao ngay {night_date_str}'}), 409
        cursor.execute("""
            INSERT INTO Room_Lock (physical_room_id, session_id, lock_date, locked_until, booking_temp_ref)
            VALUES (?, ?, ?, ?, ?)
        """, (physical_room_id, session_id, night_date_str, locked_until_str, booking_temp_ref))
        inserted_lock_ids.append(cursor.lastrowid)

    conn.commit()
    conn.close()
    return jsonify({
        'success': True,
        'lock_ids': inserted_lock_ids,
        'locked_until': locked_until_str,
        'booking_temp_ref': booking_temp_ref
    })

@room_bp.route('/api/rooms/lock/cleanup', methods=['POST'])
def api_cleanup_locks():
    conn = get_db_connection()
    cleanup_expired_locks(conn)
    conn.close()
    return jsonify({'success': True, 'message': 'Da don dep cac giu phong het han'})

@room_bp.route('/api/rooms/lock/release', methods=['POST'])
def api_release_locks():
    data = request.get_json()
    booking_temp_ref = data.get('booking_temp_ref', '')
    session_id = data.get('session_id', '')
    if not booking_temp_ref and not session_id:
        return jsonify({'success': False, 'message': 'Thieu thong tin'}), 400
    conn = get_db_connection()
    if booking_temp_ref:
        conn.execute("DELETE FROM Room_Lock WHERE booking_temp_ref = ?", (booking_temp_ref,))
    elif session_id:
        conn.execute("DELETE FROM Room_Lock WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Da giai phong giu cho'})

@room_bp.route('/api/physical-rooms', methods=['GET'])
def api_get_physical_rooms():
    filter_room_type_id = request.args.get('room_type_id', type=int)
    conn = get_db_connection()
    cursor = conn.cursor()

    where_clause = "WHERE pr.is_active = 1"
    query_params = []
    if filter_room_type_id:
        where_clause += " AND pr.room_type_id = ?"
        query_params.append(filter_room_type_id)

    cursor.execute(f"""
        SELECT pr.physical_room_id, pr.room_name, pr.housekeeping_status, pr.is_active,
               drt.room_type_id, drt.room_type_code
        FROM Physical_Room pr
        JOIN Dim_RoomType drt ON pr.room_type_id = drt.room_type_id
        {where_clause}
        ORDER BY drt.room_type_code, pr.room_name
    """, query_params)
    physical_rooms_list = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'physical_rooms': physical_rooms_list})

@room_bp.route('/api/physical-rooms/<int:physical_room_id>/status', methods=['PUT'])
def api_update_room_status(physical_room_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    data = request.get_json() or {}
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    new_housekeeping_status = data.get('housekeeping_status', '')
    valid_statuses = ('Clean', 'Occupied', 'Dirty', 'Maintenance')
    if new_housekeeping_status not in valid_statuses:
        return jsonify({'success': False, 'message': f'Trang thai khong hop le. Chon: {valid_statuses}'}), 400

    conn = get_db_connection()
    conn.execute("UPDATE Physical_Room SET housekeeping_status = ? WHERE physical_room_id = ?",
                 (new_housekeeping_status, physical_room_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Da cap nhat trang thai phong thanh {new_housekeeping_status}'})

@room_bp.route('/api/physical-rooms', methods=['POST'])
def api_create_physical_room():
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    data = request.get_json() or {}
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    room_type_id = data.get('room_type_id')
    room_name = data.get('room_name', '').strip()
    if not room_type_id or not room_name:
        return jsonify({'success': False, 'message': 'Thieu room_type_id hoac room_name'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO Physical_Room (room_type_id, room_name, housekeeping_status) VALUES (?, ?, 'Clean')",
                       (room_type_id, room_name))
        new_id = cursor.lastrowid
        conn.commit()
        return jsonify({'success': True, 'physical_room_id': new_id})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Ten phong da ton tai'}), 409
    finally:
        conn.close()

@room_bp.route('/api/physical-rooms/<int:physical_room_id>', methods=['PUT'])
def api_update_physical_room(physical_room_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    data = request.get_json() or {}
    if caller_role not in ('Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    new_room_name = data.get('room_name', '').strip()
    new_is_active = data.get('is_active', 1)
    new_housekeeping_status = data.get('housekeeping_status')

    conn = get_db_connection()
    if new_room_name:
        conn.execute("UPDATE Physical_Room SET room_name = ? WHERE physical_room_id = ?", (new_room_name, physical_room_id))
    conn.execute("UPDATE Physical_Room SET is_active = ? WHERE physical_room_id = ?", (new_is_active, physical_room_id))
    if new_housekeeping_status:
        conn.execute("UPDATE Physical_Room SET housekeeping_status = ? WHERE physical_room_id = ?", (new_housekeeping_status, physical_room_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cap nhat phong thanh cong'})
