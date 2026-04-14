from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from services.api import api_get, api_post, api_put

staff_bp = Blueprint('staff', __name__)


def _require_staff(roles=('Receptionist', 'Manager', 'Admin', 'Housekeeper')):
    if not session.get('token'):
        flash('Vui lòng đăng nhập.', 'error')
        return redirect(url_for('auth.login'))
    if session.get('account_type') != 'staff':
        flash('Bạn không có quyền truy cập trang này.', 'error')
        return redirect(url_for('search.home'))
    if session.get('role') not in roles:
        flash('Bạn không đủ quyền hạn.', 'error')
        return redirect(url_for('search.home'))
    return None


# ── Receptionist Dashboard ─────────────────────────────────────────────────────

@staff_bp.route('/receptionist')
def receptionist():
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '')

    if q:
        bookings = api_get('/api/bookings/search', params={'q': q}).get('bookings', [])
    else:
        params = {'per_page': 30}
        if status:
            params['status'] = status
        bookings = api_get('/api/bookings', params=params).get('bookings', [])

    ops = api_get('/api/operations/realtime')
    catalog = api_get('/api/service-catalog').get('catalog', [])
    return render_template('receptionist.html',
                           bookings=bookings, ops=ops, catalog=catalog,
                           q=q, status=status)


@staff_bp.route('/receptionist/room-plan')
def room_plan():
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    room_types = api_get('/api/inventory/comprehensive').get('inventory', [])
    ops = api_get('/api/operations/realtime')
    # Enrich hotel_name
    hotels = api_get('/api/hotels').get('hotels', [])
    hotel_map = {h['hotel_id']: h.get('hotel_name', '') for h in hotels}
    for rt in room_types:
        rt['hotel_name'] = hotel_map.get(rt.get('hotel_id'), '')
    return render_template('receptionist_room_plan.html', room_types=room_types, ops=ops)


# ── Booking Actions ────────────────────────────────────────────────────────────

@staff_bp.route('/receptionist/checkin/<int:booking_id>', methods=['POST'])
def checkin(booking_id):
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    result = api_put(f'/api/bookings/{booking_id}/checkin', {})
    flash('Check-in thành công!' if result.get('success') else result.get('message', 'Thất bại'),
          'success' if result.get('success') else 'error')
    return redirect(url_for('staff.receptionist'))


@staff_bp.route('/receptionist/checkout/<int:booking_id>', methods=['GET', 'POST'])
def do_checkout(booking_id):
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    if request.method == 'POST':
        result = api_put(f'/api/bookings/{booking_id}/checkout', {
            'staff_id': session.get('user_id'),
        })
        flash('Check-out thành công!' if result.get('success') else result.get('message', 'Thất bại'),
              'success' if result.get('success') else 'error')
        return redirect(url_for('staff.receptionist'))

    invoice_data = api_get(f'/api/bookings/invoice/{booking_id}')
    catalog = api_get('/api/service-catalog').get('catalog', [])
    return render_template('receptionist_checkout_detail.html',
                           booking=invoice_data.get('booking') or {},
                           extra_services=invoice_data.get('extra_services', []),
                           payments=invoice_data.get('payments', []),
                           extra_grand_total=invoice_data.get('extra_grand_total', 0),
                           catalog=catalog,
                           booking_id=booking_id)


@staff_bp.route('/receptionist/noshow/<int:booking_id>', methods=['GET', 'POST'])
def noshow(booking_id):
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    if request.method == 'POST':
        result = api_put(f'/api/bookings/{booking_id}/noshow', {})
        flash('Đã đánh dấu No-Show.' if result.get('success') else result.get('message', 'Thất bại'),
              'success' if result.get('success') else 'error')
        return redirect(url_for('staff.receptionist'))
    invoice_data = api_get(f'/api/bookings/invoice/{booking_id}')
    return render_template('receptionist_noshow.html',
                           booking=invoice_data.get('booking') or {},
                           booking_id=booking_id)


@staff_bp.route('/receptionist/add-service/<int:booking_id>', methods=['POST'])
def add_service(booking_id):
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    result = api_post(f'/api/bookings/{booking_id}/extra-services', {
        'service_name': request.form.get('service_name', ''),
        'quantity': request.form.get('quantity', 1, type=int),
        'unit_price': request.form.get('unit_price', 0.0, type=float),
        'catalog_id': request.form.get('catalog_id', type=int),
    })
    flash('Đã thêm dịch vụ.' if result.get('success') else result.get('message', 'Thất bại'),
          'success' if result.get('success') else 'error')
    return redirect(url_for('staff.do_checkout', booking_id=booking_id))


