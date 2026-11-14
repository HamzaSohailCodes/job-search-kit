// Gmail search-results extractor. Run it in a Gmail search tab of the candidate's job-search inbox
// (inbox.gmail_address in config/profile.json). It clicks each conversation row, reads the message bodies
// (.a3s), goes back, and accumulates window.__mails = [{i, from, subj, date, body}]. Read-only: it never
// replies, labels, archives or deletes.
// It may outlive the tool call's timeout; poll `window.__mails.length` until it stops growing, then click
// the red COPY button it adds and save the clipboard, e.g. on macOS
//   LC_ALL=en_US.UTF-8 pbpaste > batches/<date>-email-review/mails_<date>.json
// (mails_*.json is gitignored: inbox exports never get committed).
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  window.__mails = window.__mails || [];
  const seen = new Set(window.__mails.map(m => m.subj + '|' + m.from));
  const rows = () => [...document.querySelectorAll('tr.zA')].filter(r => r.offsetParent);
  const n = rows().length;
  for (let i = 0; i < n; i++) {
    const r = rows()[i]; if (!r) break;
    const from = clean(r.querySelector('.yW')?.innerText), subj = clean(r.querySelector('.bog')?.innerText);
    const date = r.querySelector('td.xW span')?.title || clean(r.querySelector('td.xW')?.innerText);
    if (seen.has(subj + '|' + from)) continue;
    r.click(); await sleep(1800);
    const bodies = [...document.querySelectorAll('.a3s')].map(e => clean(e.innerText)).filter(Boolean);
    window.__mails.push({ i, from, subj, date, body: bodies.join(' || ').slice(0, 6000) });
    seen.add(subj + '|' + from);
    history.back(); await sleep(1500);
  }
  document.getElementById('__cp')?.remove();
  const b = document.createElement('button'); b.id = '__cp'; b.textContent = 'COPY ' + window.__mails.length;
  Object.assign(b.style, { position: 'fixed', top: '200px', left: '600px', zIndex: 2147483647, background: 'red', color: '#fff', fontSize: '28px', padding: '18px' });
  b.onclick = async () => { await navigator.clipboard.writeText(JSON.stringify(window.__mails, null, 1)); b.textContent = 'DONE'; };
  document.body.appendChild(b);
  return window.__mails.length;
})()
