// Run in an application tab after filling (before the candidate submits). Collects every question and its
// current answer, then puts a red SNAPSHOT button on the page; clicking it copies the JSON to the
// clipboard so Claude can save it with `pbpaste > applications/_forms/<company-slug>__<date>.json`.
// Set window.__snapMeta = {company, job_title, resume_uploaded, resume_sha256, resume_archive, salary,
// left_for_candidate: [...]} first. Fields are merged into the JSON as given.
(() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const labelOf = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return clean(l.innerText); }
    const wrap = el.closest('fieldset, .ashby-application-form-field-entry, .field, .application-question, [class*=question], [class*=Field], li, div');
    const l = wrap && (wrap.querySelector('legend, label, [class*=label], h3, h4'));
    return clean(l ? l.innerText : el.getAttribute('aria-label') || el.name || el.placeholder);
  };
  const seen = new Set(), answers = [];
  const push = (q, a) => { q = q.slice(0, 400); if (!q || seen.has(q)) return; seen.add(q); answers.push({ question: q, answer: a }); };
  document.querySelectorAll('input:not([type=hidden]):not([type=file]):not([type=radio]):not([type=checkbox]):not([type=submit]), textarea, select').forEach(el => {
    if (el.offsetParent === null) return;
    const v = el.tagName === 'SELECT' ? clean(el.selectedOptions[0]?.innerText) : el.value;
    push(labelOf(el), v || '');
  });
  // radio / checkbox groups
  const groups = {};
  document.querySelectorAll('input[type=radio], input[type=checkbox]').forEach(el => {
    const k = el.name || labelOf(el); (groups[k] = groups[k] || []).push(el);
  });
  Object.values(groups).forEach(g => {
    const q = clean((g[0].closest('fieldset')?.querySelector('legend') || g[0].closest('fieldset, [role=group], [class*=question], [class*=Field]')?.querySelector('label, legend, [class*=label]'))?.innerText) || labelOf(g[0]);
    const chosen = g.filter(e => e.checked).map(e => clean(e.closest('label')?.innerText || document.querySelector(`label[for="${CSS.escape(e.id)}"]`)?.innerText || e.value));
    push(q, chosen.join('; '));
  });
  // Ashby yes/no buttons and react-select style comboboxes
  document.querySelectorAll('.ashby-application-form-field-entry').forEach(f => {
    const yn = f.querySelector('button[class*=yesno][class*=_active], button[class*=active][class*=yesno]');
    if (yn) push(clean(f.querySelector('label')?.innerText), clean(yn.innerText));
  });
  document.querySelectorAll('[class*=select__single-value], [class*=singleValue]').forEach(el => {
    const wrap = el.closest('[class*=field], [class*=question], div.select, .select__container')?.parentElement;
    push(clean(wrap?.querySelector('label')?.innerText) || 'dropdown', clean(el.innerText));
  });
  const files = [...document.querySelectorAll('input[type=file]')].map(f => [...(f.files || [])].map(x => x.name).join(', ')).filter(Boolean);
  const meta = window.__snapMeta || {};
  const jd = clean(document.querySelector('[class*=description], [class*=job-post], #content, main')?.innerText).slice(0, 20000);
  window.__snap = JSON.stringify(Object.assign({
    captured_at: new Date().toISOString(), source: 'apply-batch form snapshot', form_url: location.origin + location.pathname,
    files_attached: files, answers,
    caveat: 'Captured after Claude filled the form and before the candidate submitted; edits made afterwards are not included.',
    page_text_excerpt: jd
  }, meta), null, 2);
  document.getElementById('__snapbtn')?.remove();
  const b = document.createElement('button'); b.id = '__snapbtn'; b.textContent = 'SNAPSHOT';
  Object.assign(b.style, { position: 'fixed', top: '120px', right: '20px', zIndex: 2147483647, background: 'red', color: '#fff', fontSize: '22px', padding: '14px' });
  b.onclick = async () => { await navigator.clipboard.writeText(window.__snap); b.textContent = 'COPIED'; setTimeout(() => b.remove(), 1500); };
  document.body.appendChild(b);
  return `${answers.length} answers, ${files.length} files, ${window.__snap.length} chars`;
})()
