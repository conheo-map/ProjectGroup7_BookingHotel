import sqlite3
from datetime import datetime, timedelta, date
from database import get_db_connection


def cleanup_expired_locks(conn):
    """Xoa cac Room_Lock da het han de giai phong phong."""
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("DELETE FROM Room_Lock WHERE locked_until < ?", (now_str,))
    conn.commit()

def get_user_role_from_db(user_id, account_type='staff'):
    """Tra ve role cua user tu DB. Tra None neu khong tim thay."""
    if not user_id:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    if account_type == 'customer':
        cursor.execute("SELECT account_id FROM Customer_Accounts WHERE account_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return 'Guest' if row else None
    cursor.execute("""
        SELECT r.role_name FROM Roles r
        JOIN User_Roles ur ON r.role_id = ur.role_id
        WHERE ur.user_id = ?
        ORDER BY r.role_id DESC LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row['role_name'] if row else None

def calculate_loyalty_tier(total_points):
    """Tinh hang thanh vien dua tren tong diem."""
    if total_points >= 210:
        return 'Gold'
    elif total_points >= 50:
        return 'Silver'
    return 'Newbie'


def get_room_policy(cursor, room_type_id):
    cursor.execute("""
        SELECT
            max_adults,
            max_children,
            COALESCE(allow_child_sharing, 1) AS allow_child_sharing,
            COALESCE(extra_bed_capacity, 0) AS extra_bed_capacity,
            COALESCE(extra_adult_fee, 0.0) AS extra_adult_fee,
            COALESCE(child_breakfast_fee, 0.0) AS child_breakfast_fee
        FROM Dim_RoomType
        WHERE room_type_id = ?
    """, (room_type_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def evaluate_occupancy_policy(cursor, room_type_id, adults, children):
    """
    Trả về:
    - allowed: có hợp lệ theo chính sách phòng hay không
    - extra_adults: số người lớn cần extra bed
    - shared_children: số trẻ em dùng giường sẵn có
    - surcharge_per_night: phụ thu mỗi đêm theo chính sách
    """
    policy = get_room_policy(cursor, room_type_id)
    if not policy:
        return {'allowed': False, 'reason': 'Room type not found'}

    max_adults = int(policy['max_adults'] or 0)
    max_children = int(policy['max_children'] or 0)
    allow_child_sharing = int(policy['allow_child_sharing'] or 0) == 1
    extra_bed_capacity = int(policy['extra_bed_capacity'] or 0)
    extra_adult_fee = float(policy['extra_adult_fee'] or 0.0)
    child_breakfast_fee = float(policy['child_breakfast_fee'] or 0.0)

    adults = int(adults or 0)
    children = int(children or 0)

    extra_adults = max(0, adults - max_adults)
    if extra_adults > extra_bed_capacity:
        return {'allowed': False, 'reason': 'Not enough extra-bed capacity'}

    shared_children = 0
    if children > max_children:
        if not allow_child_sharing:
            return {'allowed': False, 'reason': 'Child sharing bed is not allowed'}
        shared_children = children - max_children
        if shared_children > 1:
            return {'allowed': False, 'reason': 'Child sharing bed exceeds policy'}

    surcharge_per_night = round((extra_adults * extra_adult_fee) + (shared_children * child_breakfast_fee), 2)
    return {
        'allowed': True,
        'extra_adults': extra_adults,
        'shared_children': shared_children,
        'surcharge_per_night': surcharge_per_night
    }

def _get_effective_price(room_type_id, room_type_code, target_date_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    price = 0.0

    # 1. Tìm trong Room_Rates (Ghi đè theo ngày)
    cursor.execute("""
        SELECT rate_id, base_price, base_price_cents FROM Room_Rates
        WHERE room_type_code = ? AND valid_date = ? AND physical_room_id IS NULL
    """, (room_type_code, target_date_str))
    override_row = cursor.fetchone()
    
    if override_row:
        if override_row['base_price_cents']:
            price = override_row['base_price_cents'] / 100.0
        else:
            price = override_row['base_price']
    else:
        # 2. Lấy giá mặc định từ Dim_RoomType
        cursor.execute("SELECT base_price, base_price_cents FROM Dim_RoomType WHERE room_type_id = ?", (room_type_id,))
        base_row = cursor.fetchone()
        if base_row:
            if base_row['base_price_cents']:
                price = base_row['base_price_cents'] / 100.0
            else:
                price = base_row['base_price']
        else:
            price = 100.0
            
    conn.close()
    return price

def get_effective_price_for_date(cursor, room_type_id, room_type_code, target_date_str):
    """Gia hieu luc cho 1 dem: uu tien Room_Rates, fallback Dim_RoomType.base_price."""
    return _get_effective_price(room_type_id, room_type_code, target_date_str)

def _get_promo_price(effective_price, target_date_str, membership_tier, room_type_code, hotel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT discount_percent, discount_type, code FROM Promotions
        WHERE active = 1 AND apply_scope = 'all'
          AND (start_date IS NULL OR start_date <= ?)
          AND (end_date IS NULL OR end_date >= ?)
          AND (max_uses = 0 OR current_uses < max_uses)
          AND (
            CASE membership_tier_required
              WHEN 'Gold' THEN 2
              WHEN 'Silver' THEN 1
              ELSE 0
            END
          ) <= (
            CASE ?
              WHEN 'Gold' THEN 2
              WHEN 'Silver' THEN 1
              ELSE 0
            END
          )
        ORDER BY discount_percent DESC LIMIT 1
    """, (target_date_str, target_date_str, membership_tier or 'Newbie'))
    promo_row = cursor.fetchone()
    if not promo_row:
        cursor.execute("""
            SELECT discount_percent, discount_type, code
            FROM Promotions
            WHERE active = 1
              AND apply_scope = 'hotel'
              AND scope_value = ?
              AND (start_date IS NULL OR start_date <= ?)
              AND (end_date IS NULL OR end_date >= ?)
              AND (max_uses = 0 OR current_uses < max_uses)
              AND (
                CASE membership_tier_required
                  WHEN 'Gold' THEN 2
                  WHEN 'Silver' THEN 1
                  ELSE 0
                END
              ) <= (
                CASE ?
                  WHEN 'Gold' THEN 2
                  WHEN 'Silver' THEN 1
                  ELSE 0
                END
              )
            ORDER BY discount_percent DESC LIMIT 1
        """, (str(hotel_id), target_date_str, target_date_str, membership_tier or 'Newbie'))
        promo_row = cursor.fetchone()
    if not promo_row:
        cursor.execute("""
            SELECT discount_percent, discount_type, code
            FROM Promotions
            WHERE active = 1
              AND apply_scope = 'room_type'
              AND scope_value = ?
              AND (start_date IS NULL OR start_date <= ?)
              AND (end_date IS NULL OR end_date >= ?)
              AND (max_uses = 0 OR current_uses < max_uses)
              AND (
                CASE membership_tier_required
                  WHEN 'Gold' THEN 2
                  WHEN 'Silver' THEN 1
                  ELSE 0
                END
              ) <= (
                CASE ?
                  WHEN 'Gold' THEN 2
                  WHEN 'Silver' THEN 1
                  ELSE 0
                END
              )
            ORDER BY discount_percent DESC LIMIT 1
        """, (room_type_code, target_date_str, target_date_str, membership_tier or 'Newbie'))
        promo_row = cursor.fetchone()
    conn.close()
    if not promo_row:
        return effective_price, None
    if promo_row['discount_type'] == 'fixed':
        promo_price = max(0.0, effective_price - promo_row['discount_percent'])
    else:
        promo_price = round(effective_price * (1 - promo_row['discount_percent'] / 100), 2)
    return promo_price, promo_row['code']

def get_promo_price_for_date(cursor, effective_price, room_type_code, target_date_str, membership_tier='Newbie', hotel_id=1):
    """Gia sau khi ap khuyen mai (neu co). Tra ve tuple (promo_price, promo_code_used)."""
    return _get_promo_price(effective_price, target_date_str, membership_tier, room_type_code, hotel_id)

def calculate_booking_total_for_nights(cursor, room_type_id, room_type_code, list_of_night_dates, membership_tier='Newbie', hotel_id=1, adults=1, children=0):
    """Tinh tong tien cho danh sach cac dem cu the da chon."""
    occupancy_eval = evaluate_occupancy_policy(cursor, room_type_id, adults, children)
    if not occupancy_eval.get('allowed'):
        return None, None
    surcharge_per_night = occupancy_eval.get('surcharge_per_night', 0.0)

    total_effective_price = 0.0
    total_promo_price = 0.0
    for night_date_str in list_of_night_dates:
        effective_price = get_effective_price_for_date(cursor, room_type_id, room_type_code, night_date_str)
        promo_price, _ = get_promo_price_for_date(cursor, effective_price, room_type_code, night_date_str, membership_tier, hotel_id)
        total_effective_price += (effective_price + surcharge_per_night)
        total_promo_price += (promo_price + surcharge_per_night)
    return round(total_effective_price, 2), round(total_promo_price, 2)

def get_refund_amount_by_hours(conn, arrival_date_str, total_paid_amount):
    """Tinh so tien hoan tra dua tren chinh sach hoan tien (theo gio)."""
    cursor = conn.cursor()
    checkin_datetime = datetime.strptime(arrival_date_str + ' 14:00:00', '%Y-%m-%d %H:%M:%S')
    hours_remaining = (checkin_datetime - datetime.now()).total_seconds() / 3600.0
    cursor.execute("""
        SELECT refund_percent FROM Refund_Policy
        WHERE hours_before_checkin <= ?
        ORDER BY hours_before_checkin DESC
        LIMIT 1
    """, (hours_remaining,))
    policy_row = cursor.fetchone()
    if not policy_row:
        cursor.execute("SELECT refund_percent FROM Refund_Policy ORDER BY days_before_arrival DESC LIMIT 1")
        policy_row = cursor.fetchone()
    refund_percent = policy_row['refund_percent'] if policy_row else 0.0
    refund_amount = round(total_paid_amount * refund_percent / 100, 2)
    return refund_percent, refund_amount

def is_night_occupied(cursor, physical_room_id, night_date_str):
    """Kiem tra xem 1 phong vat ly co bi chiem trong 1 dem cu the khong."""
    cursor.execute("""
        SELECT 1
        FROM Booking_Nights bn
        JOIN New_Bookings nb ON nb.booking_id = bn.booking_id
        WHERE bn.physical_room_id = ?
          AND bn.night_date = ?
          AND nb.status_detail NOT IN ('Canceled', 'No-Show')
        LIMIT 1
    """, (physical_room_id, night_date_str))
    if cursor.fetchone():
        return True
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        SELECT 1 FROM Room_Lock
        WHERE physical_room_id = ? AND lock_date = ? AND locked_until > ?
        LIMIT 1
    """, (physical_room_id, night_date_str, now_str))
    if cursor.fetchone():
        return True
    return False

def get_room_availability(cursor, room_type_id, checkin_date_obj, checkout_date_obj):
    """Phan loai cac phong vat ly thanh 2 nhom: lien tuc va ngat quang."""
    cursor.execute("""
        SELECT physical_room_id, room_name, housekeeping_status
        FROM Physical_Room
        WHERE room_type_id = ? AND is_active = 1
        ORDER BY room_name
    """, (room_type_id,))
    all_physical_rooms = cursor.fetchall()
    
    if not all_physical_rooms:
        return [], []

    list_of_nights = []
    current_night = checkin_date_obj
    while current_night < checkout_date_obj:
        list_of_nights.append(current_night.strftime('%Y-%m-%d'))
        current_night += timedelta(days=1)

    start_str = checkin_date_obj.strftime('%Y-%m-%d')
    end_str = checkout_date_obj.strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT bn.physical_room_id, bn.night_date
        FROM Booking_Nights bn
        JOIN New_Bookings nb ON nb.booking_id = bn.booking_id
        WHERE nb.status_detail NOT IN ('Canceled', 'No-Show')
          AND bn.physical_room_id IN (SELECT physical_room_id FROM Physical_Room WHERE room_type_id = ?)
          AND bn.night_date >= ? AND bn.night_date < ?
    """, (room_type_id, start_str, end_str))
    booked_nights = cursor.fetchall()

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        SELECT physical_room_id, lock_date
        FROM Room_Lock
        WHERE physical_room_id IN (SELECT physical_room_id FROM Physical_Room WHERE room_type_id = ?)
          AND locked_until > ? AND lock_date >= ? AND lock_date < ?
    """, (room_type_id, now_str, start_str, end_str))
    room_locks = cursor.fetchall()

    occ_map = {pr['physical_room_id']: set() for pr in all_physical_rooms}

    for bn in booked_nights:
        pr_id = bn['physical_room_id']
        if pr_id in occ_map:
            occ_map[pr_id].add(bn['night_date'])

    for rl in room_locks:
        pr_id = rl['physical_room_id']
        if pr_id in occ_map:
            occ_map[pr_id].add(rl['lock_date'])

    continuous_available_rooms = []
    fragmented_available_rooms = []

    for physical_room in all_physical_rooms:
        physical_room_id = physical_room['physical_room_id']
        free_nights_list = []
        occupied_nights_list = []
        
        pr_occ_set = occ_map.get(physical_room_id, set())

        for night_str in list_of_nights:
            if night_str in pr_occ_set:
                occupied_nights_list.append(night_str)
            else:
                free_nights_list.append(night_str)

        if len(occupied_nights_list) == 0:
            continuous_available_rooms.append({
                'physical_room_id': physical_room_id,
                'room_name': physical_room['room_name'],
                'housekeeping_status': physical_room['housekeeping_status'],
                'free_nights': free_nights_list
            })
        elif len(free_nights_list) > 0:
            fragmented_available_rooms.append({
                'physical_room_id': physical_room_id,
                'room_name': physical_room['room_name'],
                'housekeeping_status': physical_room['housekeeping_status'],
                'free_nights': free_nights_list,
                'occupied_nights': occupied_nights_list
            })

    return continuous_available_rooms, fragmented_available_rooms
