// Amenity preview chips
const amenityInput = document.querySelector('textarea[name="amenities"]');
const amenityPreview = document.getElementById('amenityPreview');

function renderAmenityChips() {
    const val = amenityInput.value;
    if (!val.trim()) { amenityPreview.innerHTML = ''; return; }
    const items = val.split(',').map(s => s.trim()).filter(Boolean);
    amenityPreview.innerHTML = items.map(a =>
        '<span class="badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-20">' +
        '<i class="fas fa-check-circle me-1"></i>' + a + '</span>'
    ).join('');
}
amenityInput.addEventListener('input', renderAmenityChips);
renderAmenityChips();

// Upload preview
function previewAndSubmit(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    if (file.size > 5 * 1024 * 1024) {
        alert('File quá lớn (tối đa 5MB)');
        input.value = '';
        return;
    }
    const reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById('previewImg').src = e.target.result;
        document.getElementById('uploadPreview').classList.remove('d-none');
        document.querySelector('.re-upload-zone__content').classList.add('d-none');
    };
    reader.readAsDataURL(file);
}

function cancelPreview() {
    document.getElementById('imageInput').value = '';
    document.getElementById('uploadPreview').classList.add('d-none');
    document.querySelector('.re-upload-zone__content').classList.remove('d-none');
}

// Drag & drop
const zone = document.getElementById('uploadZone');
if (zone) {
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const input = document.getElementById('imageInput');
        if (e.dataTransfer.files.length > 0) {
            input.files = e.dataTransfer.files;
            previewAndSubmit(input);
        }
    });
}