/* ===== NAV SCROLL ===== */
const nav = document.getElementById('nav');
window.addEventListener('scroll', () => {
  nav.classList.toggle('scrolled', window.scrollY > 60);
});

/* ===== MOBILE NAV ===== */
const burger = document.getElementById('burger');
const navLinks = document.querySelector('.nav__links');
burger.addEventListener('click', () => {
  const isOpen = navLinks.style.display === 'flex';
  navLinks.style.display = isOpen ? 'none' : 'flex';
  if (!isOpen) {
    navLinks.style.flexDirection = 'column';
    navLinks.style.position = 'absolute';
    navLinks.style.top = '100%';
    navLinks.style.left = '0';
    navLinks.style.right = '0';
    navLinks.style.background = 'rgba(10,10,10,0.98)';
    navLinks.style.padding = '2rem 5%';
    navLinks.style.gap = '1.5rem';
    navLinks.style.borderBottom = '1px solid rgba(201,168,76,0.2)';
  }
});

/* ===== PARTICLES ===== */
function createParticles() {
  const container = document.getElementById('particles');
  if (!container) return;
  for (let i = 0; i < 40; i++) {
    const p = document.createElement('div');
    p.className = 'particle';
    const size = Math.random() * 3 + 1;
    p.style.cssText = `
      left: ${Math.random() * 100}%;
      top: ${Math.random() * 100}%;
      width: ${size}px;
      height: ${size}px;
      animation-duration: ${Math.random() * 8 + 6}s;
      animation-delay: ${Math.random() * 8}s;
    `;
    container.appendChild(p);
  }
}
createParticles();

/* ===== COUNTER ANIMATION ===== */
function animateCounter(el) {
  const target = parseInt(el.dataset.target, 10);
  const duration = 2000;
  const step = target / (duration / 16);
  let current = 0;
  const timer = setInterval(() => {
    current += step;
    if (current >= target) {
      el.textContent = target;
      clearInterval(timer);
    } else {
      el.textContent = Math.floor(current);
    }
  }, 16);
}

/* ===== SCROLL REVEAL ===== */
const revealElements = [];

function setupReveal() {
  const selectors = [
    '.about__grid', '.program-card', '.process__step',
    '.testimonial', '.pricing-card', '.contact__info', '.contact__form',
    '.section-eyebrow', '.section-title'
  ];
  selectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.classList.add('reveal');
      revealElements.push(el);
    });
  });
}

function checkReveal() {
  const vh = window.innerHeight;
  revealElements.forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.top < vh * 0.9 && !el.classList.contains('visible')) {
      el.classList.add('visible');
    }
  });

  // Counters
  document.querySelectorAll('.stat__num').forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.top < vh && !el.dataset.counted) {
      el.dataset.counted = true;
      animateCounter(el);
    }
  });
}

setupReveal();
window.addEventListener('scroll', checkReveal, { passive: true });
checkReveal();

/* ===== FORM SUBMIT ===== */
const form = document.getElementById('contactForm');
const modal = document.getElementById('modal');
const modalClose = document.getElementById('modalClose');

form.addEventListener('submit', (e) => {
  e.preventDefault();
  modal.classList.add('open');
  form.reset();
});

modalClose.addEventListener('click', () => {
  modal.classList.remove('open');
});

modal.addEventListener('click', (e) => {
  if (e.target === modal) modal.classList.remove('open');
});

/* ===== SMOOTH ANCHOR SCROLL ===== */
document.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener('click', (e) => {
    const href = link.getAttribute('href');
    if (href === '#') return;
    const target = document.querySelector(href);
    if (!target) return;
    e.preventDefault();
    const offset = 80;
    const top = target.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top, behavior: 'smooth' });
    // close mobile nav if open
    if (navLinks.style.display === 'flex' && navLinks.style.position === 'absolute') {
      navLinks.style.display = 'none';
    }
  });
});
