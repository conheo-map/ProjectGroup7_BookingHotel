document.querySelector('form').addEventListener('submit', function(e) {
    var p1 = document.getElementById('pw1').value;
    var p2 = document.getElementById('pw2').value;
    var msg = document.getElementById('pw-mismatch');
    if (p1 !== p2) { e.preventDefault(); msg.classList.remove('d-none'); }
    else { msg.classList.add('d-none'); }
});