document.getElementById('catalogSelect').addEventListener('change', function() {
    var opt = this.options[this.selectedIndex];
    if (opt.value) {
        document.getElementById('svcName').value = opt.dataset.name || '';
        document.getElementById('svcPrice').value = opt.dataset.price || 0;
    }
});