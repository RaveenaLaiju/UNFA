/* ─── Reveal on Scroll ─── */
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('revealed');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });
document.querySelectorAll('.reveal-up').forEach(el => revealObserver.observe(el));

/* ─── Counter Animation ─── */
const counterObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const el = entry.target;
      const target = parseInt(el.dataset.count) || 0;
      const duration = 2000;
      const start = performance.now();
      const step = (now) => {
        const progress = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 3);
        const current = Math.floor(ease * target);
        el.textContent = current.toLocaleString();
        if (progress < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      counterObserver.unobserve(el);
    }
  });
}, { threshold: 0.5 });
document.querySelectorAll('.counter-value').forEach(el => counterObserver.observe(el));

/* ─── Stat Bar Animation ─── */
const statBarObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const bar = entry.target;
      const width = bar.dataset.width || '0';
      setTimeout(() => { bar.style.width = width + '%'; }, 300);
      statBarObserver.unobserve(bar);
    }
  });
}, { threshold: 0.5 });
document.querySelectorAll('.stat-bar-fill').forEach(el => statBarObserver.observe(el));

/* ─── Scorer Bar Animation ─── */
const barObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const bar = entry.target;
      const width = bar.dataset.width || '80';
      setTimeout(() => { bar.style.width = width + '%'; }, 200);
      barObserver.unobserve(bar);
    }
  });
}, { threshold: 0.5 });
document.querySelectorAll('.scorer-bar').forEach(el => barObserver.observe(el));

/* ─── FancyBox Lightbox ─── */
if (typeof Fancybox !== 'undefined') {
  Fancybox.bind("[data-fancybox]", {
    Thumbs: { autoStart: false },
    Toolbar: { display: ["close"] }
  });
}

/* ─── Swiper: Fixtures ─── */
new Swiper('.fixtureSwiper', {
  slidesPerView: 1.1,
  spaceBetween: 20,
  freeMode: true,
  navigation: { nextEl: '.swiper-button-next', prevEl: '.swiper-button-prev' },
  pagination: { el: '.swiper-pagination', clickable: true },
  autoplay: { delay: 3500, disableOnInteraction: false },
  breakpoints: {
    640: { slidesPerView: 2.2 },
    1024: { slidesPerView: 3.2 },
    1440: { slidesPerView: 4 }
  }
});

/* ─── Swiper: Highlights (Cards Effect) ─── */
new Swiper('.highlightSwiper', {
  effect: 'cards',
  grabCursor: true,
  autoplay: { delay: 3000, disableOnInteraction: false },
  cardsEffect: { slideShadows: true, perSlideOffset: 10, perSlideRotate: 3 },
  pagination: { el: '.swiper-pagination', clickable: true }
});

/* ─── Swiper: Players (Coverflow) ─── */
new Swiper('.playerSwiper', {
  effect: 'coverflow',
  grabCursor: true,
  centeredSlides: true,
  slidesPerView: 'auto',
  loop: true,
  autoplay: { delay: 2500, disableOnInteraction: false },
  coverflowEffect: { rotate: 35, stretch: 0, depth: 200, modifier: 1, slideShadows: true },
  pagination: { el: '.swiper-pagination', clickable: true }
});

/* ─── Swiper: Clubs (Cards Effect) ─── */
new Swiper('.clubSwiper', {
  effect: 'cards',
  grabCursor: true,
  loop: true,
  autoplay: { delay: 2800, disableOnInteraction: false },
  cardsEffect: { slideShadows: true, perSlideOffset: 10, perSlideRotate: 3 },
  pagination: { el: '.swiper-pagination', clickable: true }
});

/* ─── Swiper: Tournaments (Coverflow) ─── */
new Swiper('.tournamentSwiper', {
  effect: 'coverflow',
  grabCursor: true,
  centeredSlides: true,
  slidesPerView: 'auto',
  loop: true,
  autoplay: { delay: 3000, disableOnInteraction: false },
  coverflowEffect: {
    rotate: 25,
    stretch: 0,
    depth: 200,
    modifier: 1,
    slideShadows: true
  },
  pagination: { el: '.swiper-pagination', clickable: true },
  breakpoints: {
    640: { slidesPerView: 'auto' },
    1024: { slidesPerView: 3 }
  }
});

/* ─── Tournament Spots Bar Animation ─── */
const spotsBarObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const bar = entry.target;
      const width = bar.dataset.width || '0';
      setTimeout(() => { bar.style.width = width + '%'; }, 400);
      spotsBarObserver.unobserve(bar);
    }
  });
}, { threshold: 0.5 });
document.querySelectorAll('.spots-bar-fill').forEach(el => spotsBarObserver.observe(el));