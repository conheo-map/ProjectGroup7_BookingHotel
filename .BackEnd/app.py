import sys
import os
# Add Backend folder to path temporarily to resolve imports if run from outside
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import threading
import time
from flask import Flask
from config import SECRET_KEY as CONFIG_SECRET_KEY
from services.api_auth import init_auth_context
from database import get_db_connection
from services.db_setup import init_database
from services.booking_service import cleanup_expired_locks
from dotenv import load_dotenv

load_dotenv()



def cleanup_locks_job():
    """Tiến trình chạy ngầm để dọn dẹp các khóa phòng hết hạn."""
    print("[CRON] Starting room lock cleanup process...")
    while True:
        try:
            conn = get_db_connection()
            cleanup_expired_locks(conn)
            conn.close()
        except Exception as e:
            print(f"[CRON] Cleanup error: {repr(e)}")
        time.sleep(60) # Chạy mỗi phút

def create_app():
    # 1. Khởi tạo Database (Migration)
    try:
        init_database()
    except Exception as e:
        print(f"[ERROR] Cannot init DB: {e}")

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', CONFIG_SECRET_KEY)

    @app.before_request
    def _load_api_token():
        init_auth_context()

    # Import Blueprints
    from routes.auth_routes import auth_bp
    from routes.room_routes import room_bp
    from routes.booking_routes import booking_bp
    from routes.admin_routes import admin_bp
    from routes.manager_routes import manager_bp
    from routes.system_routes import system_bp
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(room_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(system_bp)

    # 2. Khởi chạy tiến trình dọn dẹp ngầm
    thread = threading.Thread(target=cleanup_locks_job, daemon=True)
    thread.start()

    return app

if __name__ == '__main__':
    app = create_app()
    debug_mode = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug_mode, port=5000, host='0.0.0.0')
