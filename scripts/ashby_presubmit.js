// Ashby pre-submit state check. Run AFTER filling text fields and BEFORE handing the tab to the candidate.
// Ashby keeps form state in React; values set through the native setter and yes/no buttons clicked with
// element.click() can look filled yet be missing from that state, and Submit then fails with
// "Missing entry for required field". This script (1) re-sets every filled text field through React's value
// tracker, (2) reports yes/no questions with no selection, (3) reports empty required fields, unset radio
// groups (including ones outside the field entries, e.g. relocation or EEO) and any form error banner.
// It never clicks Submit.
//
// Pass {reclick: true} via window.__presubmitOpts to also re-click the active Yes/No buttons with a full
// pointer sequence. Off by default: on some forms the re-click toggles the selection OFF. If you use it,
// zoom-screenshot every Yes/No afterwards and click once only where none is selected (dark, white text).
(() => {
  const opts = window.__presubmitOpts || {};
  const report = [];
  const typeInto = (el, v) => {
    el.focus();
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    // React's value tracker ignores a value equal to the last tracked one, so clear first
    setter.call(el, ''); el.dispatchEvent(new Event('input', { bubbles: true }));
    setter.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'a' }));
    el.blur(); el.dispatchEvent(new Event('blur', { bubbles: true }));
  };
  const realClick = el => {
    const r = el.getBoundingClientRect(); const o = { bubbles: true, cancelable: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, buttons: 1 };
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(t => el.dispatchEvent(t.startsWith('pointer') ? new PointerEvent(t, o) : new MouseEvent(t, o)));
  };
  document.querySelectorAll('.ashby-application-form-field-entry').forEach((f, i) => {
    const lab = (f.querySelector('label')?.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 60);
    const inp = f.querySelector('input:not([type=file]):not([type=radio]):not([type=checkbox]), textarea');
    if (inp && !f.querySelector('[role=combobox]')) {
      if (inp.value) { typeInto(inp, inp.value); report.push(`${i} retyped: ${lab}`); }
      else if (inp.required || /\*/.test(f.innerText.slice(0, 80))) report.push(`${i} EMPTY required: ${lab}`);
      return;
    }
    const yn = [...f.querySelectorAll('button')].filter(b => /^(Yes|No)$/.test(b.innerText.trim()));
    if (yn.length === 2) {
      const active = yn.find(b => /_active|active|selected/i.test(b.className) || b.getAttribute('aria-pressed') === 'true' || getComputedStyle(b).backgroundColor !== getComputedStyle(yn.find(x => x !== b)).backgroundColor && getComputedStyle(b).color === 'rgb(255, 255, 255)');
      if (!active) report.push(`${i} YN NOT SET: ${lab}`);
      else if (opts.reclick) { realClick(active); report.push(`${i} reclicked ${active.innerText.trim()} (verify by screenshot): ${lab}`); }
      else report.push(`${i} YN ${active.innerText.trim()}: ${lab}`);
      return;
    }
    const file = f.querySelector('input[type=file]');
    if (file) report.push(`${i} file: ${[...file.files].map(x => x.name).join(',') || 'NONE'} (${lab})`);
  });
  const groups = {};
  document.querySelectorAll('input[type=radio]').forEach(r => (groups[r.name] = groups[r.name] || []).push(r));
  Object.values(groups).forEach(g => { if (!g.some(r => r.checked)) { const q = g[0].closest('fieldset,div')?.querySelector('legend,label,[class*=label]')?.innerText?.trim().slice(0, 60); report.push(`radio NOT SET: ${q || g[0].name}`); } });
  const banner = document.querySelector('[class*=error], [role=alert]')?.innerText?.trim();
  if (banner) report.push('FORM ERROR BANNER: ' + banner.replace(/\s+/g, ' ').slice(0, 200));
  return report.join('\n');
})()
