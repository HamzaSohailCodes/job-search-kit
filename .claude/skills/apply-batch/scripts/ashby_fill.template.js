// Ashby form filler. Generated into profile/ashby_fill.js by make_fill_js.py from config/profile.json.
// Fills identity, links, start date, how-did-you-hear, location, education (GPA per education_summary.share_gpa),
// languages, certifications, references, portfolio, current salary per screening.current_salary_answer, and the
// yes/no screening questions the profile answers. Returns a report of every field:
//   SET / YN / kept = filled or already filled; LEAVE = never-ask-or-store field (SSN, date of birth, license number,
//   criminal history, bank details, attestations, SMS/marketing consent); ?? = needs the candidate or Claude by hand
//   (EEO dropdowns carry the profile's answer as a hint). Profile answers set to "ask" are never filled.
// Never sets the salary ask (it depends on each posting's range), never touches consents, never clicks Submit.
(() => {
  const V = __V__;
  const NEVER = __NEVER__;
  if (V.locReloc && /on-?site|hybrid|in[- ]office|in[- ]person/i.test(document.body.innerText)) V.loc = V.locReloc;
  const setVal = (el, v) => {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
    ['input', 'change', 'blur'].forEach(e => el.dispatchEvent(new Event(e, { bubbles: true })));
  };
  const textRules = [
    [/pronounc/i, 'pron'], [/pronoun/i, 'pronouns'], [/preferred (first )?name/i, 'first'], [/first name/i, 'first'],
    [/last name|surname/i, 'last'], [/^(full |legal )?(full )?name\*?$|^your name|legal full name|^legal name/i, 'name'],
    [/e-?mail/i, 'email'], [/phone|mobile/i, 'phone'], [/linked ?in/i, 'linkedin'], [/github/i, 'github'],
    [/portfolio|work samples?/i, 'portfolio'], [/writing sample/i, 'writing'],
    [/website|personal site/i, 'website'],
    [/earliest.*start|start date|notice period|when can you start|availability/i, 'start'],
    [/current (company|employer)|most recent (company|employer)/i, 'company'], [/current (job )?title|current role/i, 'title'],
    [/how did you (hear|find)|where did you (hear|find)|referral source/i, 'source'],
    [/^(how many )?(total )?years of (relevant |professional |software |engineering )?experience( do you have)?\??\*?$/i, 'yrs'],
    [/(city|location).*(reside|based|live|located)|where (are you|do you) (currently )?(located|live|based)|current location/i, 'loc'],
    [/(current|previous|most recent|prior) (base )?(salary|compensation|pay)|salary history/i, 'salaryNow'],
    [/\breferences?\b/i, 'references'], [/languages? (do you )?(speak|spoken|fluen)|what languages|language proficiency/i, 'languages'],
    [/certifications?/i, 'certs'], [/professional licen[cs]es?/i, 'licenses'],
    [/highest (level of )?(education|degree)|education level|degree (obtained|completed)/i, 'edu'],
    [/graduat(ion|ed|e) (date|year)|when did you graduate|expected graduation/i, 'grad'],
    [/time ?zone/i, 'tz'], [/how many days.*(office|on-?site)|days per week in (the )?office/i, 'hybridDays']
  ];
  const AREA = new Set(['start', 'source', 'references', 'languages', 'certs', 'licenses']);  // safe to put in a textarea
  const EEO = [
    [/military spouse|military dependent/i, 'military_spouse'], [/veteran/i, 'veteran'], [/hispanic|latin[oa]/i, 'hispanic_latino'],
    [/\brace\b|ethnicity/i, 'race'], [/gender identity|\bgender\b|\bsex\b/i, 'gender'], [/disabilit/i, 'disability'],
    [/sexual orientation/i, 'sexual_orientation'], [/transgender/i, 'transgender']
  ];
  const ynRules = __YN__;
  const report = [];
  document.querySelectorAll('.ashby-application-form-field-entry').forEach((f, i) => {
    const lab = (f.querySelector('label')?.innerText || f.innerText.split('\n')[0] || '').trim().replace(/\s+/g, ' ');
    const required = /\*\s*$/.test(lab) || !!f.querySelector('[required], [aria-required=true]');
    const ins = [...f.querySelectorAll('input:not([type=file]):not([type=checkbox]):not([type=radio]), textarea')];
    const yn = [...f.querySelectorAll('button[class*=yesno]')];
    if (f.querySelector('input[type=file]')) { report.push(`${i} FILE: ${lab.slice(0, 60)}`); return; }
    if (NEVER.test(lab)) { report.push(`${i} LEAVE (candidate only): ${lab.slice(0, 160)}`); return; }
    if (yn.length) {
      const r = ynRules.find(([re]) => re.test(lab));
      if (r) { yn.find(b => b.innerText.trim() === r[1])?.click(); report.push(`${i} YN ${r[1]}${r[2] ? ' (verify per company)' : ''}: ${lab.slice(0, 100)}`); }
      else report.push(`${i} ?? YN: ${lab.slice(0, 200)}`);
      return;
    }
    if (ins.length === 1 && !f.querySelector('[role=combobox]')) {
      const el = ins[0];
      if (el.value) { report.push(`${i} kept: ${lab.slice(0, 40)}`); return; }
      if (/\bgpa\b|grade point/i.test(lab)) {
        const g = required ? V.gpaReq : V.gpa;
        if (g) { setVal(el, g); report.push(`${i} SET gpa: ${lab.slice(0, 60)}`); }
        else report.push(`${i} ?? GPA (not shared per education_summary.share_gpa${required ? '; required' : ''}): ${lab.slice(0, 120)}`);
        return;
      }
      const r = textRules.find(([re]) => re.test(lab));
      if (r && V[r[1]] && (el.tagName !== 'TEXTAREA' || AREA.has(r[1]) || /how did/i.test(lab))) { setVal(el, V[r[1]]); report.push(`${i} SET ${r[1]}: ${lab.slice(0, 60)}`); }
      else report.push(`${i} ?? ${el.tagName === 'TEXTAREA' ? 'ESSAY' : 'TEXT'}: ${lab.slice(0, 250)}`);
      return;
    }
    const opts = [...f.querySelectorAll('label, [role=option]')].map(l => l.innerText.trim()).filter(Boolean).slice(1, 10);
    const e = EEO.find(([re]) => re.test(lab));
    let hint = e && V.eeo[e[1]] ? ` hint: ${V.eeo[e[1]]}` : '';
    if (e && e[1] === 'veteran' && V.veteranDetail) hint += ` (${V.veteranDetail})`;
    if (!e && /highest (level of )?(education|degree)|education level/i.test(lab) && V.edu) hint = ` hint: ${V.edu}`;
    report.push(`${i} ?? ${f.querySelector('[role=combobox]') ? 'COMBO' : f.querySelector('input[type=radio],input[type=checkbox]') ? 'CHOICE' : 'OTHER'}: ${lab.slice(0, 200)} {${opts.join(' / ').slice(0, 300)}}${hint}`);
  });
  return document.title.slice(0, 60) + '\n' + report.join('\n');
})()
