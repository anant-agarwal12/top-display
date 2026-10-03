/* Fills in the download button and details from release.json (same origin, no third parties).
   Without JavaScript the button simply opens the GitHub releases page. */
(() => {
  'use strict';
  const set = (name, value) => document.querySelectorAll(`[data-release="${name}"]`).forEach((el) => { el.textContent = value; });

  fetch('release.json', { cache: 'no-cache' })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
    .then((rel) => {
      if (!rel || !/^https:\/\/github\.com\/anant-agarwal12\/top-display\//.test(rel.url)) return;
      document.querySelectorAll('[data-release-link]').forEach((a) => { a.href = rel.url; });
      set('version', rel.version);
      set('size', `${rel.size_mb} MB`);
      set('sha', rel.sha256);
      if (rel.date) {
        const d = new Date(rel.date + 'T00:00:00Z');
        if (!isNaN(d)) set('date', d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }));
      }
    })
    .catch(() => { /* keep the built-in defaults */ });

  const copy = document.getElementById('copy-sha');
  const sha = document.getElementById('sha');
  if (copy && sha) {
    copy.setAttribute('aria-live', 'polite');
    copy.addEventListener('click', async () => {
      const text = sha.textContent.trim();
      try {
        await navigator.clipboard.writeText(text);
      } catch (e) {
        const r = document.createRange(); r.selectNodeContents(sha);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      }
      copy.textContent = 'Copied';
      setTimeout(() => { copy.textContent = 'Copy'; }, 2000);
    });
  }
})();
