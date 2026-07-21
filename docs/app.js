/* Lingua Viva landing page JS: theme, nav behavior, hero/product animation. */

document.documentElement.classList.add('js');

const bannerItems = document.querySelectorAll('.fade-in');
bannerItems.forEach((el, index) => {
  setTimeout(() => el.classList.add('visible'), 100 + index * 60);
});

(function navScrollBehavior() {
  const nav = document.getElementById('nav');
  let lastY = 0;
  let ticking = false;
  if (!nav) return;
  window.addEventListener('scroll', () => {
    if (ticking) return;
    requestAnimationFrame(() => {
      const y = window.scrollY;
      if (y > 80) {
        nav.classList.add('nav--scrolled');
        nav.classList.toggle('nav--hidden', y > lastY + 10 && !nav.matches(':focus-within'));
      } else {
        nav.classList.remove('nav--scrolled', 'nav--hidden');
      }
      lastY = y;
      ticking = false;
    });
    ticking = true;
  }, { passive: true });
})();

(function themeInit() {
  const toggle = document.querySelector('[data-theme-toggle]');
  const root = document.documentElement;
  const storageKey = 'lingua-viva-theme';
  let currentTheme = 'dark';

  function storedTheme() {
    try {
      return window.localStorage.getItem(storageKey);
    } catch (_) {
      return null;
    }
  }

  function persistTheme(theme) {
    try {
      window.localStorage.setItem(storageKey, theme);
    } catch (_) {
      /* Theme persistence is best-effort. */
    }
  }

  function setTheme(theme, persist = false) {
    currentTheme = theme;
    root.dataset.theme = theme;
    const dark = theme === 'dark';
    if (!toggle) return;
    toggle.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
    toggle.setAttribute('aria-pressed', String(!dark));
    toggle.innerHTML = dark
      ? '<svg aria-hidden="true" focusable="false" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>'
      : '<svg aria-hidden="true" focusable="false" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.2" y1="4.2" x2="5.6" y2="5.6"/><line x1="18.4" y1="18.4" x2="19.8" y2="19.8"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.2" y1="19.8" x2="5.6" y2="18.4"/><line x1="18.4" y1="5.6" x2="19.8" y2="4.2"/></svg>';
    if (persist) persistTheme(theme);
  }

  setTheme(storedTheme() || currentTheme);
  toggle?.addEventListener('click', () => {
    setTheme(currentTheme === 'dark' ? 'light' : 'dark', true);
  });
})();

(function productDemo() {
  const capture = document.getElementById('demoCapture');
  const proof = document.getElementById('demoProof');
  const lensCards = [document.getElementById('lensOne'), document.getElementById('lensTwo')].filter(Boolean);
  const chips = [document.getElementById('demoChipOne'), document.getElementById('demoChipTwo')].filter(Boolean);
  if (!capture) return;

  const text = 'Marco self-corrected passato prossimo and used essere correctly in a partner exchange.';
  const timers = [];

  function at(delay, fn) {
    timers.push(window.setTimeout(fn, delay));
  }

  function clear() {
    while (timers.length) window.clearTimeout(timers.pop());
  }

  function reset() {
    capture.textContent = '';
    proof?.classList.remove('visible');
    lensCards.forEach(card => card.classList.remove('visible'));
    chips.forEach(chip => chip.classList.remove('visible'));
  }

  function showStatic() {
    capture.textContent = text;
    proof?.classList.add('visible');
    lensCards.forEach(card => card.classList.add('visible'));
    chips.forEach(chip => chip.classList.add('visible'));
  }

  function play() {
    clear();
    reset();
    const step = 3600 / text.length;
    [...text].forEach((char, index) => {
      at(index * step, () => { capture.textContent += char; });
    });
    at(3900, () => chips.forEach((chip, index) => at(index * 220, () => chip.classList.add('visible'))));
    at(4500, () => lensCards[0]?.classList.add('visible'));
    at(5200, () => lensCards[1]?.classList.add('visible'));
    at(6100, () => proof?.classList.add('visible'));
    at(9800, play);
  }

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    showStatic();
    return;
  }
  play();
})();

document.querySelectorAll('.btn-disabled').forEach((button) => {
  button.addEventListener('click', (event) => {
    event.preventDefault();
  });
  button.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') event.preventDefault();
  });
});
