from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from services.api import api_get, api_post, api_put, api_delete

booking_bp = Blueprint('booking', __name__)


def _require_login():
    if not session.get('token'):
        flash('Vui lòng đăng nhập để tiếp tục.', 'error')
        return redirect(url_for('auth.login'))
    return None


def _nights_from_range(checkin_str, checkout_str):
    """Generate list of night date strings from checkin (inclusive) to checkout (exclusive)."""
    try:
        ci = date.fromisoformat(checkin_str)
        co = date.fromisoformat(checkout_str)
        nights = []
        cur = ci
        while cur < co:
            nights.append(cur.strftime('%Y-%m-%d'))
            cur += timedelta(days=1)
        return nights
    except Exception:
        return []


# ── Booking Form ───────────────────────────────────────────────────────────────

@booking_bp.route('/booking', methods=['GET', 'POST'])
def booking():
    err = _require_login()
    if err:
        return err
    if session.get('account_type') != 'customer':
        flash('Chỉ tài khoản khách hàng mới có thể đặt phòng qua kênh này.', 'error')
        return redirect(url_for('search.home'))

    hotels = api_get('/api/hotels').get('hotels', [])
    room_types = api_get('/api/dimensions/room-types').get('room_types', [])

    if request.method == 'POST':
        room_type_id = request.form.get('room_type_id', type=int)
        hotel_id = request.form.get('hotel_id', type=int)
        arrival_date = request.form.get('arrival_date', '').strip()
        departure_date = request.form.get('departure_date', '').strip()
        adults = request.form.get('adults', 1, type=int)
        children = request.form.get('children', 0, type=int)
        promo_code = request.form.get('promo_code', '').strip().upper()
        # ★ Đọc physical_room_id cụ thể từ form (truyền từ search page)
        target_physical_room_id = request.form.get('physical_room_id', type=int)

        if not all([room_type_id, arrival_date, departure_date]):
            flash('Vui lòng điền đầy đủ thông tin.', 'error')
            return render_template('booking.html', hotels=hotels, room_types=room_types,
                                   prefill_hotel_id=hotel_id,
                                   prefill_room_type_id=room_type_id,
                                   prefill_room_type_code='',
                                   prefill_physical_room_id=target_physical_room_id,
                                   checkin_prefill=arrival_date,
                                   checkout_prefill=departure_date)

        # Search available rooms
        search_data = api_get('/api/rooms/search', params={
            'checkin_date': arrival_date,
            'checkout_date': departure_date,
            'adults': adults,
            'children': children,
            'promo_code': promo_code,
        }, token=session.get('token'))

        # ★ API mới trả flat list, không phải grouped nữa
        all_rooms = search_data.get('rooms', [])

        # ★ Nếu có physical_room_id cụ thể từ search → tìm đúng phòng đó
        physical_room = None
        room_type_info = None
        booking_type = 'continuous'

        if target_physical_room_id:
            # Tìm chính xác phòng vật lý mà user đã chọn từ trang search
            matched = next((r for r in all_rooms
                           if r.get('physical_room_id') == target_physical_room_id
                           and r.get('room_type_id') == room_type_id), None)
            if matched:
                room_type_info = matched
                physical_room = {
                    'physical_room_id': matched['physical_room_id'],
                    'room_name': matched.get('room_name', ''),
                }
                booking_type = matched.get('availability_type', 'continuous')

        # Fallback: nếu không tìm thấy phòng cụ thể, lấy phòng đầu tiên cùng hạng
        if not physical_room:
            matched = next((r for r in all_rooms if r.get('room_type_id') == room_type_id), None)
            if matched:
                room_type_info = matched
                physical_room = {
                    'physical_room_id': matched['physical_room_id'],
                    'room_name': matched.get('room_name', ''),
                }
                booking_type = matched.get('availability_type', 'continuous')

        if not room_type_info or not physical_room:
            flash('Không còn phòng trống cho loại phòng và khoảng thời gian bạn chọn. Vui lòng thử lại.', 'error')
            return render_template('booking.html', hotels=hotels, room_types=room_types,
                                   prefill_hotel_id=hotel_id,
                                   prefill_room_type_id=room_type_id,
                                   prefill_room_type_code='',
                                   prefill_physical_room_id=target_physical_room_id,
                                   checkin_prefill=arrival_date,
                                   checkout_prefill=departure_date)

        physical_room_id = physical_room['physical_room_id']

        # Xác định danh sách đêm
        if booking_type == 'continuous':
            nights = _nights_from_range(arrival_date, departure_date)
        else:
            nights = room_type_info.get('free_nights', [])

        # Lock the room
        lock_data = api_post('/api/rooms/lock', {
            'physical_room_id': physical_room_id,
            'session_id': session.get('session_id', ''),
            'nights': nights,
        })

        if not lock_data.get('success'):
            flash(lock_data.get('message', 'Không thể giữ phòng. Vui lòng thử lại.'), 'error')
            return render_template('booking.html', hotels=hotels, room_types=room_types,
                                   prefill_hotel_id=hotel_id,
                                   prefill_room_type_id=room_type_id,
                                   prefill_room_type_code='',
                                   prefill_physical_room_id=target_physical_room_id,
                                   checkin_prefill=arrival_date,
                                   checkout_prefill=departure_date)

        session['booking_lock'] = {
            'physical_room_id': physical_room_id,
            'room_type_id': room_type_id,
            'room_type_code': room_type_info.get('room_type_code', ''),
            'hotel_id': hotel_id or room_type_info.get('hotel_id', 1),
            'hotel_name': room_type_info.get('hotel_name', ''),
            'checkin_date': arrival_date,
            'checkout_date': departure_date,
            'selected_nights': nights,
            'booking_type': booking_type,
            'adults': adults,
            'children': children,
            'babies': 0,
            'locked_until': lock_data.get('locked_until', ''),
            'temp_ref': lock_data.get('booking_temp_ref', ''),
            'promo_code': promo_code,
            'base_price': room_type_info.get('effective_price_max', room_type_info.get('base_price', 0)),
            'promo_price': room_type_info.get('promo_price_min', 0),
            'room_name': physical_room.get('room_name', ''),
        }

        if booking_type == 'fragmented':
            return redirect(url_for('booking.booking_fragmented'))
        return redirect(url_for('booking.booking_continuous'))

    # ── GET: Prefill từ search page ──
    prefill_room_type_id = request.args.get('room_type_id', '')
    prefill_hotel_id = request.args.get('hotel_id', '')
    prefill_physical_room_id = request.args.get('physical_room_id', '')
    prefill_room_type_code = ''
    prefill_room_name = ''
    if prefill_room_type_id:
        rt = next((r for r in room_types if str(r.get('room_type_id')) == str(prefill_room_type_id)), {})
        prefill_room_type_code = rt.get('room_type_code', '')
    # Lấy tên phòng vật lý nếu có
    if prefill_physical_room_id:
        phys_data = api_get('/api/physical-rooms', params={'room_type_id': prefill_room_type_id})
        for pr in phys_data.get('physical_rooms', []):
            if str(pr.get('physical_room_id')) == str(prefill_physical_room_id):
                prefill_room_name = pr.get('room_name', '')
                break

    return render_template('booking.html',
                           hotels=hotels,
                           room_types=room_types,
                           prefill_hotel_id=prefill_hotel_id,
                           prefill_room_type_id=prefill_room_type_id,
                           prefill_room_type_code=prefill_room_type_code,
                           prefill_physical_room_id=prefill_physical_room_id,
                           prefill_room_name=prefill_room_name,
                           checkin_prefill=request.args.get('checkin_date', ''),
                           checkout_prefill=request.args.get('checkout_date', ''))


