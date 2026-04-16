document.addEventListener('DOMContentLoaded', () => {
    const signUpButton = document.getElementById('signUp');
    const signInButton = document.getElementById('signIn');
    const container = document.getElementById('auth-container');
    const initMode = container.dataset.initMode;

    const overlayContainer = document.querySelector('.auth-overlay-container');
    const overlay = document.querySelector('.auth-overlay');
    const signInContainer = document.querySelector('.sign-in-container');
    const signUpContainer = document.querySelector('.sign-up-container');
    const overlayLeft = document.querySelector('.auth-overlay-left');
    const overlayRight = document.querySelector('.auth-overlay-right');

    const animDuration = 0.8;
    const animEase = 'power3.inOut';

    let isRegisterMode = false;

    function goToRegister(animate = true) {
        isRegisterMode = true;
        const dur = animate ? animDuration : 0;
        
        // Máng trượt overlay di chuyển toàn bộ sang trái
        gsap.to(overlayContainer, { x: '-100%', duration: dur, ease: animEase });
        // Tấm ảnh khổng lồ trượt từ từ sang phải để tạo hiệu ứng parallax nhẹ
        gsap.to(overlay, { x: '50%', duration: dur, ease: animEase });
        
        // Căn chỉnh 2 cục văn bản để chạy trơn tru
        gsap.to(overlayLeft, { x: 0, duration: dur, ease: animEase });
        gsap.to(overlayRight, { x: '25%', duration: dur, ease: animEase });

        // Form Login lủi đi sang phải, biến mất
        gsap.to(signInContainer, { x: '100%', opacity: 0, zIndex: 1, duration: dur, ease: animEase });
        // Form Đăng ký trồi ra, trôi sang phải lấp chỗ trống
        gsap.to(signUpContainer, { x: '100%', opacity: 1, zIndex: 5, duration: dur, ease: animEase });
    }

    function goToLogin(animate = true) {
        isRegisterMode = false;
        const dur = animate ? animDuration : 0;
        
        // Kéo tấm che về chỗ cũ bên phải
        gsap.to(overlayContainer, { x: '0%', duration: dur, ease: animEase });
        gsap.to(overlay, { x: '0%', duration: dur, ease: animEase });
        
        gsap.to(overlayLeft, { x: '-25%', duration: dur, ease: animEase });
        gsap.to(overlayRight, { x: '0%', duration: dur, ease: animEase });

        // Form Đăng Ký giấu đi về bên trái
        gsap.to(signUpContainer, { x: '0%', opacity: 0, zIndex: 1, duration: dur, ease: animEase });
        // Form Đăng Nhập mở ra ở bên trái
        gsap.to(signInContainer, { x: '0%', opacity: 1, zIndex: 5, duration: dur, ease: animEase });
    }

    // Set trạng thái ban đầu để fix form jump (khi refesh từ lỗi Register thì nó nảy form đúng vị trí)
    if (initMode === 'register') {
        goToRegister(false);
    } else {
        goToLogin(false);
    }

    // GSAP event triggers
    if(signUpButton) signUpButton.addEventListener('click', () => goToRegister(true));
    if(signInButton) signInButton.addEventListener('click', () => goToLogin(true));

    // Fix local form validation confirm password
    const registerForm = document.querySelector('.sign-up-container form');
    if(registerForm) {
        registerForm.addEventListener('submit', (e) => {
            const p1 = document.getElementById('pw1').value;
            const p2 = document.getElementById('pw2').value;
            if (p1 !== p2) {
                e.preventDefault();
                alert("Xin lỗi, Mật khẩu không trùng khớp. Vui lòng kiểm tra lại!");
            }
        });
    }
});
