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
    var overlay = document.getElementById('thanhben-phu');
    if (sidebar) sidebar.classList.add('mobile-open');
    if (overlay) overlay.style.display = 'block';
}
function closeMobileSidebar() {
    var sidebar = document.getElementById('staff-sidebar');
    var overlay = document.getElementById('thanhben-phu');
    if (sidebar) sidebar.classList.remove('mobile-open');
    if (overlay) overlay.style.display = 'none';
}

// ── Customer Navbar: scroll bubble effect ──
document.addEventListener('DOMContentLoaded', function() {
    var custNav = document.getElementById('customerNavbar');
    if (custNav) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 40) {
                custNav.classList.add('dieu-huong-cuon');
            } else {
                custNav.classList.remove('dieu-huong-cuon');
            }
        });
    }
});

// --- SLIDE-IN PANEL LOGIC ---
document.addEventListener('DOMContentLoaded', function() {
    const triggers = document.querySelectorAll('[data-panel-trigger]');
    const panel = document.getElementById('infoPanel');
    const overlay = document.getElementById('infoOverlay');
    const closeBtn = document.getElementById('closeInfoPanel');
    const sections = document.querySelectorAll('.panel-section');

    function openPanel(type) {
        // Hide all sections first
        sections.forEach(s => s.classList.add('d-none'));
        
        // Show target section
        const target = document.getElementById('content-' + type);
        if (target) {
            target.classList.remove('d-none');
            
            // GSAP Animations
            overlay.classList.add('active');
            gsap.to(panel, { right: 0, duration: 0.6, ease: 'power3.out' });
            
            // Animate content inside
            gsap.from(target.children, {
                y: 30,
                opacity: 0,
                duration: 0.8,
                stagger: 0.1,
                ease: 'power2.out',
                delay: 0.2
            });
            
            document.body.style.overflow = 'hidden'; // Prevent scrolling background
        }
    }

    function closePanel() {
        overlay.classList.remove('active');
        gsap.to(panel, { right: '-100%', duration: 0.5, ease: 'power3.in' });
        document.body.style.overflow = '';
    }

    triggers.forEach(t => {
        t.addEventListener('click', (e) => {
            const type = t.getAttribute('data-panel-trigger');
            if (type) openPanel(type);
        });
    });

    if (closeBtn) closeBtn.addEventListener('click', closePanel);
    if (overlay) overlay.addEventListener('click', closePanel);

    // ESC key to close
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closePanel();
    });
});
