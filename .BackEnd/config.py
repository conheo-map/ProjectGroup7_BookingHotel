import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database Config
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, 'db', 'HotelBooking.db'))

# Flask Config — đặt SECRET_KEY qua biến môi trường khi triển khai thật
SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key-booking-hotel")
DEBUG = True

# Token API (giây), mặc định 7 ngày
API_TOKEN_MAX_AGE = int(os.environ.get("API_TOKEN_MAX_AGE", str(60 * 60 * 24 * 7)))

# Tiền tệ hiển thị (ứng dụng dùng một đơn vị logic cho giá trong DB)
CURRENCY_LABEL = os.environ.get("CURRENCY_LABEL", "VND")
# Thuế GTGT mặc định (10%) — đồng bộ với booking_routes
DEFAULT_TAX_RATE = float(os.environ.get("DEFAULT_TAX_RATE", "0.1"))
