// Amenity preview chips
const amenityInput = document.querySelector('textarea[name="amenities"]');
const amenityPreview = document.getElementById('amenityPreview');

function renderAmenityChips() {
    if (!amenityInput || !amenityPreview) return;
    const val = amenityInput.value;
    if (!val.trim()) { amenityPreview.innerHTML = ''; return; }
    const items = val.split(',').map(s => s.trim()).filter(Boolean);
    amenityPreview.innerHTML = items.map(a =>
        '<span class="badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-20">' +
        '<i class="fas fa-check-circle me-1"></i>' + a + '</span>'
    ).join('');
}
if (amenityInput) {
    amenityInput.addEventListener('input', renderAmenityChips);
    renderAmenityChips();
}

// Upload preview & AJAX Submit
async function previewAndSubmit(input) {
    console.log("previewAndSubmit triggered", input);
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    if (file.size > 5 * 1024 * 1024) {
        alert('File quá lớn (tối đa 5MB)');
        input.value = '';
        return;
    }
    
    // Hiển thị trạng thái đang tải
    const uploadZoneContent = document.querySelector('.suaphong-tai-khu-noidung');
    let originalContent = '';
    if (uploadZoneContent) {
        originalContent = uploadZoneContent.innerHTML;
        uploadZoneContent.innerHTML = 
            '<i class="fas fa-spinner fa-spin fa-2x text-primary mb-2"></i>' +
            '<p class="mb-0 fw-bold">Đang tải ảnh lên...</p>' +
            '<p class="kichthuoc-nho-hon text-muted">Vui lòng đợi giây lát</p>';
    }
    
    // AJAX Upload
    const form = input.form || document.getElementById('uploadForm') || input.closest('form');
    if (!form) {
        console.error("Critical: Form not found for input", input);
        alert("Lỗi hệ thống: Không xác định được form tải lên. Vui lòng tải lại trang.");
        if (uploadZoneContent) uploadZoneContent.innerHTML = originalContent;
        return;
    }

    console.log("Using form:", form.action);
    const formData = new FormData();
    formData.append('image', file);

    try {
        const response = await fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!response.ok) {
            throw new Error(`Server status ${response.status}`);
        }

        const result = await response.json();
        console.log("Upload response:", result);
        if (result.success) {
            if (uploadZoneContent) {
                uploadZoneContent.innerHTML = 
                    '<i class="fas fa-check-circle fa-2x text-success mb-2"></i>' +
                    '<p class="mb-0 fw-bold">Thành công!</p>';
            }
            setTimeout(() => window.location.reload(), 500);
        } else {
            alert("Lỗi: " + (result.message || "Tải lên thất bại"));
            if (uploadZoneContent) uploadZoneContent.innerHTML = originalContent;
            input.value = '';
        }
    } catch (err) {
        console.error("AJAX Error:", err);
        alert("Lỗi tải lên: " + err.message);
        if (uploadZoneContent) uploadZoneContent.innerHTML = originalContent;
        input.value = '';
    }
}

function cancelPreview() {
    const input = document.getElementById('imageInput');
    if (input) input.value = '';
    const preview = document.getElementById('uploadPreview');
    if (preview) preview.classList.add('d-none');
    const content = document.querySelector('.suaphong-tai-khu-noidung');
    if (content) content.classList.remove('d-none');
}

// Drag & drop
const zone = document.getElementById('uploadZone');
if (zone) {
    zone.addEventListener('dragover', e => { 
        e.preventDefault(); 
        zone.classList.add('dragover'); 
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
        
        const input = document.getElementById('imageInput');
        if (!input) return;

        if (e.dataTransfer.files.length > 0) {
            input.files = e.dataTransfer.files;
            previewAndSubmit(input);
        } else {
            const html = e.dataTransfer.getData('text/html');
            if (html) {
                const imgMatch = html.match(/src="([^"]+)"/);
                if (imgMatch) {
                   alert("Bạn đang kéo ảnh từ trang web khác. Vui lòng TẢI ẨNH VỀ MÁY trước rồi mới kéo vào đây để upload.");
                }
            } else {
                alert("Vui lòng kéo một tệp hình ảnh từ máy tính của bạn.");
            }
        }
    });
}