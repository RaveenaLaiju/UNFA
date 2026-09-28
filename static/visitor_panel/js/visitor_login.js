// Tab Switching with Animation
  function switchTab(tab) {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const tabLogin = document.getElementById('tabLogin');
    const tabRegister = document.getElementById('tabRegister');

    if (tab === 'login') {
      registerForm.style.display = 'none';
      loginForm.style.display = 'flex';
      loginForm.classList.add('tab-switch-enter');
      
      tabLogin.classList.add('active');
      tabRegister.classList.remove('active');
      
      setTimeout(() => loginForm.classList.remove('tab-switch-enter'), 400);
    } else {
      loginForm.style.display = 'none';
      registerForm.style.display = 'flex';
      registerForm.classList.add('tab-switch-enter');
      
      tabRegister.classList.add('active');
      tabLogin.classList.remove('active');
      
      setTimeout(() => registerForm.classList.remove('tab-switch-enter'), 400);
    }
  }

  // Check URL hash for tab
  if (window.location.hash === '#register') {
    switchTab('register');
  }

  // Particle Generator
  function createParticles() {
    const container = document.getElementById('particlesContainer');
    const particleCount = 20;
    
    for (let i = 0; i < particleCount; i++) {
      const particle = document.createElement('div');
      particle.className = 'particle';
      particle.style.left = Math.random() * 100 + '%';
      particle.style.animationDelay = Math.random() * 15 + 's';
      particle.style.animationDuration = (Math.random() * 10 + 10) + 's';
      container.appendChild(particle);
    }
  }

  // Input Focus Effects
  document.querySelectorAll('.glass-input').forEach(input => {
    input.addEventListener('focus', function() {
      this.parentElement.style.transform = 'scale(1.02)';
      this.parentElement.style.transition = 'transform 0.3s ease';
    });
    
    input.addEventListener('blur', function() {
      this.parentElement.style.transform = 'scale(1)';
    });
  });

  // Initialize
  document.addEventListener('DOMContentLoaded', () => {
    createParticles();
  });

  // Form submission loading state
  document.querySelectorAll('.auth-form').forEach(form => {
    form.addEventListener('submit', function(e) {
      const btn = this.querySelector('.submit-btn');
      const originalText = btn.innerHTML;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
      btn.disabled = true;
      btn.style.opacity = '0.8';
      
      // Re-enable after 3 seconds in case of error
      setTimeout(() => {
        btn.innerHTML = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';
      }, 3000);
    });
  });