from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from services.api import api_post, api_put, api_get

auth_bp = Blueprint('auth', __name__)


def _role_home(role):
    if role in ('Admin', 'Manager'):
        return redirect(url_for('management.manager_dashboard'))
    if role == 'Receptionist':
        return redirect(url_for('staff.receptionist'))
    if role == 'Housekeeper':
        return redirect(url_for('staff.housekeeping'))
    return redirect(url_for('search.home'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('token'):
        return _role_home(session.get('role', 'Guest'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        result = api_post('/api/login', {'username': username, 'password': password})
        if result.get('success'):
            session.permanent = True
            session['user_id'] = result['user_id']
            session['username'] = result['username']
            session['full_name'] = result.get('full_name', '')
            session['role'] = result['role']
            session['account_type'] = result['account_type']
            session['token'] = result['token']
            flash(f"Chào mừng, {result.get('full_name') or result['username']}!", 'success')
            return _role_home(result['role'])
        flash(result.get('message', 'Sai thông tin đăng nhập'), 'error')
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('token'):
        return redirect(url_for('search.home'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        name = request.form.get('customer_name', '').strip()
        if password != confirm:
            flash('Mật khẩu xác nhận không khớp', 'error')
            return render_template('register.html')
        result = api_post('/api/register', {
            'email': email,
            'password': password,
            'customer_name': name,
        })
        if result.get('success'):
            flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
            return redirect(url_for('auth.login'))
        flash(result.get('message', 'Đăng ký thất bại'), 'error')
    return render_template('register.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('token'):
        flash('Vui lòng đăng nhập.', 'error')
        return redirect(url_for('auth.login'))
    if session.get('account_type') != 'customer':
        flash('Chỉ khách hàng mới có thể truy cập trang hồ sơ.', 'error')
        return redirect(url_for('search.home'))
    if request.method == 'POST':
        payload = {'customer_name': request.form.get('customer_name', '').strip()}
        old_pw = request.form.get('old_password', '').strip()
        new_pw = request.form.get('new_password', '').strip()
        if new_pw:
            payload['old_password'] = old_pw
            payload['new_password'] = new_pw
        result = api_put('/api/profile/update', payload)
        if result.get('success'):
            session['full_name'] = result.get('customer_name', payload['customer_name'])
            flash('Cập nhật hồ sơ thành công!', 'success')
        else:
            flash(result.get('message', 'Cập nhật thất bại'), 'error')
    uid = session.get('user_id')
    loyalty = api_get(f'/api/loyalty/{uid}').get('loyalty') or {}
    return render_template('profile.html',
                           loyalty=loyalty,
                           full_name=session.get('full_name', ''),
                           email=session.get('username', ''))
