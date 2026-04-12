// ═══════════════════════════════════════════════════
// Main JS — Global behaviors for Hotel Booking System
// ═══════════════════════════════════════════════════

// Toast auto-hide
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.toast').forEach(function (el) {
        new bootstrap.Toast(el, { autohide: true, delay: 5000 }).show();
    });
});

// ── Staff Sidebar: toggle collapse/expand ──
function toggleSidebar() {
    var sidebar = document.getElementById('staff-sidebar');
    if (!sidebar) return;
    sidebar.classList.toggle('collapsed');
    localStorage.setItem('sb_collapsed', sidebar.classList.contains('collapsed') ? '1' : '0');
}

// Restore sidebar state on load
(function () {
    var sidebar = document.getElementById('staff-sidebar');
    if (sidebar && localStorage.getItem('sb_collapsed') === '1') {
        sidebar.classList.add('collapsed');
    }
})();

// ── Mobile sidebar ──
function openMobileSidebar() {
    var sidebar = document.getElementById('staff-sidebar');
    var overlay = document.getElementById('sb-overlay');
    if (sidebar) sidebar.classList.add('mobile-open');
    if (overlay) overlay.style.display = 'block';
}
function closeMobileSidebar() {
    var sidebar = document.getElementById('staff-sidebar');
    var overlay = document.getElementById('sb-overlay');
    if (sidebar) sidebar.classList.remove('mobile-open');
    if (overlay) overlay.style.display = 'none';
}

// ── Customer Navbar: scroll bubble effect ──
document.addEventListener('DOMContentLoaded', function() {
    var custNav = document.getElementById('customerNavbar');
    if (custNav) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 40) {
                custNav.classList.add('nav-scrolled');
            } else {
                custNav.classList.remove('nav-scrolled');
            }
        });
    }
});
