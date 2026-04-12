document.addEventListener('DOMContentLoaded', function() {
    var dataNode = document.getElementById('analytics-data');
    if (!dataNode) return;
    
    var analyticsData = JSON.parse(dataNode.textContent);
    var ctx = document.getElementById('analyticsChart');
    if (!ctx) return;

    if (!analyticsData || analyticsData.length === 0) {
        ctx.parentNode.innerHTML = '<div class="text-center py-5 text-muted"><i class="fas fa-chart-area fa-3x mb-2 d-block opacity-25"></i><p>Không có dữ liệu để hiển thị biểu đồ trong khoảng thời gian này.</p></div>';
        return;
    }

    var labels = analyticsData.map(function(d) { return d.time_label; });
    var bookings = analyticsData.map(function(d) { return d.total_bookings || 0; });
    var canceled = analyticsData.map(function(d) { return d.total_canceled || 0; });

    new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Số đặt phòng',
                    data: bookings,
                    backgroundColor: 'rgba(0, 53, 128, 0.75)',
                    borderColor: 'rgba(0, 53, 128, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                    order: 2
                },
                {
                    label: 'Số hủy phòng',
                    data: canceled,
                    backgroundColor: 'rgba(220, 53, 69, 0.75)',
                    borderColor: 'rgba(220, 53, 69, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top' },
                tooltip: { mode: 'index', intersect: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 1 },
                    title: { display: true, text: 'Số lượng' }
                },
                x: { title: { display: false } }
            }
        }
    });
});
