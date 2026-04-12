document.addEventListener('DOMContentLoaded', function() {
    var dataNode = document.getElementById('cart-data');
    if (!dataNode) return;
    
    var viewData = JSON.parse(dataNode.textContent);
    var lockedUntilStr = viewData.earliestLockExpiry;
    if (!lockedUntilStr || lockedUntilStr === 'None') return;
    
    var deadline = new Date(lockedUntilStr + 'Z').getTime();
    var timerEl = document.getElementById('countdown-timer');
    var bannerEl = document.getElementById('countdown-banner');
    
    var interval = setInterval(function() {
        var now = new Date().getTime();
        var remaining = deadline - now;
        if (remaining <= 0) {
            clearInterval(interval);
            if(timerEl) timerEl.textContent = '00:00';
            if(bannerEl) {
                bannerEl.className = 'alert alert-danger d-flex align-items-center shadow-sm small py-2 rounded-8 mb-4';
                bannerEl.innerHTML = '<i class="fas fa-exclamation-triangle me-2 fs-4"></i><div><strong>Hết thời gian!</strong> Phòng đã được mở khóa. Vui lòng quay lại tìm kiếm.</div>';
            }
            // Disable submit button
            var submitBtn = document.querySelector('button[type="submit"].btn-blue-booking');
            if(submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'ĐÃ HẾT HẠN';
                submitBtn.className = 'btn btn-secondary w-100 py-3 fw-bold shadow-sm';
            }
            return;
        }
        var mins = Math.floor(remaining / 60000);
        var secs = Math.floor((remaining % 60000) / 1000);
        if(timerEl) timerEl.textContent = String(mins).padStart(2,'0') + ':' + String(secs).padStart(2,'0');
        
        if (remaining < 120000 && timerEl && bannerEl) { // < 2 minutes
            timerEl.classList.add('text-danger');
            bannerEl.classList.remove('alert-warning');
            bannerEl.classList.add('alert-danger');
        }
    }, 1000);
});
