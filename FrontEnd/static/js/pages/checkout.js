document.addEventListener('DOMContentLoaded', function() {
    // Submit guard: disable button + validate
    var checkoutForm = document.querySelector('form[action="/booking/checkout"]');
    if (checkoutForm) {
        checkoutForm.addEventListener('submit', function(e) {
            var payMethod = checkoutForm.querySelector('input[name="payment_method"]:checked');
            var payType = checkoutForm.querySelector('input[name="payment_type"]:checked');
            var errDiv = document.getElementById('checkout-error');
            if (!payMethod || !payType) {
                e.preventDefault();
                if (errDiv) { errDiv.textContent = 'Vui lòng chọn phương thức và hình thức thanh toán.'; errDiv.classList.remove('d-none'); }
                return;
            }
            if (errDiv) errDiv.classList.add('d-none');
            var btn = document.getElementById('confirm-btn');
            if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Đang xử lý...'; }
        });
    }

    var dataNode = document.getElementById('checkout-data');
    if (!dataNode) return;
    
    var viewData = JSON.parse(dataNode.textContent);
    
    var checkinStr = viewData.checkinDate;
    var checkoutStr = viewData.checkoutDate;
    var basePrice = parseFloat(viewData.basePrice || 0);
    var nights = 1;
    
    if (checkinStr && checkoutStr) {
        var t1 = new Date(checkinStr).getTime();
        var t2 = new Date(checkoutStr).getTime();
        var diff = Math.ceil((t2 - t1) / 86400000);
        if (diff > 0) nights = diff;
    }
    
    var rawNights = viewData.selectedNights;
    if (rawNights && rawNights.trim() !== '') {
        nights = rawNights.split(',').length;
    }

    var baseTotal = basePrice * nights;
    
    function updateTotalPrice() {
        var total = baseTotal;
        var paymentTypeNode = document.querySelector('input[name="payment_type"]:checked');
        var paymentType = paymentTypeNode ? paymentTypeNode.value : 'full';
        
        var displayLabel = 'Tổng cộng (Thanh toán 100%)';
        if (paymentType === 'deposit') {
            total = total * 0.5;
            displayLabel = 'Số tiền đặt cọc (50%)';
        }
        
        var priceDisplay = document.getElementById('total-price-display');
        var labelDisplay = document.getElementById('total-price-label');
        if (priceDisplay) {
            priceDisplay.textContent = total.toLocaleString('vi-VN') + 'đ';
            if (paymentType === 'deposit') {
                priceDisplay.innerHTML += ' <div class="extra-small text-danger fw-normal mt-1">Còn nợ: ' + (baseTotal * 0.5).toLocaleString('vi-VN') + 'đ</div>';
            }
        }
        if (labelDisplay) {
            labelDisplay.textContent = displayLabel;
        }
    }
    
    var radios = document.querySelectorAll('input[name="payment_type"]');
    radios.forEach(function(r) {
        r.addEventListener('change', updateTotalPrice);
    });
    
    updateTotalPrice();
});
