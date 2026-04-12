function toggleHotelType(btn, type) {
  btn.classList.toggle('active');
  const container = document.getElementById('hotel-type-inputs');
  // Xóa input cũ của loại này
  const existing = container.querySelector(`input[value="${type}"]`);
  if (existing) {
    existing.remove();
  } else {
    // Thêm mới nếu chọn
    const inp = document.createElement('input');
    inp.type = 'hidden';
    inp.name = 'hotel_types[]';
    inp.value = type;
    container.appendChild(inp);
  }
}