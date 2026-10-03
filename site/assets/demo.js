/* The live demos on the page. A small copy of the app's lyric engine: the same six styles
   with the same timings, scale, fade and "lead" as src/lyric_styles.py in the app. */
(() => {
  'use strict';

  const SONG = [
    'Tabs stacked up to the sky',
    'Cursor blinking, deadline nigh',
    'Then the chorus finds me here',
    'Floating where my eyes are clear',
    'No more switching, no lost beat',
    'Every line lands on its feet',
    'Sing it softly, sing it loud',
    'Right above the working crowd',
    'Turn it up, the verse is near',
    'Words arrive just when I hear',
  ];
  const GAP = 3.0;          // seconds from one line to the next
  const FIRST = 0.8;        // when the first line starts
  const LENGTH = FIRST + SONG.length * GAP;

  const OUT_CUBIC = 'cubic-bezier(.215,.61,.355,1)';
  // The app's "OutBack" easing, written out as a CSS linear() curve so the overshoot is the same.
  const backOut = (overshoot) => {
    if (!(window.CSS && CSS.supports && CSS.supports('transition-timing-function', 'linear(0, 1)'))) {
      return 'cubic-bezier(.34,1.56,.64,1)';
    }
    const pts = [];
    for (let i = 0; i <= 30; i++) {
      const t = i / 30 - 1;
      pts.push((t * t * ((overshoot + 1) * t + overshoot) + 1).toFixed(3));
    }
    return `linear(${pts.join(',')})`;
  };

  const STYLES = {
    smooth:     { label: 'Smooth',     hint: 'The current line grows and brightens while the list glides to it.',
                  scale: 1.22, emph: 280, ease: OUT_CUBIC, scroll: 480, sease: OUT_CUBIC, near: .72, step: .06, floor: .40, future: null, mode: 'none',  lead: .15 },
    karaoke:    { label: 'Karaoke',    hint: 'Colour sweeps across each line as it is sung, and stays on lines already sung.',
                  scale: 1.14, emph: 240, ease: OUT_CUBIC, scroll: 480, sease: OUT_CUBIC, near: .60, step: .06, floor: .32, future: null, mode: 'sweep', lead: .10 },
    typewriter: { label: 'Typewriter', hint: 'Each line types itself out as it starts. Upcoming lines stay hidden.',
                  scale: 1.12, emph: 200, ease: OUT_CUBIC, scroll: 420, sease: OUT_CUBIC, near: .55, step: .07, floor: .28, future: 0,    mode: 'type',  lead: 0 },
    pop:        { label: 'Pop',        hint: 'Each new line bounces in with a little overshoot.',
                  scale: 1.30, emph: 560, ease: 'back3.4', scroll: 560, sease: 'back.9', near: .72, step: .06, floor: .40, future: null, mode: 'none', lead: .15 },
    spotlight:  { label: 'Spotlight',  hint: 'Only the current line stands out; everything else fades into the background.',
                  scale: 1.26, emph: 340, ease: OUT_CUBIC, scroll: 520, sease: OUT_CUBIC, near: .24, step: .06, floor: .09, future: null, mode: 'none',  lead: .15 },
    instant:    { label: 'Instant',    hint: 'No animation: lines switch and scroll immediately.',
                  scale: 1.22, emph: 0,   ease: 'linear',  scroll: 0,   sease: 'linear',  near: .72, step: .06, floor: .40, future: null, mode: 'none',  lead: 0 },
  };
  const easing = (e) => e === 'back3.4' ? backOut(3.4) : e === 'back.9' ? backOut(0.9) : e;
  const reduced = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---------------------------------------------------------------- hero demo
  const lyrics = document.getElementById('demo');
  const track = document.getElementById('demo-track');
  if (!lyrics || !track) return;

  const lines = SONG.map((text) => {
    const el = document.createElement('div');
    el.className = 'line';
    el.textContent = text;
    track.appendChild(el);
    return el;
  });

  let styleKey = reduced ? 'instant' : 'smooth';
  let style = STYLES[styleKey];
  let current = -1;
  let t = reduced ? FIRST + 2 * GAP + 0.4 : 0;
  let playing = !reduced;
  let onScreen = true;
  let lineH = 48;
  let touched = false;   // the visitor has chosen something themselves

  const alphaFor = (distance) => {
    if (distance === 0) return 1;
    if (distance > 0 && style.future !== null) return style.future;
    return Math.max(style.floor, style.near - style.step * (Math.abs(distance) - 1));
  };

  function layout() {
    lineH = lines[0].offsetHeight || 48;
    const pad = Math.max(0, lyrics.clientHeight / 2 - lineH / 2);
    track.style.paddingBlock = pad + 'px';
    place(current < 0 ? 0 : current, true);
  }

  function place(i, instant) {
    if (instant) track.classList.add('is-jump');
    track.style.setProperty('--y', (-i * lineH) + 'px');
    if (instant) { void track.offsetHeight; requestAnimationFrame(() => track.classList.remove('is-jump')); }
  }

  function look(i) {
    lines.forEach((el, k) => {
      const d = k - i;
      el.style.setProperty('--a', alphaFor(d).toFixed(3));
      el.style.setProperty('--s', d === 0 ? style.scale : 1);
      el.classList.toggle('is-now', d === 0);
      if (style.mode === 'sweep') el.style.setProperty('--p', k < i ? 1 : 0);
      if (style.mode === 'type') el.style.setProperty('--t', k < i ? 1 : 0);
    });
  }

  function applyStyleVars() {
    lyrics.dataset.style = styleKey;
    lyrics.dataset.mode = style.mode;
    lyrics.style.setProperty('--emph', style.emph + 'ms');
    lyrics.style.setProperty('--emph-ease', easing(style.ease));
    lyrics.style.setProperty('--scroll', style.scroll + 'ms');
    lyrics.style.setProperty('--scroll-ease', easing(style.sease));
    lines.forEach((el) => { el.style.removeProperty('--p'); el.style.removeProperty('--t'); });
  }

  function setCurrent(i, instant) {
    current = i;
    look(i);
    place(i, instant);
  }

  function progressFor(i) {
    const start = FIRST + i * GAP;
    if (style.mode === 'sweep') return (t - start) / Math.max(0.3, GAP - style.lead);
    const chars = SONG[i].length;
    return (t - start) / Math.min(Math.max(0.6, chars * 0.045), GAP * 0.8);
  }

  function frame(now) {
    const dt = Math.min(0.1, (now - (frame.last || now)) / 1000);
    frame.last = now;
    if (playing && onScreen && !document.hidden) {
      t += dt;
      let wrapped = false;
      if (t >= LENGTH) { t -= LENGTH; wrapped = true; }
      const idx = Math.max(0, Math.min(SONG.length - 1, Math.floor((t + style.lead - FIRST) / GAP)));
      if (wrapped || idx !== current) setCurrent(idx, wrapped);
      if (style.mode !== 'none' && current >= 0) {
        const p = Math.max(0, Math.min(1, progressFor(current)));
        const el = lines[current];
        if (style.mode === 'sweep') el.style.setProperty('--p', p.toFixed(3));
        else el.style.setProperty('--t', (Math.floor(p * SONG[current].length) / SONG[current].length).toFixed(3));
      }
    }
    requestAnimationFrame(frame);
  }

  function setStyle(key, fromUser) {
    if (!STYLES[key] || key === styleKey && current >= 0) return;
    styleKey = key;
    style = STYLES[key];
    applyStyleVars();
    const idx = current < 0 ? 0 : current;
    look(idx);
    place(idx, true);
    syncControls();
    document.dispatchEvent(new CustomEvent('td-style', { detail: key }));
    if (fromUser && reduced) { /* nothing to restart: the user has asked for motion */ }
  }

  // ---- controls under the stage
  const seg = document.getElementById('style-seg');
  const hint = document.getElementById('style-hint');
  const pauseBtn = document.getElementById('pause');
  const pauseText = document.getElementById('pause-text');
  const pauseIcon = document.getElementById('pause-icon');

  Object.entries(STYLES).forEach(([key, s]) => {
    const b = document.createElement('button');
    b.type = 'button'; b.setAttribute('role', 'radio'); b.dataset.key = key; b.textContent = s.label;
    seg.appendChild(b);
  });

  function syncControls() {
    seg.querySelectorAll('button').forEach((b) => {
      const on = b.dataset.key === styleKey;
      b.setAttribute('aria-checked', on);
      b.tabIndex = on ? 0 : -1;
    });
    hint.textContent = (reduced && !touched)
      ? 'Your system asks for less motion, so this starts paused on Instant. Pick a style, or press Play, to see it move.'
      : style.hint;
  }

  seg.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    touched = true;
    setStyle(b.dataset.key, true);
    if (reduced && !playing) togglePlay(true);
  });
  seg.addEventListener('keydown', (e) => {
    const keys = Object.keys(STYLES);
    let i = keys.indexOf(styleKey);
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') i = (i + 1) % keys.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') i = (i + keys.length - 1) % keys.length;
    else return;
    e.preventDefault();
    touched = true;
    setStyle(keys[i], true);
    if (reduced && !playing) togglePlay(true);
    seg.querySelector('[aria-checked="true"]').focus();
  });

  function togglePlay(forcePlay) {
    if (typeof forcePlay === 'boolean') playing = forcePlay; else playing = !playing;
    renderPlayState();
  }
  function renderPlayState() {
    pauseBtn.setAttribute('aria-pressed', !playing);
    pauseText.textContent = playing ? 'Pause' : 'Play';
    pauseIcon.innerHTML = playing
      ? '<rect x="2" y="1" width="3" height="10" rx="1"/><rect x="7" y="1" width="3" height="10" rx="1"/>'
      : '<path d="M3 1.5v9l7.5-4.5z"/>';
  }
  pauseBtn.addEventListener('click', () => { touched = true; togglePlay(); syncControls(); });

  // follow changes made in the settings pane below
  document.addEventListener('td-style', (e) => { if (e.detail !== styleKey) setStyle(e.detail, false); });

  // only run while the stage can be seen
  if ('IntersectionObserver' in window) {
    new IntersectionObserver((entries) => { onScreen = entries[0].isIntersecting; }, { threshold: 0.15 })
      .observe(lyrics.closest('.stage'));
  }

  applyStyleVars();
  syncControls();
  renderPlayState();
  layout();
  setCurrent(Math.max(0, Math.min(SONG.length - 1, Math.floor((t + style.lead - FIRST) / GAP))), true);
  window.addEventListener('resize', layout);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(layout);
  requestAnimationFrame(frame);

  // ---------------------------------------------------------------- unlock + settings demo
  const stage = document.getElementById('make-stage');
  if (!stage) return;
  const unlockBtn = document.getElementById('unlock-btn');
  const state = document.getElementById('make-state');
  const gear = document.getElementById('gear');
  const pane = document.getElementById('pane');
  const paneStyle = document.getElementById('pane-style');
  const paneHint = document.getElementById('pane-hint');

  // the gear's teeth
  const teeth = document.getElementById('teeth');
  for (let k = 0; k < 8; k++) {
    const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r.setAttribute('x', -2.2); r.setAttribute('y', -9.6); r.setAttribute('width', 4.4);
    r.setAttribute('height', 6); r.setAttribute('rx', 1.1); r.setAttribute('transform', `rotate(${k * 45})`);
    teeth.appendChild(r);
  }

  Object.entries(STYLES).forEach(([key, s]) => {
    const o = document.createElement('option'); o.value = key; o.textContent = s.label; paneStyle.appendChild(o);
  });
  const syncPane = () => { paneStyle.value = styleKey; paneHint.textContent = STYLES[styleKey].hint; };
  paneStyle.addEventListener('change', () => setStyle(paneStyle.value, true));
  document.addEventListener('td-style', syncPane);
  syncPane();

  let unlocked = false;
  function setUnlocked(on) {
    unlocked = on;
    stage.dataset.unlocked = on;
    gear.disabled = !on;
    gear.setAttribute('aria-hidden', !on);
    unlockBtn.setAttribute('aria-pressed', on);
    unlockBtn.textContent = on ? 'Lock it again' : 'Try unlocking it';
    state.textContent = on
      ? 'Unlocked. The screen dims, the window gets a blue edge and an opacity bar, and the gear appears. Click it.'
      : "Locked. It's just the lyrics.";
    if (!on) closePane(false);
  }
  function openPane() { pane.hidden = false; gear.setAttribute('aria-expanded', 'true'); }
  function closePane(refocus) {
    pane.hidden = true; gear.setAttribute('aria-expanded', 'false');
    if (refocus) gear.focus();
  }
  unlockBtn.addEventListener('click', () => setUnlocked(!unlocked));
  gear.addEventListener('click', () => (pane.hidden ? openPane() : closePane(false)));
  stage.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !pane.hidden) { e.preventDefault(); closePane(true); } });
  setUnlocked(false);

  // the app's real shortcut also works here, when nothing is being typed into
  document.addEventListener('keydown', (e) => {
    if (!(e.ctrlKey && e.altKey && e.code === 'KeyL')) return;
    const a = document.activeElement;
    if (a && (a.matches('input, textarea, select') || a.isContentEditable)) return;
    e.preventDefault();
    setUnlocked(!unlocked);
  });

  // the pane's tabs
  const tabs = pane.querySelectorAll('[role="tab"]');
  tabs.forEach((tab) => tab.addEventListener('click', () => {
    tabs.forEach((x) => x.setAttribute('aria-selected', x === tab));
    pane.querySelectorAll('[data-page]').forEach((p) => { p.hidden = p.dataset.page !== tab.dataset.tab; });
  }));
  pane.querySelector('.pane__tabs').addEventListener('keydown', (e) => {
    const list = [...tabs]; const i = list.indexOf(document.activeElement);
    if (i < 0) return;
    const next = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : null;
    if (next === null || next < 0 || next >= list.length) return;
    e.preventDefault(); list[next].focus(); list[next].click();
  });
  pane.querySelector('.quit').addEventListener('click', () => {
    state.textContent = 'In the real app, that closes Top Display. Here, nothing happens.';
  });
})();
