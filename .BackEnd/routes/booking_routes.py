from flask import Blueprint, request, jsonify, g
import sqlite3
from datetime import datetime, timedelta, date
from database import get_db_connection
from config import DEFAULT_TAX_RATE
from services.money import quantize_money, to_cents
from werkzeug.security import generate_password_hash
from services.api_auth import require_token, can_access_customer_booking
from services.booking_service import (
    get_user_role_from_db, calculate_booking_total_for_nights,
    get_refund_amount_by_hours, calculate_loyalty_tier, evaluate_occupancy_policy
)

booking_bp = Blueprint('booking_bp', __name__)


# ─── BOOKING ENDPOINTS ────────────────────────────────────────────────────────

@booking_bp.route('/api/bookings', methods=['GET'])
def api_get_bookings():
    """Lay danh sach dat phong. Uu tien ngay check-in gan nhat (gan hien tai nhat)."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_user_id = g.api_user_id
    account_type = g.api_account_type or 'customer'
    caller_role = get_user_role_from_db(caller_user_id, account_type) or 'Guest'
    status_filter = request.args.get('status', '')
    page_number = request.args.get('page', 1, type=int)
    records_per_page = request.args.get('per_page', 20, type=int)
    offset_value = (page_number - 1) * records_per_page

    conn = get_db_connection()
    cursor = conn.cursor()

    if caller_role in ('Admin', 'Manager', 'Receptionist'):
        where_clause = "WHERE 1=1"
        query_params = []
    else:
        where_clause = "WHERE nb.user_id = ?"
        query_params = [caller_user_id]

    if status_filter == 'canceled':
        where_clause += " AND nb.is_canceled = 1"
    elif status_filter == 'active':
        where_clause += " AND nb.is_canceled = 0"
    elif status_filter:
        where_clause += " AND nb.status_detail = ?"
        query_params.append(status_filter)

    cursor.execute(f"""
        SELECT nb.booking_id, nb.user_id,
               ca.email AS customer_email, ca.customer_name AS customer_full_name,
               nb.hotel_id, dh.hotel AS hotel_name,
               nb.room_type_id, drt.room_type_code,
               nb.physical_room_id, pr.room_name AS physical_room_name,
               nb.arrival_date, nb.departure_date, nb.nights,
               nb.adults, nb.children, nb.babies,
               nb.total_price, nb.deposit_paid, nb.tax_amount,
               nb.is_canceled, nb.status, nb.status_detail,
               nb.booking_type, nb.selected_nights,
               nb.promo_code, nb.discount_amount, nb.created_at
        FROM New_Bookings nb
        LEFT JOIN Customer_Accounts ca ON nb.user_id = ca.account_id
        LEFT JOIN Dim_Hotel dh ON nb.hotel_id = dh.hotel_id
        LEFT JOIN Dim_RoomType drt ON nb.room_type_id = drt.room_type_id
        LEFT JOIN Physical_Room pr ON nb.physical_room_id = pr.physical_room_id
        {where_clause}
        ORDER BY nb.arrival_date DESC, nb.created_at DESC
        LIMIT ? OFFSET ?
    """, query_params + [records_per_page, offset_value])
    bookings_list = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'bookings': bookings_list})


@booking_bp.route('/api/bookings/search', methods=['GET'])
def api_search_bookings():
    """Tim kiem booking theo email khach hang, ma booking, hoac ten khach."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_user_id = g.api_user_id
    account_type = g.api_account_type or 'staff'
    caller_role = get_user_role_from_db(caller_user_id, account_type)
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    search_keyword = request.args.get('q', '').strip()
    if not search_keyword:
        return jsonify({'success': False, 'message': 'Vui long nhap tu khoa tim kiem'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nb.booking_id, nb.user_id,
               ca.email AS customer_email, ca.customer_name AS customer_full_name,
               nb.hotel_id, dh.hotel AS hotel_name,
               nb.room_type_id, drt.room_type_code,
               nb.physical_room_id, pr.room_name AS physical_room_name,
               nb.arrival_date, nb.departure_date, nb.nights,
               nb.total_price, nb.deposit_paid, nb.status_detail,
               nb.booking_type, nb.selected_nights, nb.is_canceled, nb.special_requests
        FROM New_Bookings nb
        LEFT JOIN Customer_Accounts ca ON nb.user_id = ca.account_id
        LEFT JOIN Dim_Hotel dh ON nb.hotel_id = dh.hotel_id
        LEFT JOIN Dim_RoomType drt ON nb.room_type_id = drt.room_type_id
        LEFT JOIN Physical_Room pr ON nb.physical_room_id = pr.physical_room_id
        WHERE ca.email LIKE ? OR ca.customer_name LIKE ? OR CAST(nb.booking_id AS TEXT) = ?
        ORDER BY nb.arrival_date DESC
        LIMIT 20
    """, (f'%{search_keyword}%', f'%{search_keyword}%', search_keyword))
    found_bookings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'bookings': found_bookings})


@booking_bp.route('/api/bookings/active', methods=['GET'])
def api_get_active_bookings():
    """Lấy danh sách các booking đang và sắp sửa lưu trú (cho Lễ tân)."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_user_id = g.api_user_id
    account_type = g.api_account_type or 'staff'
    caller_role = get_user_role_from_db(caller_user_id, account_type)
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Không có quyền'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nb.booking_id, nb.user_id,
               ca.email AS customer_email, ca.customer_name AS customer_full_name,
               nb.hotel_id, dh.hotel AS hotel_name,
               nb.room_type_id, drt.room_type_code,
               nb.physical_room_id, pr.room_name AS physical_room_name,
               nb.arrival_date, nb.departure_date, nb.nights,
               nb.total_price, nb.deposit_paid, nb.status_detail,
               nb.booking_type, nb.selected_nights, nb.is_canceled, nb.special_requests
        FROM New_Bookings nb
        LEFT JOIN Customer_Accounts ca ON nb.user_id = ca.account_id
        LEFT JOIN Dim_Hotel dh ON nb.hotel_id = dh.hotel_id
        LEFT JOIN Dim_RoomType drt ON nb.room_type_id = drt.room_type_id
        LEFT JOIN Physical_Room pr ON nb.physical_room_id = pr.physical_room_id
        WHERE nb.status_detail NOT IN ('Canceled', 'Checked-Out', 'No-Show')
        ORDER BY nb.arrival_date ASC
    """)
    active_bookings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'active_bookings': active_bookings})


@booking_bp.route('/api/bookings/invoice/<int:booking_id>', methods=['GET'])
def api_get_invoice(booking_id):
    """Lấy chi tiết hóa đơn của một booking."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nb.*, 
               ca.customer_name as customer_full_name, 
               ca.customer_name,
               ca.email as customer_email,
               drt.room_type_code, 
               dh.hotel as hotel_name, 
               pr.room_name as physical_room_name
        FROM New_Bookings nb
        LEFT JOIN Customer_Accounts ca ON nb.user_id = ca.account_id
        LEFT JOIN Dim_RoomType drt ON nb.room_type_id = drt.room_type_id
        LEFT JOIN Dim_Hotel dh ON nb.hotel_id = dh.hotel_id
        LEFT JOIN Physical_Room pr ON nb.physical_room_id = pr.physical_room_id
        WHERE nb.booking_id = ?
    """, (booking_id,))
    booking = cursor.fetchone()
    if not booking:
        conn.close()
        return jsonify({'success': False, 'message': 'Không tìm thấy booking'}), 404
    if not can_access_customer_booking(booking['user_id']):
        conn.close()
        return jsonify({'success': False, 'message': 'Khong co quyen xem hoa don nay'}), 403

    cursor.execute("SELECT * FROM Extra_Services WHERE booking_id = ?", (booking_id,))
    extra_services = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM Payments WHERE booking_id = ?", (booking_id,))
    payments = [dict(row) for row in cursor.fetchall()]

    extra_grand_total = sum(s['total_price'] for s in extra_services)

    conn.close()
    return jsonify({
        'success': True,
        'booking': dict(booking),
        'extra_services': extra_services,
        'payments': payments,
        'extra_grand_total': extra_grand_total
    })


@booking_bp.route('/api/bookings', methods=['POST'])
def api_create_booking():
    """Tao booking moi sau khi payment thanh cong. Xoa Room_Lock tuong ung."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    if (g.api_account_type or '') != 'customer':
        return jsonify({'success': False, 'message': 'Chi tai khoan khach hang duoc dat qua kenh nay'}), 403
    customer_user_id = g.api_user_id
    data = request.get_json()
    hotel_id = data.get('hotel_id')
    room_type_id = data.get('room_type_id')
    physical_room_id = data.get('physical_room_id')
    booking_type = data.get('booking_type', 'continuous')
    checkin_date_str = data.get('checkin_date', '')
    checkout_date_str = data.get('checkout_date', '')
    selected_nights_str = data.get('selected_nights', '')
    number_of_adults = data.get('adults', 1)
    number_of_children = data.get('children', 0)
    number_of_babies = data.get('babies', 0)
    promo_code = data.get('promo_code', '').strip().upper()
    payment_type = data.get('payment_type', 'full')
    payment_method = data.get('payment_method', 'credit_card')
    special_requests = data.get('special_requests', '').strip()
    extra_services = data.get('extra_services', []) # list of catalog_ids
    source_channel = (data.get('source_channel') or 'direct').strip() or 'direct'
    utm_campaign = (data.get('utm_campaign') or '').strip()
    utm_medium = (data.get('utm_medium') or '').strip()

    if not all([customer_user_id, hotel_id, room_type_id, physical_room_id]):
        return jsonify({'success': False, 'message': 'Thieu thong tin dat phong'}), 400

    # Date integrity validation
    if booking_type == 'continuous':
        try:
            ci_dt = datetime.strptime(checkin_date_str, '%Y-%m-%d').date()
            co_dt = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
            if ci_dt >= co_dt:
                return jsonify({'success': False, 'message': 'Ngay nhan phong phai truoc ngay tra phong'}), 400
        except ValueError:
            return jsonify({'success': False, 'message': 'Dinh dang ngay khong hop le'}), 400
    if int(number_of_adults) <= 0:
        return jsonify({'success': False, 'message': 'So nguoi lon phai lon hon 0'}), 400

    conn = get_db_connection()
    # New_Bookings và Payments có FK references Users(user_id) từ dataset gốc,
    # nhưng khách hàng web dùng Customer_Accounts.account_id → tắt FK tạm thời.
    conn.execute("PRAGMA foreign_keys=OFF")
    cursor = conn.cursor()

    # Zombie cart check: Room_Lock phai con hieu luc tai thoi diem thanh toan
    cursor.execute(
        "SELECT lock_id FROM Room_Lock WHERE physical_room_id = ? AND locked_until > ?",
        (physical_room_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Phien giu phong da het han. Vui long chon phong va dat lai.'}), 400

    cursor.execute("SELECT room_type_code, base_price FROM Dim_RoomType WHERE room_type_id = ?", (room_type_id,))
    room_type_row = cursor.fetchone()
    if not room_type_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Loai phong khong ton tai'}), 404
    room_type_code = room_type_row['room_type_code']

    # Tinh so dem va gia tien
    if booking_type == 'continuous':
        checkin_date_obj = datetime.strptime(checkin_date_str, '%Y-%m-%d').date()
        checkout_date_obj = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
        number_of_nights = (checkout_date_obj - checkin_date_obj).days
        list_of_nights = []
        current_night = checkin_date_obj
        while current_night < checkout_date_obj:
            list_of_nights.append(current_night.strftime('%Y-%m-%d'))
            current_night += timedelta(days=1)
    else:
        list_of_nights = [n.strip() for n in selected_nights_str.split(',') if n.strip()]
        list_of_nights.sort()
        number_of_nights = len(list_of_nights)
        checkin_date_str = list_of_nights[0] if list_of_nights else ''
        checkout_date_str = (datetime.strptime(list_of_nights[-1], '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d') if list_of_nights else ''

    cursor.execute("SELECT membership_tier FROM Customer_Accounts WHERE account_id = ?", (customer_user_id,))
    tier_row = cursor.fetchone()
    membership_tier = tier_row['membership_tier'] if tier_row and tier_row['membership_tier'] else 'Newbie'

    total_effective_price, total_promo_price = calculate_booking_total_for_nights(
        cursor, room_type_id, room_type_code, list_of_nights, membership_tier, hotel_id, number_of_adults, number_of_children
    )
    if total_promo_price is None:
        conn.close()
        return jsonify({'success': False, 'message': 'So luong nguoi khong phu hop chinh sach phong (child sharing/extra bed)'}), 400

    # Kiem tra va ap ma khuyen mai them (neu co ma cu the)
    discount_amount = quantize_money(0)
    final_total_price = quantize_money(total_promo_price)
    if promo_code:
        cursor.execute("""
            SELECT discount_percent, discount_type, max_uses, current_uses, membership_tier_required
            FROM Promotions
            WHERE code = ? AND active = 1
              AND (start_date IS NULL OR start_date <= ?)
              AND (end_date IS NULL OR end_date >= ?)
              AND (max_uses = 0 OR current_uses < max_uses)
        """, (promo_code, checkin_date_str, checkin_date_str))
        promo_row = cursor.fetchone()
        if promo_row:
            # check membership tier requirement
            tier_rank = {'Newbie': 0, 'Silver': 1, 'Gold': 2}
            if tier_rank.get(membership_tier, 0) < tier_rank.get(promo_row['membership_tier_required'] or 'Newbie', 0):
                promo_row = None
        if promo_row:
            if promo_row['discount_type'] == 'fixed':
                discount_amount = quantize_money(min(promo_row['discount_percent'], float(final_total_price)))
            else:
                discount_amount = quantize_money(final_total_price * quantize_money(promo_row['discount_percent']) / 100)
            final_total_price = quantize_money(final_total_price - discount_amount)
            cursor.execute("UPDATE Promotions SET current_uses = COALESCE(current_uses, 0) + 1 WHERE code = ?", (promo_code,))

    tax_rate = DEFAULT_TAX_RATE
    tax_amount = quantize_money(final_total_price * quantize_money(tax_rate))
    final_total_with_tax = quantize_money(final_total_price + tax_amount)

    deposit_paid = quantize_money(final_total_with_tax * quantize_money("0.5")) if payment_type == 'deposit' else final_total_with_tax
    total_price_cents = to_cents(final_total_with_tax)
    tax_amount_cents = to_cents(tax_amount)
    discount_amount_cents = to_cents(discount_amount)
    deposit_paid_cents = to_cents(deposit_paid)

    try:
        cursor.execute("""
            INSERT INTO New_Bookings
                (user_id, hotel_id, room_type_id, physical_room_id, booking_type, selected_nights,
                 arrival_date, departure_date, nights, adults, children, babies,
                 total_price, total_price_cents,
                 discount_amount, discount_amount_cents,
                 promo_code,
                 tax_amount, tax_amount_cents,
                 deposit_paid, deposit_paid_cents,
                status, status_detail, is_canceled, special_requests,
                source_channel, utm_campaign, utm_medium)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 'Confirmed', 0, ?, ?, ?, ?)
        """, (customer_user_id, hotel_id, room_type_id, physical_room_id, booking_type, selected_nights_str,
              checkin_date_str, checkout_date_str, number_of_nights,
              number_of_adults, number_of_children, number_of_babies,
              float(final_total_with_tax), total_price_cents,
              float(discount_amount), discount_amount_cents,
              promo_code,
              float(tax_amount), tax_amount_cents,
              float(deposit_paid), deposit_paid_cents,
              special_requests, source_channel, utm_campaign, utm_medium))
        new_booking_id = cursor.lastrowid
        invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{new_booking_id:06d}"
        cursor.execute("UPDATE New_Bookings SET invoice_number = ?, invoice_issued_at = datetime('now') WHERE booking_id = ?", (invoice_number, new_booking_id))

        # Lưu chuẩn hoá các đêm đã đặt
        cursor.executemany(
            "INSERT OR IGNORE INTO Booking_Nights (booking_id, physical_room_id, night_date) VALUES (?, ?, ?)",
            [(new_booking_id, physical_room_id, d) for d in list_of_nights],
        )

        # Add extra services
        if extra_services:
            for cat_id in extra_services:
                cursor.execute("SELECT item_name, default_price FROM Service_Catalog WHERE catalog_id = ?", (cat_id,))
                cat_item = cursor.fetchone()
                if cat_item:
                    unit_price = cat_item['default_price']
                    unit_price_cents = to_cents(unit_price)
                    cursor.execute("""
                        INSERT INTO Extra_Services (booking_id, service_name, quantity, unit_price, unit_price_cents, total_price, total_price_cents, added_by)
                        VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                    """, (
                        new_booking_id,
                        cat_item['item_name'],
                        float(unit_price),
                        unit_price_cents,
                        float(unit_price),
                        unit_price_cents,
                        customer_user_id,
                    ))

        # Ghi nhan thanh toan
        cursor.execute("""
            INSERT INTO Payments (booking_id, user_id, amount, amount_cents, payment_method, payment_status, payment_date)
            VALUES (?, ?, ?, ?, ?, 'completed', ?)
        """, (new_booking_id, customer_user_id, float(deposit_paid), deposit_paid_cents, payment_method,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        # Xoa Room_Lock cho phong nay
        booking_temp_ref_pattern = f"TEMP_%_{physical_room_id}"
        cursor.execute("DELETE FROM Room_Lock WHERE physical_room_id = ? AND session_id LIKE '%'", (physical_room_id,))

        conn.commit()
    except Exception as e:
        conn.rollback()
        import traceback
        err_detail = traceback.format_exc()
        print(f"[ERROR CreateBooking] {e}\n{err_detail}")
        return jsonify({'success': False, 'message': f'Lỗi xử lý dữ liệu: {str(e)}'}), 500
    finally:
        conn.close()
    return jsonify({
        'success': True, 'booking_id': new_booking_id,
        'total_price': float(final_total_with_tax), 'deposit_paid': float(deposit_paid),
        'discount_amount': float(discount_amount), 'tax_amount': float(tax_amount),
        'invoice_number': invoice_number,
    })


@booking_bp.route('/api/bookings/walkin', methods=['POST'])
def api_create_walkin_booking():
    """Le tan tao booking truc tiep tai quay cho khach hang."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json()

    customer_name = data.get('customer_name', '').strip()
    customer_phone = data.get('customer_phone', '').strip()
    
    hotel_id = data.get('hotel_id')
    room_type_id = data.get('room_type_id')
    physical_room_id = data.get('physical_room_id')
    checkin_date_str = data.get('checkin_date', '')
    checkout_date_str = data.get('checkout_date', '')
    number_of_adults = data.get('adults', 1)
    
    deposit_paid = data.get('deposit_paid', 0.0)
    payment_method = data.get('payment_method', 'cash')
    
    if not customer_name or not customer_phone or not physical_room_id:
         return jsonify({'success': False, 'message': 'Thieu thong tin bat buoc'}), 400

    # Date integrity validation
    try:
        ci_dt = datetime.strptime(checkin_date_str, '%Y-%m-%d').date()
        co_dt = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
        if ci_dt >= co_dt:
            return jsonify({'success': False, 'message': 'Ngay nhan phong phai truoc ngay tra phong'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': 'Dinh dang ngay khong hop le'}), 400
    if int(number_of_adults) <= 0:
        return jsonify({'success': False, 'message': 'So nguoi lon phai lon hon 0'}), 400

    conn = get_db_connection()
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        cursor = conn.cursor()

        # 1. Xu ly tai khoan khach (Tao hoac tai su dung)
        fake_email = f"{customer_phone}@walkin.local"
        cursor.execute("SELECT account_id FROM Customer_Accounts WHERE email = ?", (fake_email,))
        customer_row = cursor.fetchone()
        if customer_row:
            customer_user_id = customer_row['account_id']
        else:
            # Tao tai khoan moi
            password_hash = generate_password_hash('walkin_123')
            try:
                cursor.execute("""
                    INSERT INTO Customer_Accounts (email, password_hash, customer_name)
                    VALUES (?, ?, ?)
                """, (fake_email, password_hash, customer_name))
                customer_user_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                conn.close()
                return jsonify({'success': False, 'message': 'Loi tao tai khoan khach vang lai'}), 500

        # 2. Tinh tien (nhanh, vi dat lien tuc)
        cursor.execute("SELECT room_type_code FROM Dim_RoomType WHERE room_type_id = ?", (room_type_id,))
        room_type_row = cursor.fetchone()
        if not room_type_row:
             return jsonify({'success': False, 'message': 'Loai phong khong hop le'}), 404
        room_type_code = room_type_row['room_type_code']

        checkin_date_obj = datetime.strptime(checkin_date_str, '%Y-%m-%d').date()
        checkout_date_obj = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
        number_of_nights = (checkout_date_obj - checkin_date_obj).days
        
        list_of_nights = []
        current_night = checkin_date_obj
        while current_night < checkout_date_obj:
            list_of_nights.append(current_night.strftime('%Y-%m-%d'))
            current_night += timedelta(days=1)

        cursor.execute("SELECT membership_tier FROM Customer_Accounts WHERE account_id = ?", (customer_user_id,))
        tier_row = cursor.fetchone()
        membership_tier = tier_row['membership_tier'] if tier_row and tier_row['membership_tier'] else 'Newbie'
        occupancy_eval = evaluate_occupancy_policy(cursor, room_type_id, number_of_adults, 0)
        if not occupancy_eval.get('allowed'):
            return jsonify({'success': False, 'message': 'So luong nguoi lon vuot qua suc chua extra bed cua phong'}), 400
        _, total_promo_price = calculate_booking_total_for_nights(
            cursor, room_type_id, room_type_code, list_of_nights, membership_tier, hotel_id, number_of_adults, 0
        )
        tax_amount = quantize_money(quantize_money(total_promo_price) * quantize_money(DEFAULT_TAX_RATE))
        final_total_with_tax = quantize_money(quantize_money(total_promo_price) + tax_amount)
        total_price_cents = to_cents(final_total_with_tax)
        tax_amount_cents = to_cents(tax_amount)
        deposit_paid_cents = to_cents(deposit_paid)

        # 3. Kiem tra xem co the tiep nhan khach vao o luon khong (Check-in ngay)
        today_str = date.today().strftime('%Y-%m-%d')
        if checkin_date_str == today_str:
            status = 'checked_in'
            status_detail = 'Checked-In'
            new_hk_status = 'Occupied'
        else:
            status = 'confirmed'
            status_detail = 'Confirmed'
            new_hk_status = None

        # 4. Insert Booking
        cursor.execute("""
            INSERT INTO New_Bookings
                (user_id, hotel_id, room_type_id, physical_room_id, booking_type, selected_nights,
                 arrival_date, departure_date, nights, adults, children, babies,
                 total_price, total_price_cents,
                 discount_amount, discount_amount_cents,
                 promo_code,
                 tax_amount, tax_amount_cents,
                 deposit_paid, deposit_paid_cents,
                status, status_detail, is_canceled,
                source_channel)
            VALUES (?, ?, ?, ?, 'continuous', '', ?, ?, ?, ?, 0, 0, ?, ?, 0, 0, '', ?, ?, ?, ?, ?, ?, 0, ?)
        """, (customer_user_id, hotel_id, room_type_id, physical_room_id,
              checkin_date_str, checkout_date_str, number_of_nights, number_of_adults,
              float(final_total_with_tax), total_price_cents,
              float(tax_amount), tax_amount_cents,
              float(deposit_paid), deposit_paid_cents,
              status, status_detail, 'walkin'))
        new_booking_id = cursor.lastrowid
        invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{new_booking_id:06d}"
        cursor.execute("UPDATE New_Bookings SET invoice_number = ?, invoice_issued_at = datetime('now') WHERE booking_id = ?", (invoice_number, new_booking_id))

        cursor.executemany(
            "INSERT OR IGNORE INTO Booking_Nights (booking_id, physical_room_id, night_date) VALUES (?, ?, ?)",
            [(new_booking_id, physical_room_id, d) for d in list_of_nights],
        )

        # 5. Ghi nhan thanh toan (coc hoac tra het)
        if float(deposit_paid) > 0:
            cursor.execute("""
                INSERT INTO Payments (booking_id, user_id, amount, amount_cents, payment_method, payment_status, payment_date)
                VALUES (?, ?, ?, ?, ?, 'completed', ?)
            """, (new_booking_id, customer_user_id, float(deposit_paid), deposit_paid_cents, payment_method,
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        # 6. Cap nhat trang thai phong vat ly
        if new_hk_status:
            cursor.execute("UPDATE Physical_Room SET housekeeping_status = ? WHERE physical_room_id = ?",
                           (new_hk_status, physical_room_id))

        conn.commit()
        return jsonify({
            'success': True, 'booking_id': new_booking_id,
            'status_detail': status_detail, 'total_price': float(final_total_with_tax)
        })
    except Exception as e:
        conn.rollback()
        import traceback
        print(f"[ERROR Walkin] {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Lỗi xử lý dữ liệu: {str(e)}'}), 500
    finally:
        conn.close()


@booking_bp.route('/api/bookings/cancel-preview/<int:booking_id>', methods=['GET'])
def api_cancel_preview(booking_id):
    """Xem truoc phi huy phong truoc khi xac nhan huy."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nb.booking_id, nb.user_id, nb.arrival_date, nb.total_price, nb.deposit_paid,
               nb.status_detail, nb.is_canceled, ca.customer_name
        FROM New_Bookings nb
        LEFT JOIN Customer_Accounts ca ON nb.user_id = ca.account_id
        WHERE nb.booking_id = ?
    """, (booking_id,))
    booking_row = cursor.fetchone()
    if not booking_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay booking'}), 404
    if not can_access_customer_booking(booking_row['user_id']):
        conn.close()
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    if booking_row['status_detail'] in ('Canceled', 'No-Show', 'Checked-Out'):
        conn.close()
        return jsonify({'success': False, 'message': 'Booking nay khong the huy'}), 400

    refund_percent, refund_amount = get_refund_amount_by_hours(
        conn, booking_row['arrival_date'], booking_row['deposit_paid']
    )
    penalty_amount = round(booking_row['deposit_paid'] - refund_amount, 2)
    conn.close()
    return jsonify({
        'success': True,
        'booking_id': booking_id,
        'arrival_date': booking_row['arrival_date'],
        'total_price': booking_row['total_price'],
        'deposit_paid': booking_row['deposit_paid'],
        'refund_percent': refund_percent,
        'refund_amount': refund_amount,
        'penalty_amount': penalty_amount,
        'customer_name': booking_row['customer_name']
    })


@booking_bp.route('/api/bookings/<int:booking_id>/cancel', methods=['PUT'])
def api_cancel_booking(booking_id):
    """Huy booking voi chinh sach hoan tien. Ho tro huy tu khach hang lan le tan."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_user_id = g.api_user_id
    account_type = g.api_account_type or 'customer'
    caller_role = get_user_role_from_db(caller_user_id, account_type) or 'Guest'
    data = request.get_json() or {}
    cancel_reason = data.get('cancel_reason', 'Khach hang yeu cau huy')
    override_penalty_amount = data.get('override_penalty')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nb.booking_id, nb.user_id, nb.arrival_date, nb.total_price, nb.deposit_paid,
               nb.status_detail, nb.physical_room_id, nb.booking_type, nb.selected_nights
        FROM New_Bookings nb WHERE nb.booking_id = ?
    """, (booking_id,))
    booking_row = cursor.fetchone()

    if not booking_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay booking'}), 404

    if caller_role == 'Guest' and booking_row['user_id'] != caller_user_id:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong co quyen huy booking nay'}), 403

    if booking_row['status_detail'] not in ('Confirmed', 'Pending'):
        conn.close()
        return jsonify({'success': False, 'message': 'Chi co the huy booking o trang thai Confirmed hoac Pending'}), 400

    refund_percent, refund_amount = get_refund_amount_by_hours(
        conn, booking_row['arrival_date'], booking_row['deposit_paid']
    )

    if override_penalty_amount is not None and caller_role in ('Receptionist', 'Manager', 'Admin'):
        refund_amount = round(booking_row['deposit_paid'] - float(override_penalty_amount), 2)

    try:
        cursor.execute("""
            UPDATE New_Bookings
            SET status_detail = 'Canceled', is_canceled = 1, status = 'canceled',
                cancel_reason = ?, canceled_by = ?
            WHERE booking_id = ?
        """, (cancel_reason, caller_user_id, booking_id))

        if booking_row['physical_room_id']:
            cursor.execute("""
                UPDATE Physical_Room SET housekeeping_status = 'Dirty'
                WHERE physical_room_id = ? AND housekeeping_status = 'Occupied'
            """, (booking_row['physical_room_id'],))

        cursor.execute("""
            INSERT INTO Payments (booking_id, user_id, amount, amount_cents, payment_method, payment_status, payment_date)
            VALUES (?, ?, ?, ?, 'refund', 'pending', ?)
        """, (booking_id, booking_row['user_id'], -refund_amount, to_cents(-refund_amount),
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR CancelBooking] {e}")
        return jsonify({'success': False, 'message': 'Hủy booking thất bại do lỗi giao dịch.'}), 500
    finally:
        conn.close()
    return jsonify({
        'success': True, 'message': 'Huy booking thanh cong',
        'refund_percent': refund_percent, 'refund_amount': refund_amount
    })


@booking_bp.route('/api/bookings/<int:booking_id>/partial-cancel', methods=['PUT'])
def api_partial_cancel_booking(booking_id):
    """Huy ngat quang: cap nhat ngay checkout moi (cat bot dem cuoi)."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_user_id = g.api_user_id
    account_type = g.api_account_type or 'staff'
    caller_role = get_user_role_from_db(caller_user_id, account_type)
    data = request.get_json() or {}
    if caller_role not in ('Receptionist', 'Manager', 'Admin', 'Guest'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    new_checkout_date_str = data.get('new_checkout_date', '')
    if not new_checkout_date_str:
        return jsonify({'success': False, 'message': 'Vui long cung cap ngay checkout moi'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT booking_id, user_id, arrival_date, departure_date, total_price, deposit_paid,
               room_type_id, physical_room_id, status_detail, adults, children
        FROM New_Bookings WHERE booking_id = ?
    """, (booking_id,))
    booking_row = cursor.fetchone()
    if not booking_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay booking'}), 404
    if caller_role == 'Guest' and booking_row['user_id'] != g.api_user_id:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    old_checkout_date_obj = datetime.strptime(booking_row['departure_date'], '%Y-%m-%d').date()
    new_checkout_date_obj = datetime.strptime(new_checkout_date_str, '%Y-%m-%d').date()
    if new_checkout_date_obj >= old_checkout_date_obj:
        conn.close()
        return jsonify({'success': False, 'message': 'Ngay checkout moi phai truoc ngay checkout cu'}), 400

    cursor.execute("SELECT room_type_code FROM Dim_RoomType WHERE room_type_id = ?", (booking_row['room_type_id'],))
    room_type_code = cursor.fetchone()['room_type_code']

    # Tinh lai so dem va tien
    checkin_date_obj = datetime.strptime(booking_row['arrival_date'], '%Y-%m-%d').date()
    new_nights_list = []
    current = checkin_date_obj
    while current < new_checkout_date_obj:
        new_nights_list.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    cursor.execute("SELECT membership_tier FROM Customer_Accounts WHERE account_id = ?", (booking_row['user_id'],))
    tier_row = cursor.fetchone()
    membership_tier = tier_row['membership_tier'] if tier_row and tier_row['membership_tier'] else 'Newbie'
    cursor.execute("SELECT hotel_id FROM New_Bookings WHERE booking_id = ?", (booking_id,))
    hrow = cursor.fetchone()
    booking_hotel_id = hrow['hotel_id'] if hrow and hrow['hotel_id'] else 1
    _, new_total_promo_price = calculate_booking_total_for_nights(
        cursor,
        booking_row['room_type_id'],
        room_type_code,
        new_nights_list,
        membership_tier,
        booking_hotel_id,
        booking_row['adults'] if booking_row['adults'] is not None else 1,
        booking_row['children'] if booking_row['children'] is not None else 0
    )
    new_tax = round(new_total_promo_price * DEFAULT_TAX_RATE, 2)
    new_total_with_tax = round(new_total_promo_price + new_tax, 2)
    price_difference = round(booking_row['total_price'] - new_total_with_tax, 2)

    try:
        cursor.execute("""
            UPDATE New_Bookings
            SET departure_date = ?, nights = ?, total_price = ?, tax_amount = ?
            WHERE booking_id = ? AND is_canceled = 0
        """, (new_checkout_date_str, len(new_nights_list), new_total_with_tax, new_tax, booking_id))

        # Cập nhật Booking_Nights: giữ lại các đêm < new_checkout_date
        cursor.execute(
            "DELETE FROM Booking_Nights WHERE booking_id = ? AND night_date >= ?",
            (booking_id, new_checkout_date_str),
        )

        if price_difference > 0:
            cursor.execute("""
                INSERT INTO Payments (booking_id, user_id, amount, amount_cents, payment_method, payment_status, payment_date)
                VALUES (?, ?, ?, ?, 'refund', 'pending', ?)
            """, (booking_id, booking_row['user_id'], -price_difference, to_cents(-price_difference),
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR EarlyCheckout] {e}")
        return jsonify({'success': False, 'message': 'Giao dịch trả phòng sớm thất bại.'}), 500
    finally:
        conn.close()
    return jsonify({
        'success': True, 'new_checkout_date': new_checkout_date_str,
        'new_total_price': new_total_with_tax, 'refund_difference': price_difference
    })


@booking_bp.route('/api/bookings/<int:booking_id>/checkin', methods=['PUT'])
def api_checkin(booking_id):
    """Le tan thuc hien check-in: cap nhat trang thai booking va phong vat ly."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nb.booking_id, nb.physical_room_id, nb.status_detail, nb.arrival_date, pr.housekeeping_status
        FROM New_Bookings nb
        LEFT JOIN Physical_Room pr ON nb.physical_room_id = pr.physical_room_id
        WHERE nb.booking_id = ?
    """, (booking_id,))
    booking_row = cursor.fetchone()
    
    if not booking_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay booking'}), 404

    # Rules Check
    today_str = date.today().strftime('%Y-%m-%d')
    if today_str < booking_row['arrival_date']:
        conn.close()
        return jsonify({'success': False, 'message': 'Chưa tới ngày check-in của booking này!'}), 400
        
    if booking_row['physical_room_id'] and booking_row['housekeeping_status'] != 'Clean':
        conn.close()
        return jsonify({'success': False, 'message': 'Không thể giao khóa! Phòng chưa ở trạng thái Sạch (Clean).'}), 400

    try:
        cursor.execute("""
            UPDATE New_Bookings SET status_detail = 'Checked-In', status = 'checked_in'
            WHERE booking_id = ? AND is_canceled = 0
        """, (booking_id,))

        if booking_row['physical_room_id']:
            cursor.execute("""
                UPDATE Physical_Room SET housekeeping_status = 'Occupied'
                WHERE physical_room_id = ?
            """, (booking_row['physical_room_id'],))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR Checkin] {e}")
        return jsonify({'success': False, 'message': 'Check-in thất bại do lỗi giao dịch.'}), 500
    finally:
        conn.close()
    return jsonify({'success': True, 'message': 'Check-in thanh cong'})


@booking_bp.route('/api/bookings/<int:booking_id>/checkout', methods=['PUT'])
def api_checkout(booking_id):
    """Le tan thuc hien check-out: tinh tong tien, cap nhat trang thai."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nb.booking_id, nb.user_id, nb.total_price, nb.deposit_paid,
               nb.physical_room_id, nb.nights, nb.status_detail
        FROM New_Bookings nb WHERE nb.booking_id = ?
    """, (booking_id,))
    booking_row = cursor.fetchone()
    if not booking_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay booking'}), 404

    # Tinh tong tien dich vu phat sinh
    cursor.execute("""
        SELECT COALESCE(SUM(total_price), 0) as extra_total
        FROM Extra_Services WHERE booking_id = ?
    """, (booking_id,))
    extra_services_total = cursor.fetchone()['extra_total']

    total_outstanding = round(booking_row['total_price'] + extra_services_total - booking_row['deposit_paid'], 2)

    try:
        cursor.execute("""
            UPDATE New_Bookings SET status_detail = 'Checked-Out', status = 'checked_out'
            WHERE booking_id = ? AND is_canceled = 0 AND status_detail = 'Checked-In'
        """, (booking_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            return jsonify({'success': False, 'message': 'Booking khong o trang thai Checked-In hoac da bi huy'}), 400

        if booking_row['physical_room_id']:
            cursor.execute("""
                UPDATE Physical_Room SET housekeeping_status = 'Dirty'
                WHERE physical_room_id = ?
            """, (booking_row['physical_room_id'],))

        # Cap nhat loyalty points
        cursor.execute("SELECT loyalty_points FROM Customer_Accounts WHERE account_id = ?", (booking_row['user_id'],))
        customer_loyalty_row = cursor.fetchone()
        if customer_loyalty_row is not None:
            new_loyalty_points = (customer_loyalty_row['loyalty_points'] or 0) + booking_row['nights'] * 10
            new_tier = calculate_loyalty_tier(new_loyalty_points)
            cursor.execute("""
                UPDATE Customer_Accounts SET loyalty_points = ?, membership_tier = ? WHERE account_id = ?
            """, (new_loyalty_points, new_tier, booking_row['user_id']))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR Checkout] {e}")
        return jsonify({'success': False, 'message': 'Check-out thất bại do lỗi giao dịch.'}), 500
    finally:
        conn.close()
    return jsonify({
        'success': True, 'message': 'Check-out thanh cong',
        'extra_services_total': extra_services_total,
        'total_outstanding': total_outstanding
    })


@booking_bp.route('/api/bookings/<int:booking_id>/noshow', methods=['PUT'])
def api_mark_noshow(booking_id):
    """Le tan xac nhan khach khong den (No-Show)."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE New_Bookings SET status_detail = 'No-Show', is_canceled = 1, status = 'canceled',
               cancel_reason = 'Khach khong den (No-Show)'
        WHERE booking_id = ? AND status_detail = 'Confirmed'
    """, (booking_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Da danh dau No-Show'})


@booking_bp.route('/api/bookings/<int:booking_id>/extra-services', methods=['GET'])
def api_get_extra_services(booking_id):
    """Lay danh sach dich vu phat sinh cua mot booking kem theo canh bao tra phong tre."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM New_Bookings WHERE booking_id = ?", (booking_id,))
    own = cursor.fetchone()
    if not own:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay booking'}), 404
    if not can_access_customer_booking(own['user_id']):
        conn.close()
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    
    # Check late checkout
    cursor.execute("SELECT departure_date, status_detail FROM New_Bookings WHERE booking_id = ?", (booking_id,))
    booking_row = cursor.fetchone()
    is_late_checkout = False
    if booking_row and booking_row['status_detail'] == 'Checked-In':
        today_str = date.today().strftime('%Y-%m-%d')
        # Neu qua ngay departure hoac dung ngay departure nhung qua 12h trua
        if today_str > booking_row['departure_date'] or (today_str == booking_row['departure_date'] and datetime.now().hour >= 12):
            is_late_checkout = True

    cursor.execute("""
        SELECT es.service_id, es.service_name, es.quantity, es.unit_price, es.total_price, es.added_at,
               u.username AS added_by_staff
        FROM Extra_Services es
        LEFT JOIN Users u ON es.added_by = u.user_id
        WHERE es.booking_id = ?
        ORDER BY es.added_at DESC
    """, (booking_id,))
    services_list = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT COALESCE(SUM(total_price), 0) as grand_total FROM Extra_Services WHERE booking_id = ?", (booking_id,))
    grand_total = cursor.fetchone()['grand_total']
    
    # Lay danh muc dich vu (Catalog)
    cursor.execute("SELECT item_name, default_price, category FROM Service_Catalog ORDER BY category, item_name")
    catalog_list = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({
        'success': True, 
        'extra_services': services_list, 
        'grand_total': grand_total,
        'is_late_checkout': is_late_checkout,
        'catalog': catalog_list
    })


@booking_bp.route('/api/bookings/<int:booking_id>/extra-services', methods=['POST'])
@booking_bp.route('/api/bookings/<int:booking_id>/extra-service', methods=['POST'])
def api_add_extra_service(booking_id):
    """Le tan them dich vu phat sinh cho mot booking."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json() or {}
    caller_user_id = g.api_user_id

    service_name = data.get('service_name', '').strip()
    quantity = data.get('quantity', 1)
    unit_price = data.get('unit_price', 0.0)
    if not service_name or unit_price <= 0:
        return jsonify({'success': False, 'message': 'Thieu ten dich vu hoac gia'}), 400

    total_price = round(quantity * unit_price, 2)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Extra_Services (booking_id, service_name, quantity, unit_price, total_price, added_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (booking_id, service_name, quantity, unit_price, total_price, caller_user_id))
    new_service_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'service_id': new_service_id, 'total_price': total_price})


@booking_bp.route('/api/noshow-check', methods=['GET'])
@booking_bp.route('/api/bookings/noshow-candidates', methods=['GET'])
def api_noshow_check():
    """Lay danh sach booking Confirmed ma ngay check-in la hom nay hoac da qua."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    today_str = date.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nb.booking_id, nb.arrival_date,
               ca.customer_name, ca.email AS customer_email,
               nb.hotel_id, dh.hotel AS hotel_name,
               drt.room_type_code, pr.room_name AS physical_room_name
        FROM New_Bookings nb
        LEFT JOIN Customer_Accounts ca ON nb.user_id = ca.account_id
        LEFT JOIN Dim_Hotel dh ON nb.hotel_id = dh.hotel_id
        LEFT JOIN Dim_RoomType drt ON nb.room_type_id = drt.room_type_id
        LEFT JOIN Physical_Room pr ON nb.physical_room_id = pr.physical_room_id
        WHERE nb.status_detail = 'Confirmed' AND nb.arrival_date <= ?
        ORDER BY nb.arrival_date ASC
    """, (today_str,))
    noshow_candidates = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'noshow_candidates': noshow_candidates})


# ─── ROOM PLAN (GANTT) ENDPOINT ───────────────────────────────────────────────

@booking_bp.route('/api/room-plan', methods=['GET'])
def api_get_room_plan():
    """Lay du lieu so do phong dang bang Gantt cho le tan (7 ngay ke tu ngay xem)."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    start_date_str = request.args.get('start_date', date.today().strftime('%Y-%m-%d'))
    start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    number_of_days = request.args.get('days', 7, type=int)

    list_of_dates = []
    for day_offset in range(number_of_days):
        list_of_dates.append((start_date_obj + timedelta(days=day_offset)).strftime('%Y-%m-%d'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pr.physical_room_id, pr.room_name, pr.housekeeping_status,
               drt.room_type_id, drt.room_type_code, drt.hotel_id, drt.base_price, dh.hotel as hotel_name
        FROM Physical_Room pr
        JOIN Dim_RoomType drt ON pr.room_type_id = drt.room_type_id
        LEFT JOIN Dim_Hotel dh ON drt.hotel_id = dh.hotel_id
        WHERE pr.is_active = 1
        ORDER BY dh.hotel_id, drt.room_type_code, pr.room_name
    """)
    all_physical_rooms = cursor.fetchall()

    end_date_str = list_of_dates[-1]
    cursor.execute("""
        SELECT nb.booking_id, nb.physical_room_id, nb.arrival_date, nb.departure_date,
               nb.selected_nights, nb.booking_type, nb.status_detail,
               ca.customer_name
        FROM New_Bookings nb
        LEFT JOIN Customer_Accounts ca ON nb.user_id = ca.account_id
        WHERE nb.status_detail NOT IN ('Canceled', 'No-Show')
          AND nb.physical_room_id IS NOT NULL
          AND (
            (nb.booking_type = 'continuous' AND nb.arrival_date <= ? AND nb.departure_date > ?)
            OR
            (nb.booking_type = 'fragmented')
          )
    """, (end_date_str, start_date_str))
    all_bookings = cursor.fetchall()

    room_plan_data = []
    for physical_room in all_physical_rooms:
        physical_room_id = physical_room['physical_room_id']
        cells_per_day = {}

        for target_date_str in list_of_dates:
            cell_status = 'empty'
            booking_info = None
            for booking_row in all_bookings:
                if booking_row['physical_room_id'] != physical_room_id:
                    continue
                if booking_row['booking_type'] == 'continuous':
                    if booking_row['arrival_date'] <= target_date_str < booking_row['departure_date']:
                        cell_status = booking_row['status_detail']
                        booking_info = {
                            'booking_id': booking_row['booking_id'],
                            'customer_name': booking_row['customer_name']
                        }
                        break
                else:
                    nights_list = [n.strip() for n in (booking_row['selected_nights'] or '').split(',') if n.strip()]
                    if target_date_str in nights_list:
                        cell_status = booking_row['status_detail']
                        booking_info = {
                            'booking_id': booking_row['booking_id'],
                            'customer_name': booking_row['customer_name']
                        }
                        break

            if cell_status == 'empty' and physical_room['housekeeping_status'] == 'Dirty':
                cell_status = 'Dirty'
            elif cell_status == 'empty' and physical_room['housekeeping_status'] == 'Maintenance':
                cell_status = 'Maintenance'

            cells_per_day[target_date_str] = {'status': cell_status, 'booking': booking_info}

        room_plan_data.append({
            'physical_room_id': physical_room_id,
            'room_name': physical_room['room_name'],
            'room_type_id': physical_room['room_type_id'],
            'room_type_code': physical_room['room_type_code'],
            'base_price': physical_room['base_price'],
            'hotel_name': physical_room['hotel_name'],
            'housekeeping_status': physical_room['housekeeping_status'],
            'cells': cells_per_day
        })

    conn.close()
    return jsonify({
        'success': True,
        'dates': list_of_dates,
        'room_plan': room_plan_data
    })


def _move_booking_room_impl(booking_id: int, new_physical_room_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT booking_id, room_type_id, physical_room_id FROM New_Bookings WHERE booking_id = ?", (booking_id,))
    booking_row = cursor.fetchone()
    cursor.execute("SELECT physical_room_id, room_type_id FROM Physical_Room WHERE physical_room_id = ?", (new_physical_room_id,))
    new_room_row = cursor.fetchone()

    if not booking_row or not new_room_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Khong tim thay booking hoac phong'}), 404

    if booking_row['room_type_id'] != new_room_row['room_type_id']:
        conn.close()
        return jsonify({'success': False, 'message': 'Chi co the doi sang phong cung loai'}), 400

    old_room_id = booking_row['physical_room_id']
    cursor.execute("UPDATE New_Bookings SET physical_room_id = ? WHERE booking_id = ?",
                   (new_physical_room_id, booking_id))
    cursor.execute(
        "UPDATE Booking_Nights SET physical_room_id = ? WHERE booking_id = ?",
        (new_physical_room_id, booking_id),
    )
    if old_room_id:
        cursor.execute("UPDATE Physical_Room SET housekeeping_status = 'Dirty' WHERE physical_room_id = ?",
                       (old_room_id,))
    cursor.execute("UPDATE Physical_Room SET housekeeping_status = 'Occupied' WHERE physical_room_id = ?",
                   (new_physical_room_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Da doi phong thanh cong'})


@booking_bp.route('/api/room-plan/move', methods=['POST'])
def api_move_booking_room():
    """Le tan doi phong vat ly cho mot booking (cung loai phong)."""
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    data = request.get_json() or {}
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403

    booking_id = data.get('booking_id')
    new_physical_room_id = data.get('new_physical_room_id')
    if not booking_id or not new_physical_room_id:
        return jsonify({'success': False, 'message': 'Thieu booking_id hoac new_physical_room_id'}), 400
    return _move_booking_room_impl(int(booking_id), int(new_physical_room_id))


@booking_bp.route('/api/bookings/<int:booking_id>/move-room', methods=['PUT'])
def api_move_booking_room_by_booking(booking_id):
    auth_err = require_token()
    if auth_err is not None:
        return auth_err
    caller_role = get_user_role_from_db(g.api_user_id, g.api_account_type or 'staff')
    if caller_role not in ('Receptionist', 'Manager', 'Admin'):
        return jsonify({'success': False, 'message': 'Khong co quyen'}), 403
    data = request.get_json() or {}
    new_physical_room_id = data.get('new_physical_room_id')
    if not new_physical_room_id:
        return jsonify({'success': False, 'message': 'Thieu new_physical_room_id'}), 400
    return _move_booking_room_impl(booking_id, int(new_physical_room_id))