@booking_bp.route('/booking/continuous')
def booking_continuous():
    lock = session.get('booking_lock')
    if not lock:
        return redirect(url_for('booking.booking'))
    return render_template('booking_continuous.html',
                           room_type={'room_type_code': lock.get('room_type_code', '')},
                           physical_room_id=lock.get('physical_room_id'),
                           room_name=lock.get('room_name', ''),
                           checkin_date=lock.get('checkin_date'),
                           checkout_date=lock.get('checkout_date'),
                           locked_until=lock.get('locked_until'))


@booking_bp.route('/booking/fragmented')
def booking_fragmented():
    lock = session.get('booking_lock')
    if not lock:
        return redirect(url_for('booking.booking'))
    return render_template('booking_fragmented.html',
                           room_type={'room_type_code': lock.get('room_type_code', '')},
                           physical_room_id=lock.get('physical_room_id'),
                           selected_nights=lock.get('selected_nights', []),
                           locked_until=lock.get('locked_until'))


# ── Checkout ───────────────────────────────────────────────────────────────────

@booking_bp.route('/booking/checkout', methods=['GET', 'POST'])
def checkout():
    err = _require_login()
    if err:
        return err
    lock = session.get('booking_lock')
    if not lock:
        flash('Phiên đặt phòng đã hết hạn hoặc không tồn tại.', 'error')
        return redirect(url_for('booking.booking'))

    catalog = api_get('/api/service-catalog').get('catalog', [])

    if request.method == 'POST':
        # Lưu lựa chọn checkout vào session rồi chuyển sang trang thanh toán
        session['checkout_choices'] = {
            'payment_method': request.form.get('payment_method', 'credit_card'),
            'payment_type': request.form.get('payment_type', 'full'),
            'promo_code': request.form.get('promo_code', lock.get('promo_code', '')).strip().upper(),
            'special_requests': request.form.get('special_requests', '').strip(),
            'extra_services': request.form.getlist('extra_services', type=int),
        }
        return redirect(url_for('booking.payment'))

    room_type = {
        'room_type_code': lock.get('room_type_code', ''),
        'base_price': lock.get('base_price', 0),
    }
    return render_template('checkout.html',
                           room_type=room_type,
                           checkin_date=lock.get('checkin_date'),
                           checkout_date=lock.get('checkout_date'),
                           selected_nights=','.join(lock.get('selected_nights', [])),
                           booking_type=lock.get('booking_type', 'continuous'),
                           adults=lock.get('adults', 1),
                           children=lock.get('children', 0),
                           locked_until=lock.get('locked_until'),
                           promo_code=lock.get('promo_code', ''),
                           catalog=catalog)


