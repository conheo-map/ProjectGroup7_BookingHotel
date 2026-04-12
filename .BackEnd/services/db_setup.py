import sqlite3
from datetime import datetime, timedelta
import os
from database import get_db_connection

def init_database():
    """Chạy migration: tạo bảng mới, thêm cột, seed dữ liệu mẫu."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Tạo bảng Physical_Room
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Physical_Room (
            physical_room_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            room_type_id        INTEGER NOT NULL,
            room_name           TEXT NOT NULL UNIQUE,
            housekeeping_status TEXT NOT NULL DEFAULT 'Clean',
            is_active           INTEGER DEFAULT 1,
            created_at          TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (room_type_id) REFERENCES Dim_RoomType(room_type_id)
        )
    """)

    # 2. Tạo bảng Room_Lock
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Room_Lock (
            lock_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            physical_room_id INTEGER NOT NULL,
            session_id       TEXT NOT NULL,
            lock_date        TEXT NOT NULL,
            locked_until     TEXT NOT NULL,
            booking_temp_ref TEXT
        )
    """)

    # 3. Tạo bảng Extra_Services (Bảng dịch vụ phát sinh)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Extra_Services (
            service_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id   INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            quantity     INTEGER DEFAULT 1,
            unit_price   REAL NOT NULL,
            total_price  REAL NOT NULL,
            added_by     INTEGER,
            added_at     TEXT DEFAULT (datetime('now'))
        )
    """)

    # 4. Tạo bảng Service_Catalog (Danh mục dịch vụ)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Service_Catalog (
            catalog_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            default_price REAL NOT NULL,
            category TEXT DEFAULT 'Food'
        )
    """)
    cursor.execute("SELECT COUNT(*) as cnt FROM Service_Catalog")
    if cursor.fetchone()['cnt'] == 0:
        services = [
            ('Phí dọn dẹp thêm', 100.0, 'Service'),
            ('Nước suối', 15.0, 'Beverage'),
            ('Coca Cola', 25.0, 'Beverage'),
            ('Mì ly thịt xay', 35.0, 'Food'),
            ('Giặt ủi (kg)', 50.0, 'Laundry'),
            ('Thuê xe máy (ngày)', 150.0, 'Rental')
        ]
        cursor.executemany("INSERT INTO Service_Catalog (item_name, default_price, category) VALUES (?, ?, ?)", services)

    # 4b. Booking_Nights: chuẩn hoá các đêm đã đặt (thay cho CSV selected_nights)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Booking_Nights (
            booking_night_id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id       INTEGER NOT NULL,
            physical_room_id INTEGER NOT NULL,
            night_date       TEXT NOT NULL,
            created_at       TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (booking_id) REFERENCES New_Bookings(booking_id) ON DELETE CASCADE,
            FOREIGN KEY (physical_room_id) REFERENCES Physical_Room(physical_room_id)
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_booking_nights_booking_date
        ON Booking_Nights(booking_id, night_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_booking_nights_room_date
        ON Booking_Nights(physical_room_id, night_date)
    """)

    # 5. Các cột bổ sung cho các bảng cũ (Migration)
    # Dim_RoomType
    new_columns_dim_roomtype = [
        ("max_adults",   "INTEGER DEFAULT 2"),
        ("max_children", "INTEGER DEFAULT 1"),
        ("base_price",   "REAL DEFAULT 100.0"),
        ("description",  "TEXT DEFAULT ''"),
        ("amenities",    "TEXT DEFAULT ''"),
        ("is_active",    "INTEGER DEFAULT 1"),
        ("hotel_id",     "INTEGER DEFAULT 1"),
        ("allow_child_sharing", "INTEGER DEFAULT 1"),
        ("extra_bed_capacity", "INTEGER DEFAULT 0"),
        ("extra_adult_fee", "REAL DEFAULT 0.0"),
        ("child_breakfast_fee", "REAL DEFAULT 0.0"),
    ]
    for col_name, col_def in new_columns_dim_roomtype:
        try:
            cursor.execute(f"ALTER TABLE Dim_RoomType ADD COLUMN {col_name} {col_def}")
        except Exception: pass

    # New_Bookings
    new_columns_new_bookings = [
        ("status_detail",    "TEXT DEFAULT 'Confirmed'"),
        ("deposit_paid",     "REAL DEFAULT 0.0"),
        ("deposit_paid_cents", "INTEGER DEFAULT 0"),
        ("physical_room_id", "INTEGER"),
        ("booking_type",     "TEXT DEFAULT 'continuous'"),
        ("selected_nights",  "TEXT DEFAULT ''"),
        ("adults",           "INTEGER DEFAULT 1"),
        ("children",         "INTEGER DEFAULT 0"),
        ("babies",           "INTEGER DEFAULT 0"),
        ("cancel_reason",    "TEXT DEFAULT ''"),
        ("canceled_by",      "INTEGER"),
        ("tax_amount",       "REAL DEFAULT 0.0"),
        ("tax_amount_cents", "INTEGER DEFAULT 0"),
        ("special_requests", "TEXT DEFAULT ''"),
        ("group_order_id",   "TEXT"),
        ("source_channel",   "TEXT DEFAULT 'direct'"),
        ("utm_campaign",     "TEXT DEFAULT ''"),
        ("utm_medium",       "TEXT DEFAULT ''"),
        ("invoice_number",   "TEXT DEFAULT ''"),
        ("invoice_issued_at","TEXT")
    ]
    for col_name, col_def in new_columns_new_bookings:
        try:
            cursor.execute(f"ALTER TABLE New_Bookings ADD COLUMN {col_name} {col_def}")
        except Exception: pass

    # Promotions
    new_columns_promotions = [
        ("start_date",    "TEXT"),
        ("end_date",      "TEXT"),
        ("description",   "TEXT DEFAULT ''"),
        ("apply_scope",   "TEXT DEFAULT 'all'"),
        ("scope_value",   "TEXT DEFAULT ''"),
        ("discount_type", "TEXT DEFAULT 'percent'"),
        ("max_uses",      "INTEGER DEFAULT 0"),
        ("current_uses",  "INTEGER DEFAULT 0"),
        ("membership_tier_required", "TEXT DEFAULT 'Newbie'")
    ]
    for col_name, col_def in new_columns_promotions:
        try:
            cursor.execute(f"ALTER TABLE Promotions ADD COLUMN {col_name} {col_def}")
        except Exception: pass

    # Money columns (write-through, giữ tương thích cũ)
    for col_name, col_def in [
        ("total_price_cents", "INTEGER DEFAULT 0"),
        ("discount_amount_cents", "INTEGER DEFAULT 0"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE New_Bookings ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass

    for table, cols in [
        ("Payments", [("amount_cents", "INTEGER DEFAULT 0")]),
        ("Extra_Services", [("unit_price_cents", "INTEGER DEFAULT 0"), ("total_price_cents", "INTEGER DEFAULT 0")]),
        ("Room_Rates", [("base_price_cents", "INTEGER DEFAULT 0")]),
        ("Dim_RoomType", [
            ("base_price_cents", "INTEGER DEFAULT 0"),
            ("extra_adult_fee_cents", "INTEGER DEFAULT 0"),
            ("child_breakfast_fee_cents", "INTEGER DEFAULT 0")
        ]),
    ]:
        for col_name, col_def in cols:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
            except Exception:
                pass

    # 6. Bảng Cart & Roles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Cart_Sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Cart_Items (
            cart_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            room_type_id INTEGER,
            physical_room_id INTEGER,
            arrival_date TEXT,
            departure_date TEXT,
            adults INTEGER,
            children INTEGER,
            babies INTEGER,
            booking_type TEXT,
            selected_nights TEXT,
            total_price REAL,
            source_channel TEXT DEFAULT 'direct',
            utm_campaign TEXT DEFAULT '',
            utm_medium TEXT DEFAULT ''
        )
    """)
    for col_name, col_def in [
        ("source_channel", "TEXT DEFAULT 'direct'"),
        ("utm_campaign", "TEXT DEFAULT ''"),
        ("utm_medium", "TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE Cart_Items ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass

    # Conversion tracking / data linkage
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Funnel_Events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            user_id INTEGER,
            event_name TEXT NOT NULL,
            hotel_id INTEGER,
            room_type_id INTEGER,
            booking_id INTEGER,
            metadata_json TEXT DEFAULT '{}',
            source_channel TEXT DEFAULT 'direct',
            utm_campaign TEXT DEFAULT '',
            utm_medium TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_funnel_event_name_time ON Funnel_Events(event_name, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_funnel_event_session ON Funnel_Events(session_id)")
    cursor.execute("SELECT COUNT(*) as cnt FROM Roles WHERE role_name = 'Housekeeper'")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("INSERT INTO Roles (role_name) VALUES ('Housekeeper')")

    # 7. Seed Physical_Room nếu chưa có
    cursor.execute("SELECT COUNT(*) as cnt FROM Physical_Room")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("SELECT room_type_id, room_type_code FROM Dim_RoomType ORDER BY room_type_code")
        all_room_types = cursor.fetchall()
        for rt in all_room_types:
            for i in range(1, 6):
                room_name = f"{rt['room_type_code']}_{i}"
                cursor.execute("INSERT OR IGNORE INTO Physical_Room (room_type_id, room_name) VALUES (?, ?)", (rt['room_type_id'], room_name))

    # 8. Indexes cho hiệu năng
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_dates ON New_Bookings(arrival_date, departure_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_pr ON New_Bookings(physical_room_id, status_detail)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_room_locks_date ON Room_Lock(physical_room_id, locked_until)")

    # 9. Migrate Booking_Nights từ dữ liệu hiện có (chạy 1 lần, idempotent)
    cursor.execute("SELECT COUNT(*) as cnt FROM Booking_Nights")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("""
            SELECT booking_id, physical_room_id, booking_type, arrival_date, departure_date, selected_nights, status_detail
            FROM New_Bookings
            WHERE physical_room_id IS NOT NULL
              AND status_detail NOT IN ('Canceled', 'No-Show')
        """)
        rows = cursor.fetchall()
        to_insert = []
        for r in rows:
            pr_id = r['physical_room_id']
            if not pr_id:
                continue
            if r['booking_type'] == 'fragmented':
                nights = [n.strip() for n in (r['selected_nights'] or '').split(',') if n.strip()]
            else:
                nights = []
                try:
                    ad = datetime.strptime(r['arrival_date'], '%Y-%m-%d').date()
                    dd = datetime.strptime(r['departure_date'], '%Y-%m-%d').date()
                    cur = ad
                    while cur < dd:
                        nights.append(cur.strftime('%Y-%m-%d'))
                        cur += timedelta(days=1)
                except Exception:
                    nights = []
            for nd in nights:
                to_insert.append((r['booking_id'], pr_id, nd))

        if to_insert:
            cursor.executemany(
                "INSERT OR IGNORE INTO Booking_Nights (booking_id, physical_room_id, night_date) VALUES (?, ?, ?)",
                to_insert,
            )

    # 10. Backfill cents columns nếu đang trống (idempotent theo điều kiện = 0)
    try:
        cursor.execute("UPDATE New_Bookings SET total_price_cents = ROUND(COALESCE(total_price,0) * 100) WHERE COALESCE(total_price_cents,0) = 0 AND COALESCE(total_price,0) > 0")
        cursor.execute("UPDATE New_Bookings SET deposit_paid_cents = ROUND(COALESCE(deposit_paid,0) * 100) WHERE COALESCE(deposit_paid_cents,0) = 0 AND COALESCE(deposit_paid,0) > 0")
        cursor.execute("UPDATE New_Bookings SET tax_amount_cents = ROUND(COALESCE(tax_amount,0) * 100) WHERE COALESCE(tax_amount_cents,0) = 0 AND COALESCE(tax_amount,0) > 0")
        cursor.execute("UPDATE New_Bookings SET discount_amount_cents = ROUND(COALESCE(discount_amount,0) * 100) WHERE COALESCE(discount_amount_cents,0) = 0 AND COALESCE(discount_amount,0) > 0")
        cursor.execute("UPDATE Payments SET amount_cents = ROUND(COALESCE(amount,0) * 100) WHERE COALESCE(amount_cents,0) = 0 AND COALESCE(amount,0) != 0")
        cursor.execute("UPDATE Extra_Services SET unit_price_cents = ROUND(COALESCE(unit_price,0) * 100) WHERE COALESCE(unit_price_cents,0) = 0 AND COALESCE(unit_price,0) > 0")
        cursor.execute("UPDATE Extra_Services SET total_price_cents = ROUND(COALESCE(total_price,0) * 100) WHERE COALESCE(total_price_cents,0) = 0 AND COALESCE(total_price,0) > 0")
        cursor.execute("UPDATE Room_Rates SET base_price_cents = ROUND(COALESCE(base_price,0) * 100) WHERE COALESCE(base_price_cents,0) = 0 AND COALESCE(base_price,0) > 0")
        cursor.execute("UPDATE Dim_RoomType SET base_price_cents = ROUND(COALESCE(base_price,0) * 100) WHERE COALESCE(base_price_cents,0) = 0 AND COALESCE(base_price,0) > 0")
        cursor.execute("UPDATE Dim_RoomType SET extra_adult_fee_cents = ROUND(COALESCE(extra_adult_fee,0) * 100) WHERE COALESCE(extra_adult_fee_cents,0) = 0 AND COALESCE(extra_adult_fee,0) > 0")
        cursor.execute("UPDATE Dim_RoomType SET child_breakfast_fee_cents = ROUND(COALESCE(child_breakfast_fee,0) * 100) WHERE COALESCE(child_breakfast_fee_cents,0) = 0 AND COALESCE(child_breakfast_fee,0) > 0")
    except Exception:
        pass

    # 11. Backfill membership_tier từ loyalty_points (đảm bảo nhất quán dữ liệu)
    try:
        cursor.execute("""
            UPDATE Customer_Accounts
            SET membership_tier =
                CASE
                    WHEN COALESCE(loyalty_points, 0) >= 210 THEN 'Gold'
                    WHEN COALESCE(loyalty_points, 0) >= 50 THEN 'Silver'
                    ELSE 'Newbie'
                END
        """)
    except Exception:
        pass

    # 12. Backfill policy room occupancy cho dữ liệu cũ (idempotent)
    try:
        # Bảo đảm không NULL cho các cột policy mới
        cursor.execute("""
            UPDATE Dim_RoomType
            SET
                allow_child_sharing = COALESCE(allow_child_sharing, 1),
                extra_bed_capacity = COALESCE(extra_bed_capacity, 0),
                extra_adult_fee = COALESCE(extra_adult_fee, 0.0),
                child_breakfast_fee = COALESCE(child_breakfast_fee, 0.0)
        """)

        # Nếu dữ liệu cũ cho phép tối đa > 2 người lớn mà chưa cấu hình giường phụ,
        # tự suy diễn sức chứa giường phụ từ max_adults để vận hành được ngay.
        cursor.execute("""
            UPDATE Dim_RoomType
            SET extra_bed_capacity = CASE
                WHEN COALESCE(max_adults, 2) > 2 THEN COALESCE(max_adults, 2) - 2
                ELSE 0
            END
            WHERE COALESCE(extra_bed_capacity, 0) = 0
              AND COALESCE(max_adults, 2) > 2
        """)

        # Đồng bộ 2 chiều fee <-> cents để tránh lệch dữ liệu sau migration
        cursor.execute("""
            UPDATE Dim_RoomType
            SET extra_adult_fee_cents = ROUND(COALESCE(extra_adult_fee, 0) * 100)
            WHERE COALESCE(extra_adult_fee_cents, 0) = 0
              AND COALESCE(extra_adult_fee, 0) > 0
        """)
        cursor.execute("""
            UPDATE Dim_RoomType
            SET child_breakfast_fee_cents = ROUND(COALESCE(child_breakfast_fee, 0) * 100)
            WHERE COALESCE(child_breakfast_fee_cents, 0) = 0
              AND COALESCE(child_breakfast_fee, 0) > 0
        """)
        cursor.execute("""
            UPDATE Dim_RoomType
            SET extra_adult_fee = ROUND(COALESCE(extra_adult_fee_cents, 0) / 100.0, 2)
            WHERE COALESCE(extra_adult_fee, 0) = 0
              AND COALESCE(extra_adult_fee_cents, 0) > 0
        """)
        cursor.execute("""
            UPDATE Dim_RoomType
            SET child_breakfast_fee = ROUND(COALESCE(child_breakfast_fee_cents, 0) / 100.0, 2)
            WHERE COALESCE(child_breakfast_fee, 0) = 0
              AND COALESCE(child_breakfast_fee_cents, 0) > 0
        """)
    except Exception:
        pass

    conn.commit()
    conn.close()
    print("[DB] System is ready.")
