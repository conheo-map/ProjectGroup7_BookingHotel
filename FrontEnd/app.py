import os
import uuid
from datetime import timedelta
from flask import Flask, session, render_template


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'frontend-hotel-secret-2025')
    app.permanent_session_lifetime = timedelta(days=7)

    # ── Jinja2 Filters ──────────────────────────────────────────────────────────
    @app.template_filter('vnd')
    def fmt_vnd(value):
        try:
            return f"{float(value):,.0f}đ"
        except Exception:
            return "0đ"

    @app.template_filter('date_vn')
    def fmt_date_vn(value):
        from datetime import datetime
        try:
            if isinstance(value, str):
                value = datetime.strptime(value[:10], '%Y-%m-%d')
            return value.strftime('%d/%m/%Y')
        except Exception:
            return str(value) if value else ''

    @app.template_filter('date_parse')
    def date_parse(value, fmt='%Y-%m-%d'):
        from datetime import datetime
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            return value

    @app.template_filter('format_date')
    def format_date(value, fmt='%d/%m/%Y'):
        try:
            return value.strftime(fmt)
        except Exception:
            return value

    @app.template_filter('stars')
    def fmt_stars(value):
        try:
            n = round(float(value))
            return '★' * n + '☆' * (5 - n)
        except Exception:
            return '☆☆☆☆☆'

    # ── Context Processor (auth) ─────────────────────────────────────────────────
    @app.context_processor
    def inject_auth():
        return {
            'auth': {
                'is_logged_in': bool(session.get('token') and session.get('user_id')),
                'user_id': session.get('user_id'),
                'username': session.get('username', ''),
                'full_name': session.get('full_name', ''),
                'role': session.get('role', 'Guest'),
                'account_type': session.get('account_type', 'customer'),
                'token': session.get('token', ''),
            }
        }

    # ── Session ID for cart / room locks ────────────────────────────────────────
    @app.before_request
    def ensure_session_id():
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
            session.permanent = True

    # ── Blueprints ──────────────────────────────────────────────────────────────
    from routes.auth import auth_bp
    from routes.search import search_bp
    from routes.booking import booking_bp
    from routes.staff import staff_bp
    from routes.management import management_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(management_bp)

    # ── Error Handlers ──────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('home.html', error='Trang không tìm thấy.'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('home.html', error='Lỗi máy chủ nội bộ.'), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5001, host='0.0.0.0')