# ── Payment (Stripe-style) ─────────────────────────────────────────────────────

@booking_bp.route('/booking/payment', methods=['GET', 'POST'])
def payment():
    err = _require_login()
    if err:
        return err
    lock = session.get('booking_lock')
    choices = session.get('checkout_choices')
    if not lock or not choices:
        flash('Phiên đặt phòng đã hết hạn.', 'error')
        return redirect(url_for('booking.booking'))

    if request.method == 'POST':
        # Chỉ kiểm tra nhập đủ dữ liệu → thanh toán thành công
        payment_method = choices.get('payment_method', 'credit_card')
        errors = []

        if payment_method == 'credit_card':
            if not request.form.get('card_number', '').strip():
                errors.append('Vui lòng nhập số thẻ.')
            if not request.form.get('card_expiry', '').strip():
                errors.append('Vui lòng nhập ngày hết hạn.')
            if not request.form.get('card_cvc', '').strip():
                errors.append('Vui lòng nhập mã CVC.')
            if not request.form.get('card_holder', '').strip():
                errors.append('Vui lòng nhập tên chủ thẻ.')
        elif payment_method == 'bank_transfer':
            if not request.form.get('bank_name', '').strip():
                errors.append('Vui lòng chọn ngân hàng.')
            if not request.form.get('transfer_name', '').strip():
                errors.append('Vui lòng nhập tên người chuyển.')
        # cash: không cần nhập gì thêm

        if errors:
            flash(' '.join(errors), 'error')
            return redirect(url_for('booking.payment'))

        # Tạo booking
        payload = {
            'hotel_id': lock.get('hotel_id'),
            'room_type_id': lock.get('room_type_id'),
            'physical_room_id': lock.get('physical_room_id'),
            'booking_type': lock.get('booking_type', 'continuous'),
            'checkin_date': lock.get('checkin_date'),
            'checkout_date': lock.get('checkout_date'),
            'selected_nights': ','.join(lock.get('selected_nights', [])),
            'adults': lock.get('adults', 1),
            'children': lock.get('children', 0),
            'babies': lock.get('babies', 0),
            'promo_code': choices.get('promo_code', ''),
            'payment_type': choices.get('payment_type', 'full'),
            'payment_method': payment_method,
            'special_requests': choices.get('special_requests', ''),
            'extra_services': choices.get('extra_services', []),
            'source_channel': 'direct',
        }
        result = api_post('/api/bookings', payload)
        if result.get('success'):
            session.pop('booking_lock', None)
            session.pop('checkout_choices', None)
            session['last_booking'] = {
                'booking_id': result.get('booking_id'),
                'total_price': result.get('total_price'),
                'deposit_paid': result.get('deposit_paid'),
                'invoice_number': result.get('invoice_number', ''),
                'payment_type': choices.get('payment_type'),
                'payment_method': payment_method,
            }
            api_post('/api/funnel/event', {
                'event_name': 'booking_success',
                'session_id': session.get('session_id', ''),
                'booking_id': result.get('booking_id'),
            })
            return redirect(url_for('booking.payment_success'))
        flash(result.get('message', 'Thanh toán thất bại. Vui lòng thử lại.'), 'error')

    # GET: Hiển thị trang thanh toán Stripe-style
    # Tính giá
    base_price = lock.get('base_price', 0)
    nights = lock.get('selected_nights', [])
    num_nights = len(nights) if nights else 1
    subtotal = base_price * num_nights
    tax = subtotal * 0.1
    payment_type = choices.get('payment_type', 'full')
    if payment_type == 'deposit':
        total_due = (subtotal + tax) * 0.5
    else:
        total_due = subtotal + tax

    return render_template('payment.html',
                           lock=lock,
                           choices=choices,
                           base_price=base_price,
                           num_nights=num_nights,
                           subtotal=subtotal,
                           tax=tax,
                           total_due=total_due)


