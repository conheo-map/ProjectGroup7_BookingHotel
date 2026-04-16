function switchPaymentMethod(method) {
  document.querySelectorAll('.thanhtoan-phuongthuc-chitiet').forEach(function(el) {
    el.classList.add('d-none');
  });
  var target = document.getElementById('form-' + method);
  if (target) target.classList.remove('d-none');
  document.querySelectorAll('.thanhtoan-phuongthuc-muc').forEach(function(el) {
    el.classList.remove('active');
  });
  event.target.closest('.thanhtoan-phuongthuc-muc').classList.add('active');
}

function formatCardNumber(input) {
  var v = input.value.replace(/\D/g, '').substring(0, 16);
  input.value = v.replace(/(\d{4})(?=\d)/g, '$1 ');
}

function formatExpiry(input) {
  var v = input.value.replace(/\D/g, '').substring(0, 4);
  if (v.length >= 3) {
    input.value = v.substring(0, 2) + ' / ' + v.substring(2);
  } else {
    input.value = v;
  }
}

// Client-side validation
document.getElementById('payment-form').addEventListener('submit', function(e) {
  var activeMethod = document.querySelector('input[name="method_display"]:checked');
  if (!activeMethod) return;
  var method = activeMethod.value;
  var errors = [];
  var errDiv = document.getElementById('pay-error');

  if (method === 'credit_card') {
    if (!document.querySelector('[name="card_number"]').value.trim()) errors.push('So the');
    if (!document.querySelector('[name="card_expiry"]').value.trim()) errors.push('han');
    if (!document.querySelector('[name="card_cvc"]').value.trim()) errors.push('CVC');
    if (!document.querySelector('[name="card_holder"]').value.trim()) errors.push('ten');
    if (errors.length) {
      e.preventDefault();
      errDiv.textContent = 'Vui long nhap day du thong tin the.';
      errDiv.classList.remove('d-none');
      return;
    }
  } else if (method === 'bank_transfer') {
    if (!document.querySelector('[name="bank_name"]').value.trim()) errors.push('bank');
    if (!document.querySelector('[name="transfer_name"]').value.trim()) errors.push('name');
    if (errors.length) {
      e.preventDefault();
      errDiv.textContent = 'Vui long nhap day du thong tin chuyen khoan.';
      errDiv.classList.remove('d-none');
      return;
    }
  }

  if (errDiv) errDiv.classList.add('d-none');
  var btn = document.getElementById('btn-pay');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Dang xu ly...';
  }
});