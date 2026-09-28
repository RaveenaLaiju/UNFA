/* ═══════════════════════════════════════
   FOOTBALL ARENA - INTERACTIVE EFFECTS
   Particles | Parallax | Form FX
═══════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    initParticles();
    initParallax();
    initButtonEffects();
    initInputEffects();
    initStadiumAmbience();
});

/* ─── Trophy Particles System ─── */
function initParticles() {
    const container = document.getElementById('trophyParticles');
    const icons = ['⚽', '🏆', '⭐', '🥅', '👟', '🏟️', '🎯', '⚡'];
    const particleCount = window.innerWidth < 768 ? 12 : 20;

    for (let i = 0; i < particleCount; i++) {
        createParticle(container, icons, i);
    }
}

function createParticle(container, icons, index) {
    const particle = document.createElement('div');
    particle.className = 'particle';
    particle.textContent = icons[Math.floor(Math.random() * icons.length)];
    
    const size = Math.random() * 0.8 + 0.8;
    const left = Math.random() * 100;
    const duration = Math.random() * 15 + 10;
    const delay = Math.random() * 10;
    
    particle.style.cssText = `
        left: ${left}%;
        font-size: ${size}rem;
        animation-duration: ${duration}s;
        animation-delay: ${delay}s;
        filter: hue-rotate(${Math.random() * 60}deg);
    `;
    
    container.appendChild(particle);
    
    // Recycle particle after animation
    particle.addEventListener('animationend', () => {
        particle.remove();
        createParticle(container, icons, index);
    });
}

/* ─── Mouse Parallax on Card ─── */
function initParallax() {
    const card = document.getElementById('playerCard');
    if (!card || window.innerWidth < 768) return;

    let bounds = card.getBoundingClientRect();
    
    window.addEventListener('resize', () => {
        bounds = card.getBoundingClientRect();
    });

    document.addEventListener('mousemove', (e) => {
        const mouseX = e.clientX;
        const mouseY = e.clientY;
        const centerX = bounds.left + bounds.width / 2;
        const centerY = bounds.top + bounds.height / 2;
        
        const percentX = (mouseX - centerX) / (window.innerWidth / 2);
        const percentY = (mouseY - centerY) / (window.innerHeight / 2);
        
        const rotateX = percentY * -5;
        const rotateY = percentX * 5;
        
        card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    });

    document.addEventListener('mouseleave', () => {
        card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0)';
        card.style.transition = 'transform 0.5s ease';
    });
    
    card.addEventListener('mouseenter', () => {
        card.style.transition = 'transform 0.1s ease';
    });
}

/* ─── Button Interactive FX ─── */
function initButtonEffects() {
    const btn = document.getElementById('kickoffBtn');
    if (!btn) return;

    btn.addEventListener('mousemove', (e) => {
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        btn.style.background = `
            radial-gradient(circle at ${x}px ${y}px, 
            rgba(255,255,255,0.2) 0%, 
            transparent 50%),
            linear-gradient(135deg, #10b981 0%, #059669 100%)
        `;
    });

    btn.addEventListener('mouseleave', () => {
        btn.style.background = '';
    });
}

/* ─── Input Focus Effects ─── */
function initInputEffects() {
    const inputs = document.querySelectorAll('.squad-input');
    
    inputs.forEach(input => {
        input.addEventListener('focus', () => {
            input.parentElement.parentElement.style.transform = 'scale(1.02)';
            input.parentElement.parentElement.style.transition = 'transform 0.3s ease';
        });
        
        input.addEventListener('blur', () => {
            input.parentElement.parentElement.style.transform = 'scale(1)';
        });
    });
}

/* ─── Stadium Ambience ─── */
function initStadiumAmbience() {
    // Dynamic background shift based on time
    const hour = new Date().getHours();
    const bg = document.querySelector('.stadium-bg');
    
    if (hour >= 18 || hour < 6) {
        // Night match - darker
        bg.style.filter = 'brightness(0.5) contrast(1.3)';
    } else {
        // Day match - brighter
        bg.style.filter = 'brightness(0.7) contrast(1.2)';
    }
}

/* ─── Form Submission Animation ─── */
document.querySelector('.tactical-form')?.addEventListener('submit', function(e) {
    const btn = document.getElementById('kickoffBtn');
    
    btn.querySelector('.btn-text').textContent = 'Entering Stadium...';
    btn.style.pointerEvents = 'none';
    btn.style.opacity = '0.8';
    
    // Add loading particles
    for (let i = 0; i < 5; i++) {
        setTimeout(() => {
            const spark = document.createElement('div');
            spark.style.cssText = `
                position: absolute;
                width: 4px;
                height: 4px;
                background: #00ff88;
                border-radius: 50%;
                left: 50%;
                top: 50%;
                pointer-events: none;
                animation: explode 0.6s ease-out forwards;
            `;
            const angle = (i / 5) * Math.PI * 2;
            const velocity = 50;
            spark.style.setProperty('--tx', `${Math.cos(angle) * velocity}px`);
            spark.style.setProperty('--ty', `${Math.sin(angle) * velocity}px`);
            btn.appendChild(spark);
            
            setTimeout(() => spark.remove(), 600);
        }, i * 50);
    }
});

// Add explode animation dynamically
const style = document.createElement('style');
style.textContent = `
    @keyframes explode {
        to {
            transform: translate(var(--tx, 0), var(--ty, 0)) scale(0);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);