@booking_bp.route('/booking/release', methods=['POST'])
def release():
    lock = session.get('booking_lock')
    if lock:
        api_post('/api/rooms/lock/release', {
            'session_id': session.get('session_id', ''),
            'booking_temp_ref': lock.get('temp_ref', ''),
        })
        session.pop('booking_lock', None)
    return redirect(url_for('booking.booking'))


@booking_bp.route('/payment/success')
def payment_success():
    last = session.get('last_booking') or {}
    return render_template('payment_success.html', booking=last)


# ── History & Guest Actions ────────────────────────────────────────────────────

@booking_bp.route('/history')
def history():
    err = _require_login()
    if err:
        return err
    data = api_get('/api/bookings')
    return render_template('history.html', bookings=data.get('bookings', []))


@booking_bp.route('/loyalty')
def loyalty():
    err = _require_login()
    if err:
        return err
    uid = session.get('user_id')
    data = api_get(f'/api/loyalty/{uid}')
    return render_template('loyalty.html', loyalty=data.get('loyalty') or {})


@booking_bp.route('/cancel-preview/<int:booking_id>')
def cancel_preview(booking_id):
    err = _require_login()
    if err:
        return err
    data = api_get(f'/api/bookings/cancel-preview/{booking_id}')
    if not data.get('success'):
        flash(data.get('message', 'Không thể tải thông tin hủy phòng.'), 'error')
        return redirect(url_for('booking.history'))
    return render_template('cancel_preview.html', preview=data.get('preview') or {})


