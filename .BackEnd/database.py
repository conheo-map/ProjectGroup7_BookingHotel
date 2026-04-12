import sqlite3
from config import DB_PATH

def get_db_connection():
    """Tạo và trả về connection tới CSDL SQLite."""
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def execute_query(query, args=(), fetchone=False, fetchall=False, commit=False):
    """Tiện ích thực thi truy vấn nhanh."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, args)
        if commit:
            conn.commit()
        if fetchone:
            return cursor.fetchone()
        if fetchall:
            return cursor.fetchall()
        return cursor.lastrowid
    finally:
        conn.close()
