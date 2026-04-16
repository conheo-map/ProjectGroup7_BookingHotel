# 🏨 Hotel Booking System — Saigon-Condao Islands Resort

Hệ thống quản lý đặt phòng khách sạn trực tuyến được xây dựng bằng **Python Flask**, sử dụng kiến trúc **tách biệt Frontend – Backend (Decoupled Architecture)**.

<p align="center">
  <img src="FrontEnd/static/images/cropped-logo-1.png" alt="Logo" height="60">
</p>

---

## 📋 Mục lục

- [Tính năng chính](#-tính-năng-chính)
- [Kiến trúc hệ thống](#-kiến-trúc-hệ-thống)
- [Yêu cầu hệ thống](#-yêu-cầu-hệ-thống)
- [Hướng dẫn cài đặt từ A-Z](#-hướng-dẫn-cài-đặt-từ-a-z)
- [Khởi chạy dự án](#-khởi-chạy-dự-án)
- [Tài khoản mặc định](#-tài-khoản-mặc-định)
- [Cấu trúc thư mục](#-cấu-trúc-thư-mục)
- [Công nghệ sử dụng](#-công-nghệ-sử-dụng)

---

## ✨ Tính năng chính

### Dành cho Khách hàng (Customer)
- 🔍 Tìm kiếm phòng trống theo ngày, số khách, bộ lọc nâng cao
- 🛒 Giỏ hàng & đặt phòng trực tuyến (hỗ trợ đặt liền / đêm lẻ)
- 💳 Thanh toán toàn bộ hoặc đặt cọc 50%
- ⏱️ Khóa phòng tạm thời (countdown) để đảm bảo không bị trùng
- ⭐ Đánh giá & xếp hạng sau khi lưu trú
- 🎖️ Chương trình Loyalty tích điểm

### Dành cho Nhân viên (Staff)
- 📋 **Lễ tân**: Quản lý đặt phòng, Check-in/Check-out, Walk-in, Sơ đồ phòng
- 🧹 **Buồng phòng**: Quản lý trạng thái dọn phòng
- 📊 **Quản lý**: Danh mục phòng, Kho & Giá, Lịch giá chi tiết, Khuyến mãi, Báo cáo doanh thu
- 👥 **Admin**: Quản lý nhân sự, Cấu hình hệ thống

---

## 🏗️ Kiến trúc hệ thống

```
┌─────────────────┐         API (REST)         ┌─────────────────┐
│                 │ ◄──────────────────────────►│                 │
│    FrontEnd     │    http://localhost:5000     │    BackEnd      │
│  (Flask :5001)  │                             │  (Flask :5000)  │
│                 │                             │                 │
│  • HTML/Jinja2  │                             │  • REST API     │
│  • CSS/JS       │                             │  • SQLite DB    │
│  • Bootstrap 5  │                             │  • Auth Token   │
└─────────────────┘                             └─────────────────┘
```

- **Frontend** (port `5001`): Giao diện người dùng, render HTML bằng Jinja2
- **Backend** (port `5000`): API server xử lý logic nghiệp vụ, truy vấn CSDL

---

## 💻 Yêu cầu hệ thống

| Phần mềm | Phiên bản tối thiểu | Ghi chú |
|---|---|---|
| **Python** | 3.9 trở lên | Ngôn ngữ chính của dự án |
| **pip** | Đi kèm Python | Trình quản lý thư viện |
| **Git** | Bất kỳ | Để clone dự án |
| **Trình duyệt** | Chrome / Edge / Firefox | Để truy cập giao diện |

> **Lưu ý:** Dự án sử dụng SQLite (tích hợp sẵn trong Python), **không cần** cài đặt MySQL, PostgreSQL hay bất kỳ hệ quản trị CSDL nào khác.

---

## 🚀 Hướng dẫn cài đặt từ A-Z

### Bước 1: Cài đặt Python

1. Truy cập [python.org/downloads](https://www.python.org/downloads/)
2. Tải bản **Python 3.12** (hoặc mới hơn) phù hợp với hệ điều hành
3. Khi cài đặt, **bắt buộc tích vào ô** ✅ `Add Python to PATH`
4. Nhấn **Install Now** và chờ hoàn tất

**Kiểm tra cài đặt thành công:**
```bash
python --version
# Kết quả mong đợi: Python 3.12.x
```

### Bước 2: Cài đặt Git

1. Truy cập [git-scm.com/downloads](https://git-scm.com/downloads)
2. Tải và cài đặt theo mặc định (nhấn Next liên tục)

**Kiểm tra:**
```bash
git --version
# Kết quả mong đợi: git version 2.x.x
```

### Bước 3: Clone dự án về máy

Mở **Terminal** (hoặc **Command Prompt** / **PowerShell** trên Windows):

```bash
git clone https://github.com/<username>/BookingHotel.git
cd BookingHotel/Project_1
```

> Thay `<username>` bằng tên tài khoản GitHub thực tế của bạn.

### Bước 4: Thiết lập môi trường ảo (Khuyên dùng)

Mở Terminal tại thư mục `Project_1`:
```bash
# Tạo môi trường ảo
python -m venv venv

# Kích hoạt môi trường ảo (Windows)
.\venv\Scripts\activate

# Kích hoạt môi trường ảo (macOS/Linux)
source venv/bin/activate
```

### Bước 5: Cài đặt thư viện Python

Khi môi trường ảo đã được kích hoạt:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Hoặc cài thủ công các thư viện chính:**
> `pip install flask requests itsdangerous werkzeug Jinja2 waitress gunicorn python-dotenv flask-cors`

### Bước 6: Cấu hình môi trường (.env)

Tạo file `.env` tại thư mục gốc (nếu cần đổi cổng hoặc secret key):
```ini
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=1
```

### Các lệnh quản lý môi trường & thư viện
```bash
# Xem danh sách thư viện đã cài
pip list

# Kiểm tra thư viện nào lỗi thời
pip list --outdated

# Cài đặt một thư viện cụ thể bản mới nhất
pip install --upgrade <tên_thư_viện>

# Xóa một thư viện
pip uninstall <tên_thư_viện>

# Xuất lại file requirements mới nhất từ máy bạn
pip freeze > requirements.txt
```

---

## ▶️ Khởi chạy dự án
VUI LÒNG CHẠY DỰ ÁN BẰNG PHIÊN BẢN PYTHON 3.13.x

> ⚠️ **Quan trọng:** Phải mở **2 cửa sổ Terminal riêng biệt** và chạy đồng thời cả 2 server.

### Terminal 1 — Khởi động Backend (API Server)

```bash
cd .BackEnd
python app.py
```

Kết quả mong đợi:
```
[DB] System is ready.
[CRON] Starting room lock cleanup process...
 * Running on http://127.0.0.1:5000
```

### Terminal 2 — Khởi động Frontend (Giao diện)

```bash
cd FrontEnd
python app.py
```

Kết quả mong đợi:
```
 * Running on http://127.0.0.1:5001
```

### Truy cập hệ thống

Mở trình duyệt và truy cập:

| Trang | URL |
|---|---|
| 🌐 **Trang chủ khách hàng** | [http://localhost:5001](http://localhost:5001) |
| 🔍 **Tìm kiếm phòng** | [http://localhost:5001/search](http://localhost:5001/search) |
| 🔐 **Đăng nhập** | [http://localhost:5001/login](http://localhost:5001/login) |

---

## 🔑 Tài khoản mặc định

Hệ thống đi kèm dữ liệu mẫu. Bạn có thể đăng nhập ngay với các tài khoản sau:

### Nhân viên (Staff)

| Vai trò | Username | Password | Họ tên |
|---|---|---|---|
| 🔴 Admin | `admin` | `123` | Truong Duy Cuong |
| 🟡 Manager | `Jack97` | `123` | Trinh Tran Phuong Tuan |
| 🔵 Receptionist | `DinhVanMinhTuan` | `123` | Dinh Van Minh Tuan |
| HouseKeeper | `leanhtuan` | `123` | Le Anh Tuan |
### Khách hàng (Customer)

| Email | Password |
|---|---|
| `guest1@example.com` | `123` |

> 💡 Mật khẩu mặc định của tất cả tài khoản demo là `123`. Bạn cũng có thể tự tạo tài khoản khách hàng mới qua trang **Đăng ký**.

---

## 📁 Cấu trúc thư mục

```
Project_1/
│
├── .BackEnd/                    # 🔧 Backend API Server (Port 5000)
│   ├── app.py                   #    Entry point
│   ├── config.py                #    Cấu hình (DB path, secret key, ...)
│   ├── database.py              #    Kết nối SQLite
│   ├── db/
│   │   └── HotelBooking.db      #    📦 File cơ sở dữ liệu SQLite
│   ├── routes/                  #    Các module API (Flask Blueprint)
│   │   ├── auth_routes.py       #       Đăng nhập / Đăng ký
│   │   ├── booking_routes.py    #       Đặt phòng / Thanh toán
│   │   ├── room_routes.py       #       Tìm kiếm / Chi tiết phòng
│   │   ├── manager_routes.py    #       Quản lý phòng / Giá / KM
│   │   └── system_routes.py     #       Cấu hình hệ thống
│   └── services/                #    Logic nghiệp vụ dùng chung
│       ├── booking_service.py   #       Xử lý đặt phòng, khóa phòng
│       ├── auth_tokens.py       #       Tạo / xác thực token
│       └── api_auth.py          #       Middleware xác thực API
│
├── FrontEnd/                    # 🎨 Frontend Web (Port 5001)
│   ├── app.py                   #    Entry point
│   ├── static/                  #    Tài nguyên tĩnh
│   │   ├── css/
│   │   │   ├── main.css         #       CSS toàn cục
│   │   │   └── pages/           #       CSS riêng cho từng trang
│   │   ├── js/
│   │   │   ├── main.js          #       JS toàn cục (sidebar, scroll, toast)
│   │   │   └── pages/           #       JS riêng cho từng trang
│   │   └── images/              #       Hình ảnh, logo
│   ├── templates/               #    Giao diện HTML (Jinja2)
│   │   ├── base.html            #       Layout gốc (navbar, sidebar)
│   │   ├── search.html          #       Tìm kiếm phòng
│   │   ├── checkout.html        #       Thanh toán
│   │   └── ...                  #       Các trang khác
│   ├── routes/                  #    Routing frontend
│   └── services/
│       └── api.py               #    Gọi API đến Backend
│
└── README.md                    # 📖 File này
```

---

## 🛠️ Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| **Backend** | Python 3 · Flask · SQLite |
| **Frontend** | Python 3 · Flask · Jinja2 |
| **Giao diện** | HTML5 · CSS3 · JavaScript (Vanilla) |
| **UI Framework** | Bootstrap 5.3 · Font Awesome 6 |
| **Biểu đồ** | Chart.js |
| **Kiến trúc** | Decoupled (FE ↔ BE qua REST API) |
| **Database** | SQLite (tích hợp sẵn, không cần cài riêng) |
| **Xác thực** | Token-based (itsdangerous) |

---

## ❓ Xử lý sự cố thường gặp

### Lỗi: `ModuleNotFoundError: No module named 'flask'`
➡️ Bạn chưa cài thư viện. Chạy lại:
```bash
pip install flask requests itsdangerous
```

### Trang web hiển thị nhưng không có dữ liệu phòng
➡️ Backend chưa chạy. Mở Terminal riêng và chạy:
```bash
cd .BackEnd
python app.py
```

### Lỗi: `python` không nhận ra lệnh
➡️ Python chưa được thêm vào PATH. Cài lại Python và **tích vào ô "Add to PATH"**. Hoặc thử dùng `python3` thay cho `python`.

### Port bị chiếm (Address already in use)
➡️ Có tiến trình cũ đang chạy. Tắt tất cả Terminal cũ rồi mở lại.

---

## 📄 Giấy phép

Dự án này được phát triển cho mục đích học tập và nghiên cứu.

---

<p align="center">
  <b>Saigon-Condao Islands Resort</b> · A member of Saigontourist Group
</p>