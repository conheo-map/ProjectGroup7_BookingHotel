document.addEventListener('DOMContentLoaded', function() {
    const dataNode = document.getElementById('manager-reports-data');
    if (!dataNode) return;
    
    const chartData = JSON.parse(dataNode.textContent);
    const labels = chartData.labels || [];
    const revenues = chartData.revenues || [];
    const bookings = chartData.bookings || [];

    if (document.getElementById('monthlyChart') && labels.length > 0) {
        new Chart(document.getElementById('monthlyChart'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Doanh thu (đ)',
                    data: revenues,
                    backgroundColor: 'rgba(0,53,128,.7)',
                    yAxisID: 'y'
                }, {
                    label: 'Đặt phòng',
                    data: bookings,
                    type: 'line',
                    borderColor: '#10b981',
                    backgroundColor: 'transparent',
                    pointBackgroundColor: '#10b981',
                    yAxisID: 'y1',
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { position: 'top' } },
                scales: {
                    y: { type: 'linear', position: 'left', ticks: { callback: v => v.toLocaleString('vi') + 'đ' } },
                    y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false } }
                }
            }
        });
    }
});