@booking_bp.route('/cancel/<int:booking_id>', methods=['POST'])
def cancel(booking_id):
    err = _require_login()
    if err:
        return err
    reason = request.form.get('cancel_reason', '').strip()
    result = api_put(f'/api/bookings/{booking_id}/cancel', {'cancel_reason': reason})
    if result.get('success'):
        flash('Đã hủy đặt phòng thành công.', 'success')
    else:
        flash(result.get('message', 'Hủy phòng thất bại.'), 'error')
    return redirect(url_for('booking.history'))


@booking_bp.route('/booking/review/<int:booking_id>', methods=['GET', 'POST'])
def review_post(booking_id):
    err = _require_login()
    if err:
        return err
    if request.method == 'POST':
        result = api_post('/api/reviews', {
            'hotel_id': request.form.get('hotel_id', type=int),
            'booking_id': booking_id,
            'rating': request.form.get('rating', type=int),
            'comment': request.form.get('comment', '').strip(),
        })
        if result.get('success'):
            flash('Cảm ơn bạn đã đánh giá!', 'success')
            return redirect(url_for('booking.history'))
        flash(result.get('message', 'Gửi đánh giá thất bại.'), 'error')
    booking_data = api_get(f'/api/bookings/invoice/{booking_id}')
    booking = booking_data.get('booking') or {}
    hotels = api_get('/api/hotels').get('hotels', [])
    return render_template('review_post.html', booking=booking, booking_id=booking_id, hotels=hotels)


# ── Cart ───────────────────────────────────────────────────────────────────────

@booking_bp.route('/cart')
def cart():
    session_id = session.get('session_id', '')
    data = api_get('/api/cart', params={'session_id': session_id})
    catalog = api_get('/api/service-catalog').get('catalog', [])
    cart_items = data.get('items', [])
    locks = [item.get('locked_until', '') for item in cart_items if item.get('locked_until')]
    earliest_lock_expiry = min(locks) if locks else None
    return render_template('cart.html',
                           cart_items=cart_items,
                           catalog=catalog,
                           earliest_lock_expiry=earliest_lock_expiry)


@booking_bp.route('/cart/add', methods=['POST'])
def cart_add():
    result = api_post('/api/cart/add', {
        'session_id': session.get('session_id', ''),
        'room_type_id': request.form.get('room_type_id', type=int),
        'physical_room_id': request.form.get('physical_room_id', type=int),
        'arrival_date': request.form.get('arrival_date', ''),
        'departure_date': request.form.get('departure_date', ''),
        'adults': request.form.get('adults', 1, type=int),
        'children': request.form.get('children', 0, type=int),
        'booking_type': request.form.get('booking_type', 'continuous'),
        'selected_nights': request.form.get('selected_nights', ''),
    })
    if result.get('success'):
        flash('Đã thêm vào giỏ hàng!', 'success')
    else:
        flash(result.get('message', 'Thêm vào giỏ thất bại.'), 'error')
    return redirect(url_for('booking.cart'))


@booking_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
def cart_remove(item_id):
    api_delete(f'/api/cart/remove/{item_id}')
    return redirect(url_for('booking.cart'))


@booking_bp.route('/cart/checkout', methods=['POST'])
def cart_checkout():
    err = _require_login()
    if err:
        return err
    result = api_post('/api/cart/checkout', {
        'session_id': session.get('session_id', ''),
        'user_id': session.get('user_id'),
        'payment_method': request.form.get('payment_method', 'credit_card'),
        'payment_type': request.form.get('payment_type', 'full'),
        'promo_code': request.form.get('promo_code', '').strip(),
        'special_requests': request.form.get('special_requests', '').strip(),
        'extra_services': request.form.getlist('extra_services', type=int),
    })
    if result.get('success'):
        flash('Đặt phòng thành công!', 'success')
        return redirect(url_for('booking.history'))
    flash(result.get('message', 'Thanh toán thất bại. Vui lòng thử lại.'), 'error')
    return redirect(url_for('booking.cart'))
