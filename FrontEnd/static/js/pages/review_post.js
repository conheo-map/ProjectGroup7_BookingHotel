document.querySelectorAll('input[name="rating"]').forEach(function(radio) {
    radio.addEventListener('change', function() {
        document.querySelectorAll('.btn-outline-warning').forEach(function(btn) {
            btn.classList.remove('active', 'btn-warning');
            btn.classList.add('btn-outline-warning');
        });
        this.nextElementSibling.classList.remove('btn-outline-warning');
        this.nextElementSibling.classList.add('btn-warning', 'active');
    });
});