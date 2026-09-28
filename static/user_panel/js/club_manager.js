// Particle System
(function() {
  const container = document.getElementById('particles');
  const particleCount = 25;

  for (let i = 0; i < particleCount; i++) {
    const particle = document.createElement('div');
    particle.className = 'particle';
    particle.style.left = Math.random() * 100 + '%';
    particle.style.animationDuration = (Math.random() * 10 + 10) + 's';
    particle.style.animationDelay = Math.random() * 10 + 's';
    particle.style.opacity = Math.random() * 0.5 + 0.2;

    const colors = ['#ccff00', '#00f0ff', '#ffd700', '#ff3366'];
    particle.style.background = colors[Math.floor(Math.random() * colors.length)];
    particle.style.boxShadow = `0 0 ${Math.random() * 10 + 5}px ${particle.style.background}`;

    container.appendChild(particle);
  }
})();

// Intersection Observer for scroll animations
const observerOptions = {
  threshold: 0.1,
  rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const el = entry.target;
      const delay = el.getAttribute('data-delay') || '0';
      el.style.animationDelay = delay + 'ms';
      el.style.opacity = '1';
      observer.unobserve(el);
    }
  });
}, observerOptions);

document.querySelectorAll('[data-animate]').forEach(el => observer.observe(el));

// Stat bar animation
document.querySelectorAll('.bar-fill').forEach(bar => {
  const width = bar.style.width;
  bar.style.width = '0%';
  setTimeout(() => { bar.style.width = width; }, 500);
});

// Clubs

document.addEventListener('DOMContentLoaded', function() {
  // Intersection Observer for dramatic scroll reveals
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const delay = entry.target.dataset.delay || 0;
        setTimeout(() => {
          entry.target.classList.add('fc1-visible');
        }, delay * 80);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08, rootMargin: '0px 0px -50px 0px' });

  document.querySelectorAll('.fc1-transfer-link, .fc1-holo-card, .fc1-neon-billboard, .fc1-command-deck').forEach(el => {
    observer.observe(el);
  });

  // Live Search with Color Feedback
  const searchInput = document.getElementById('liveSearch');
  const clubContainer = document.getElementById('clubContainer');
  const countText = document.getElementById('clubCountText');
  const countBadge = document.getElementById('clubCount');

  if (searchInput) {
    searchInput.addEventListener('input', function(e) {
      const query = e.target.value.toLowerCase().trim();
      const cards = clubContainer.querySelectorAll('.fc1-transfer-link');
      let visibleCount = 0;

      cards.forEach(card => {
        const cardText = card.textContent.toLowerCase();
        if (cardText.includes(query)) {
          card.style.display = 'block';
          card.classList.remove('fc1-visible');
          setTimeout(() => card.classList.add('fc1-visible'), 50);
          visibleCount++;
        } else {
          card.style.display = 'none';
        }
      });

      countText.textContent = visibleCount;
      if (countBadge) countBadge.textContent = visibleCount;
      
      // Flash counter color on change
      countText.parentElement.style.borderColor = 'var(--fc1-neon-lime)';
      setTimeout(() => {
        countText.parentElement.style.borderColor = 'var(--fc1-glass-edge)';
      }, 300);
    });
  }

  // Dynamic OVR-based card coloring
  document.querySelectorAll('.fc1-player-holo-card').forEach(card => {
    const weight = parseInt(card.dataset.weight) || 0;
    const shell = card.querySelector('.fc1-holo-shell');
    
    if (weight >= 90) {
      shell.style.background = 'linear-gradient(135deg, rgba(255,240,31,0.8), rgba(255,0,170,0.8), rgba(0,240,255,0.8), rgba(255,240,31,0.8))';
      shell.style.backgroundSize = '400% 400%';
      card.querySelector('.fc1-ovr-shield').style.borderColor = 'var(--fc1-neon-gold)';
      card.querySelector('.fc1-ovr-shield').style.color = 'var(--fc1-neon-gold)';
      card.querySelector('.fc1-ovr-shield').style.boxShadow = '0 0 20px rgba(255,240,31,0.3)';
    } else if (weight >= 75) {
      shell.style.background = 'linear-gradient(135deg, rgba(0,240,255,0.7), rgba(176,38,255,0.7), rgba(0,240,255,0.7))';
      shell.style.backgroundSize = '300% 300%';
    }
  });
});