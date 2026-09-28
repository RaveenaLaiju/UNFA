/* ═══════════════════════════════════════════════════════
   FOOTBALL ARENA — COMPLETE INTERACTIVE SYSTEM
═══════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    initParticles();
    initDugout();
    initCounters();
    initMatchTimer();
    initStadiumAmbience();
    initAlertDismiss();
});

/* ─── Trophy Particles ─── */
function initParticles() {
    const container = document.getElementById('trophyParticles');
    if (!container) return;
    
    const icons = ['⚽', '🏆', '⭐', '🥅', '👟', '🏟️', '🎯', '⚡', '🏃', '🌟'];
    const count = window.innerWidth < 768 ? 10 : 18;

    for (let i = 0; i < count; i++) {
        spawnParticle(container, icons);
    }
}

function spawnParticle(container, icons) {
    const p = document.createElement('div');
    p.className = 'particle';
    p.textContent = icons[Math.floor(Math.random() * icons.length)];
    
    const size = Math.random() * 0.7 + 0.6;
    const left = Math.random() * 100;
    const duration = Math.random() * 12 + 8;
    const delay = Math.random() * 8;
    
    p.style.cssText = `
        left: ${left}%;
        font-size: ${size}rem;
        animation-duration: ${duration}s;
        animation-delay: ${delay}s;
        filter: hue-rotate(${Math.random() * 40}deg);
    `;
    
    container.appendChild(p);
    p.addEventListener('animationend', () => {
        p.remove();
        spawnParticle(container, icons);
    });
}

/* ─── Dugout Mobile Toggle ─── */
function initDugout() {
    const toggle = document.getElementById('whistleToggle');
    const dugout = document.getElementById('dugout');
    const overlay = document.getElementById('pitchOverlay');
    
    if (!toggle || !dugout) return;

    toggle.addEventListener('click', () => {
        dugout.classList.toggle('open');
        overlay?.classList.toggle('active');
        toggle.querySelector('.whistle-icon').textContent = 
            dugout.classList.contains('open') ? '✕' : '☰';
    });

    overlay?.addEventListener('click', () => {
        dugout.classList.remove('open');
        overlay.classList.remove('active');
        toggle.querySelector('.whistle-icon').textContent = '☰';
    });

    // Close on link click (mobile)
    dugout.querySelectorAll('.play-link').forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                dugout.classList.remove('open');
                overlay?.classList.remove('active');
                toggle.querySelector('.whistle-icon').textContent = '☰';
            }
        });
    });
}

/* ─── Animated Counters ─── */
function initCounters() {
    const counters = document.querySelectorAll('.stat-score[data-target]');
    
    counters.forEach(counter => {
        const target = parseInt(counter.getAttribute('data-target')) || 0;
        const duration = 1500;
        const step = target / (duration / 16);
        let current = 0;
        
        const update = () => {
            current += step;
            if (current < target) {
                counter.textContent = Math.floor(current).toLocaleString();
                requestAnimationFrame(update);
            } else {
                counter.textContent = target.toLocaleString();
            }
        };
        
        // Intersection Observer for scroll-trigger
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    update();
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });
        
        observer.observe(counter);
    });
}

/* ─── Match Timer ─── */
function initMatchTimer() {
    const timer = document.getElementById('matchTimer');
    if (!timer) return;
    
    let seconds = 0;
    setInterval(() => {
        seconds++;
        const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
        const secs = (seconds % 60).toString().padStart(2, '0');
        timer.textContent = `${mins}:${secs}`;
    }, 1000);
}

/* ─── Stadium Ambience ─── */
function initStadiumAmbience() {
    const hour = new Date().getHours();
    const bg = document.querySelector('.stadium-bg');
    if (!bg) return;
    
    if (hour >= 18 || hour < 6) {
        bg.style.filter = 'brightness(0.45) contrast(1.3)';
    } else {
        bg.style.filter = 'brightness(0.65) contrast(1.15)';
    }
}

/* ─── Auto-dismiss Alerts ─── */
function initAlertDismiss() {
    const alerts = document.querySelectorAll('.match-alerts-toast .alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.animation = 'fadeOut 0.4s ease-in forwards';
            setTimeout(() => alert.remove(), 400);
        }, 5000);
    });
}