@staff_bp.route('/receptionist/cancel/<int:booking_id>', methods=['GET', 'POST'])
def cancel_booking(booking_id):
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    if request.method == 'POST':
        result = api_put(f'/api/bookings/{booking_id}/cancel', {
            'cancel_reason': request.form.get('cancel_reason', '').strip(),
        })
        flash('Đã hủy đặt phòng.' if result.get('success') else result.get('message', 'Thất bại'),
              'success' if result.get('success') else 'error')
        return redirect(url_for('staff.receptionist'))
    preview = api_get(f'/api/bookings/cancel-preview/{booking_id}').get('preview') or {}
    return render_template('receptionist_cancel.html', preview=preview, booking_id=booking_id)


@staff_bp.route('/receptionist/invoice/<int:booking_id>')
def invoice(booking_id):
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    invoice_data = api_get(f'/api/bookings/invoice/{booking_id}')
    if not invoice_data.get('success'):
        flash(invoice_data.get('message', 'Không tìm thấy hóa đơn.'), 'error')
        return redirect(url_for('staff.receptionist'))
    return render_template('receptionist_invoice.html',
                           booking=invoice_data.get('booking') or {},
                           extra_services=invoice_data.get('extra_services', []),
                           payments=invoice_data.get('payments', []),
                           extra_grand_total=invoice_data.get('extra_grand_total', 0))


@staff_bp.route('/receptionist/move-room/<int:booking_id>', methods=['GET', 'POST'])
def move_room(booking_id):
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    if request.method == 'POST':
        result = api_put(f'/api/bookings/{booking_id}/move-room', {
            'new_physical_room_id': request.form.get('new_physical_room_id', type=int),
            'reason': request.form.get('reason', '').strip(),
        })
        flash('Đã chuyển phòng thành công.' if result.get('success') else result.get('message', 'Thất bại'),
              'success' if result.get('success') else 'error')
        return redirect(url_for('staff.receptionist'))
    invoice_data = api_get(f'/api/bookings/invoice/{booking_id}')
    room_types = api_get('/api/inventory/comprehensive').get('inventory', [])
    return render_template('receptionist_move_room.html',
                           booking=invoice_data.get('booking') or {},
                           room_types=room_types,
                           booking_id=booking_id)


@staff_bp.route('/receptionist/walkin', methods=['GET', 'POST'])
def walkin():
    err = _require_staff(('Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    if request.method == 'POST':
        payload = {
            'customer_name': request.form.get('customer_name', '').strip(),
            'customer_phone': request.form.get('customer_phone', '').strip(),
            'hotel_id': request.form.get('hotel_id', type=int),
            'room_type_id': request.form.get('room_type_id', type=int),
            'physical_room_id': request.form.get('physical_room_id', type=int),
            'checkin_date': request.form.get('checkin_date', ''),
            'checkout_date': request.form.get('checkout_date', ''),
            'adults': request.form.get('adults', 1, type=int),
            'children': request.form.get('children', 0, type=int),
            'deposit_paid': request.form.get('deposit_paid', 0.0, type=float),
            'payment_method': request.form.get('payment_method', 'cash'),
            'special_requests': request.form.get('special_requests', '').strip(),
        }
        print(f"[WALKIN] Payload: {payload}")
        result = api_post('/api/bookings/walkin', payload)
        print(f"[WALKIN] Result success={result.get('success')}, booking_id={result.get('booking_id')}")
        if result.get('success'):
            flash(f"Walk-in #{result.get('booking_id')} tạo thành công!", 'success')
            return redirect(url_for('staff.receptionist'))
        flash(result.get('message', 'Tạo walk-in thất bại.'), 'error')
    hotels = api_get('/api/hotels').get('hotels', [])
    room_types = api_get('/api/inventory/comprehensive').get('inventory', [])
    return render_template('receptionist_walkin_booking.html', hotels=hotels, room_types=room_types)


# ── Housekeeping ───────────────────────────────────────────────────────────────

@staff_bp.route('/housekeeping')
def housekeeping():
    err = _require_staff(('Housekeeper', 'Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    rooms = api_get('/api/housekeeping/rooms').get('rooms', [])
    ops = api_get('/api/operations/realtime')
    return render_template('housekeeping_dashboard.html', rooms=rooms, ops=ops)


@staff_bp.route('/housekeeping/clean/<int:room_id>', methods=['POST'])
def mark_clean(room_id):
    err = _require_staff(('Housekeeper', 'Receptionist', 'Manager', 'Admin'))
    if err:
        return err
    result = api_post(f'/api/housekeeping/rooms/{room_id}/clean', {})
    flash('Phòng đã được đánh dấu sạch.' if result.get('success') else result.get('message', 'Thất bại'),
          'success' if result.get('success') else 'error')
    return redirect(url_for('staff.housekeeping'))
