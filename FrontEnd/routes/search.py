from flask import Blueprint, render_template, request, session
from services.api import api_get, api_post
from datetime import date, timedelta

search_bp = Blueprint('search', __name__)


@search_bp.route('/')
def home():
    hotels = api_get('/api/hotels').get('hotels', [])
    today = date.today().strftime('%Y-%m-%d')
    tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    return render_template('home.html', hotels=hotels, today=today, tomorrow=tomorrow)


@search_bp.route('/index')
def index():
    return home()


@search_bp.route('/search')
def search():
    checkin = request.args.get('checkin_date', '')
    checkout = request.args.get('checkout_date', '')
    adults = request.args.get('adults', 1, type=int)
    children = request.args.get('children', 0, type=int)
    hotel_id = request.args.get('hotel_id', '')
    promo_code = request.args.get('promo_code', '')
    # Legacy single-value filters (kept for backward compat)
    room_type_code = request.args.get('room_type_code', '')
    availability = request.args.get('availability', '')
    # New OTA multi-value filters
    star_ratings = request.args.getlist('star_ratings[]')
    hotel_types = request.args.getlist('hotel_types[]')
    room_type_codes = request.args.getlist('room_type_codes[]')
    min_price = request.args.get('min_price', '', type=str)
    max_price = request.args.get('max_price', '', type=str)
    sort_by = request.args.get('sort_by', 'price_asc')

    params = {
        'checkin_date': checkin,
        'checkout_date': checkout,
        'adults': adults,
        'children': children,
        'promo_code': promo_code,
        'hotel_id': hotel_id,
        'room_type_code': room_type_code,
        'availability': availability,
        'star_ratings': star_ratings,
        'hotel_types': hotel_types,
        'room_type_codes': room_type_codes,
        'min_price': min_price,
        'max_price': max_price,
        'sort_by': sort_by,
    }

    if checkin and checkout:
        api_post('/api/funnel/event', {
            'event_name': 'search_performed',
            'session_id': session.get('session_id', ''),
        })

    rooms = []
    if checkin and checkout:
        # Build API query params including multi-value arrays
        api_params = {
            'checkin_date': checkin,
            'checkout_date': checkout,
            'adults': adults,
            'children': children,
            'sort_by': sort_by,
        }
        if promo_code:
            api_params['promo_code'] = promo_code
        if hotel_id:
            api_params['hotel_id'] = hotel_id
        if availability:
            api_params['availability'] = availability
        if min_price:
            api_params['min_price'] = min_price
        if max_price:
            api_params['max_price'] = max_price
        # Multi-value: must be repeated keys — use a list of tuples
        api_params_list = list(api_params.items())
        for sr in star_ratings:
            api_params_list.append(('star_ratings[]', sr))
        for ht in hotel_types:
            api_params_list.append(('hotel_types[]', ht))
        for rtc in room_type_codes:
            api_params_list.append(('room_type_codes[]', rtc))

        from urllib.parse import urlencode
        qs = urlencode(api_params_list)
        from services.api import api_get_qs
        search_data = api_get_qs(f'/api/rooms/search?{qs}', token=session.get('token'))
        rooms = search_data.get('rooms', [])

    hotels = api_get('/api/hotels').get('hotels', [])
    all_room_types = api_get('/api/room-types').get('room_types', [])

    return render_template('search.html',
                           rooms=rooms,
                           hotels=hotels,
                           all_room_types=all_room_types,
                           params=params)



@search_bp.route('/room/<int:room_type_id>')
def room_detail(room_type_id):
    checkin = request.args.get('checkin_date', '')
    checkout = request.args.get('checkout_date', '')
    detail = api_get('/api/rooms/detail', params={
        'room_type_id': room_type_id,
        'checkin_date': checkin,
        'checkout_date': checkout,
    }, token=session.get('token'))
    room = detail.get('room_type') or {}
    continuous_rooms = detail.get('continuous_rooms', [])
    fragmented_rooms = detail.get('fragmented_rooms', [])
    avg_rating = detail.get('avg_rating', 0)
    review_count = detail.get('review_count', 0)
    reviews = detail.get('reviews', [])
    if not reviews:
        reviews = api_get('/api/reviews', params={'hotel_id': room.get('hotel_id', 1)}).get('reviews', [])[:8]

    # Fetch hotel metadata (star_rating, hotel_type)
    hotels = api_get('/api/hotels').get('hotels', [])
    hotel_info = next((h for h in hotels if h.get('hotel_id') == room.get('hotel_id')), {})

    return render_template('room_detail.html',
                           room=room,
                           hotel_info=hotel_info,
                           continuous_rooms=continuous_rooms,
                           fragmented_rooms=fragmented_rooms,
                           reviews=reviews,
                           avg_rating=avg_rating,
                           review_count=review_count,
                           checkin_date=checkin,
                           checkout_date=checkout)


@search_bp.route('/reviews')
def reviews():
    hotel_id = request.args.get('hotel_id', '')
    data = api_get('/api/reviews', params={'hotel_id': hotel_id} if hotel_id else {})
    hotels = api_get('/api/hotels').get('hotels', [])
    return render_template('reviews.html',
                           reviews=data.get('reviews', []),
                           hotels=hotels,
                           selected_hotel=hotel_id,
                           avg_rating=data.get('avg_rating'))
