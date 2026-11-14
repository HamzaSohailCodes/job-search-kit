/**
 * Tracker styling + Dashboard for the job-search-kit Google Sheet.
 *
 * Install: open the tracker sheet > Extensions > Apps Script, paste this file, save, run styleTracker()
 * once (it asks for permission to edit this spreadsheet only). Re-run it any time; it rebuilds the
 * Dashboard tab and replaces only its own formatting rules. It never changes cell values except
 * filling the P1..R1 headers when they are empty.
 *
 * One tab holds every role: full-time, part-time and contract rows sit side by side, told apart by
 * column L (Employment Type). There is no separate contract tab. Columns A..AC are documented in
 * scripts/tracker_header.md (S..AC are the contract / outreach columns).
 * Bound to the active spreadsheet, so no sheet ID lives here. Keep the settings below in step with
 * config/profile.json.
 */
const TAB_GID = 0;          // tracker.gid: the table tab (the scripts always address this tab)
const FOLLOW_UP_DAYS = 10;  // followups.quiet_days
const H1B_MODULE = false;   // modules.h1b: colour rows by column Q (H-1B Evidence)
const STATUSES = ['Shortlisted', 'Applied', 'Interviewing', 'Offer', 'Rejected', 'Skipped', 'Blocked', 'Pending Review', 'Closed'];
const REASONS = ['sponsorship', 'location', 'stack', 'domain', 'seniority', 'clearance', 'closed', 'pay', 'other', 'unknown'];
// Column L labels (core/config.py EMPLOYMENT_TYPES) and their optional colours [background, text]
const EMPLOYMENT_TYPES = ['Full-time', 'Part-time', 'Contract (W2)', 'Contract (C2C)', 'Contract (1099)', 'Not stated'];
const COLOR_EMPLOYMENT_TYPE = true;  // false: leave column L uncoloured
const TYPE_COLORS = {
  'Full-time': ['#e0e7ff', '#3730a3'],
  'Part-time': ['#fce7f3', '#9d174d'],
  'Contract (W2)': ['#ccfbf1', '#115e59'],
  'Contract (C2C)': ['#fef9c3', '#854d0e'],
  'Contract (1099)': ['#ffe4e6', '#9f1239'],
  'Not stated': ['#f3f4f6', '#6b7280']
};
// Outreach stage words at the start of column O on contract rows
const OUTREACH_STAGES = ['Not contacted', 'Emailed', 'Connected', 'Replied', 'Screen call', 'Submitted (RTR)', 'Client interview'];
const LAST_COL = 29;  // A..AC

function styleTracker() {
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheets().find(s => s.getSheetId() === TAB_GID);
  const lastCol = LAST_COL;
  const lastRow = Math.max(sh.getLastRow(), 2);
  const NAVY = '#1f3a5f';

  // Base font and alignment
  sh.getRange(1, 1, sh.getMaxRows(), lastCol)
    .setFontFamily('Inter').setFontSize(10).setVerticalAlignment('middle');

  // Header
  sh.getRange(1, 1, 1, lastCol)
    .setBackground(NAVY).setFontColor('#ffffff').setFontWeight('bold')
    .setWrap(true).setHorizontalAlignment('center');
  sh.setRowHeight(1, 36);
  sh.setFrozenRows(1);
  sh.setFrozenColumns(2);

  // Alternating rows
  sh.getBandings().forEach(b => b.remove());
  const band = sh.getRange(2, 1, lastRow - 1, lastCol)
    .applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY, false, false);
  band.setFirstRowColor('#ffffff').setSecondRowColor('#f5f7fa');

  // Column widths and clipping for long text
  const widths = {1: 280, 2: 150, 3: 190, 4: 160, 5: 130, 6: 115, 7: 100, 8: 110,
                  9: 320, 10: 70, 11: 140, 12: 120, 13: 240, 14: 160, 15: 320, 16: 110, 17: 260,
                  18: 90, 19: 220, 20: 70, 21: 200, 22: 200, 23: 140, 24: 220, 25: 260, 26: 220,
                  27: 105, 28: 105, 29: 105};
  Object.keys(widths).forEach(c => sh.setColumnWidth(+c, widths[c]));
  sh.getRange(2, 1, lastRow - 1, lastCol).setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP);
  sh.getRange(2, 6, lastRow - 1, 2).setHorizontalAlignment('center');
  sh.getRange(2, 10, lastRow - 1, 1).setHorizontalAlignment('center').setFontWeight('bold');
  sh.getRange(2, 2, lastRow - 1, 1).setFontWeight('bold');
  sh.getRange(2, 12, lastRow - 1, 1).setHorizontalAlignment('center');
  sh.getRange(2, 18, lastRow - 1, 1).setHorizontalAlignment('center');
  sh.getRange(2, 20, lastRow - 1, 1).setHorizontalAlignment('center').setFontWeight('bold');
  sh.getRange(2, 27, sh.getMaxRows() - 1, 3).setNumberFormat('yyyy-mm-dd').setHorizontalAlignment('center');
  // contract / outreach block (S..AC) gets a slightly different header so it reads as its own group
  sh.getRange(1, 19, 1, LAST_COL - 18).setBackground('#334e68');

  // Status dropdown (warn only, never blocks typing)
  sh.getRange(2, 6, sh.getMaxRows() - 1, 1).setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInList(STATUSES, true).setAllowInvalid(true).build());

  // Reason tag dropdown (column P)
  if (!sh.getRange('P1').getValue()) sh.getRange('P1').setValue('Reason Tag');
  sh.getRange(2, 16, sh.getMaxRows() - 1, 1).setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInList(REASONS, true).setAllowInvalid(true).build());
  if (!sh.getRange('Q1').getValue()) sh.getRange('Q1').setValue('H-1B Evidence');
  if (!sh.getRange('R1').getValue()) sh.getRange('R1').setValue('Reached Interview');
  const dv = list => SpreadsheetApp.newDataValidation().requireValueInList(list, true).setAllowInvalid(true).build();
  sh.getRange(2, 12, sh.getMaxRows() - 1, 1).setDataValidation(dv(EMPLOYMENT_TYPES));  // L
  sh.getRange(2, 18, sh.getMaxRows() - 1, 1).setDataValidation(dv(['Yes', 'No']));       // R
  sh.getRange(2, 20, sh.getMaxRows() - 1, 1).setDataValidation(dv(['A', 'B', 'C']));     // T Priority

  // Status colors (replace earlier rules on column F, keep everything else)
  const fRange = sh.getRange(2, 6, sh.getMaxRows() - 1, 1);
  const colors = {
    'Shortlisted': ['#eef1f5', '#4a5568'],
    'Applied': ['#dbeafe', '#1e40af'],
    'Interviewing': ['#d1fae5', '#065f46'],
    'Offer': ['#bbf7d0', '#14532d'],
    'Rejected': ['#fee2e2', '#991b1b'],
    'Skipped': ['#fef3c7', '#92400e'],
    'Blocked': ['#ffedd5', '#9a3412'],
    'Pending Review': ['#ede9fe', '#5b21b6'],
    'Closed': ['#f3f4f6', '#6b7280']
  };
  // drop the rules this script made last time (status F, type L, Q, AB/AC, row tint); keep anyone else's
  const ours = g => (g.getNumColumns() === 1 && [6, 12, 17, 28, 29].indexOf(g.getColumn()) >= 0) ||
    (g.getColumn() === 1 && g.getNumColumns() === 5) || (g.getColumn() === 7 && g.getNumColumns() === 9);
  let rules = sh.getConditionalFormatRules().filter(r => !r.getRanges().some(ours));
  Object.keys(colors).forEach(s => rules.push(SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo(s).setBackground(colors[s][0]).setFontColor(colors[s][1]).setBold(true)
    .setRanges([fRange]).build()));
  // Whole row tint for interviewing rows
  rules.push(SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$F2="Interviewing"').setBackground('#ecfdf5')
    .setRanges([sh.getRange(2, 1, sh.getMaxRows() - 1, 5), sh.getRange(2, 7, sh.getMaxRows() - 1, 9)]).build());
  if (H1B_MODULE) {
    // Column Q starts with "sponsors" (green) or "some" (light green), as written by the h1b module
    const qRange = sh.getRange(2, 17, sh.getMaxRows() - 1, 1);
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenTextStartsWith('sponsors')
      .setBackground('#bbf7d0').setFontColor('#14532d').setRanges([qRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenTextStartsWith('some')
      .setBackground('#ecfdf5').setFontColor('#065f46').setRanges([qRange]).build());
  }
  if (COLOR_EMPLOYMENT_TYPE) {
    const lRange = sh.getRange(2, 12, sh.getMaxRows() - 1, 1);
    Object.keys(TYPE_COLORS).forEach(t => rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(t).setBackground(TYPE_COLORS[t][0]).setFontColor(TYPE_COLORS[t][1])
      .setRanges([lRange]).build()));
  }
  // Contract follow-up dates (AB, AC) turn red when due and the row is still at Emailed / Connected
  [['AB', 28], ['AC', 29]].forEach(([col, c]) => {
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=AND(' + col + '2<>"",' + col + '2<=TODAY(),REGEXMATCH($O2,"^(Emailed|Connected)"))')
      .setBackground('#fee2e2').setFontColor('#991b1b').setBold(true)
      .setRanges([sh.getRange(2, c, sh.getMaxRows() - 1, 1)]).build());
  });
  sh.setConditionalFormatRules(rules);

  buildDashboard(ss, sh.getName());
}

function buildDashboard(ss, src) {
  let d = ss.getSheetByName('Dashboard');
  if (d) ss.deleteSheet(d);
  d = ss.insertSheet('Dashboard', 0);
  d.setHiddenGridlines(true);
  d.getRange('A1:Z200').setFontFamily('Inter').setVerticalAlignment('middle');
  d.setColumnWidth(1, 24);
  for (let c = 2; c <= 17; c++) d.setColumnWidth(c, 78);
  const F = `'${src}'!F2:F`;

  d.getRange('B2').setValue('Job Search Dashboard').setFontSize(20).setFontWeight('bold').setFontColor('#1f3a5f');
  d.getRange('B3').setFormula('="Updated "&TEXT(NOW(),"mmm d, yyyy h:mm AM/PM")').setFontColor('#6b7280');
  d.setRowHeight(2, 38);

  const cards = [
    ['Interviewing', `=COUNTIF(${F},"Interviewing")`, '#065f46', '#d1fae5'],
    ['Applied', `=COUNTIF(${F},"Applied")`, '#1e40af', '#dbeafe'],
    ['Shortlisted', `=COUNTIF(${F},"Shortlisted")`, '#4a5568', '#eef1f5'],
    ['Rejected', `=COUNTIF(${F},"Rejected")`, '#991b1b', '#fee2e2'],
    ['Skipped', `=COUNTIF(${F},"Skipped")`, '#92400e', '#fef3c7'],
    ['Response rate', `=IFERROR(COUNTIF(${F},"Interviewing")/(COUNTIF(${F},"Applied")+COUNTIF(${F},"Interviewing")+COUNTIF(${F},"Rejected")+COUNTIF(${F},"Offer")),0)`, '#5b21b6', '#ede9fe'],
    ['Applied today', `=COUNTIFS(${F},"Applied",'${src}'!G2:G,TODAY())`, '#0e7490', '#cffafe'],
    ['Total tracked', `=COUNTA('${src}'!B2:B)`, '#1f3a5f', '#e5e7eb']
  ];
  // 8 cards, 2 columns wide each, rows 5-7
  cards.forEach((c, i) => {
    const col = 2 + i * 2;
    const box = d.getRange(5, col, 3, 2);
    box.setBackground(c[3]).setBorder(true, true, true, true, false, false, c[2], SpreadsheetApp.BorderStyle.SOLID_THICK);
    d.getRange(5, col, 1, 2).merge().setValue(c[0].toUpperCase()).setFontSize(9).setFontWeight('bold')
      .setFontColor(c[2]).setHorizontalAlignment('center');
    const v = d.getRange(6, col, 2, 2).merge().setFormula(c[1]).setFontSize(24).setFontWeight('bold')
      .setFontColor(c[2]).setHorizontalAlignment('center');
    if (c[0] === 'Response rate') v.setNumberFormat('0%');
  });
  d.setRowHeight(5, 24); d.setRowHeight(6, 30); d.setRowHeight(7, 30);

  // By employment type (column L): one row per type, counts per status, to the right of the cards
  const L = `'${src}'!L2:L`;
  d.getRange('S4').setValue('By employment type').setFontSize(13).setFontWeight('bold').setFontColor('#1f3a5f');
  const tcols = ['Type', 'Total', 'Applied', 'Interviewing', 'Offer', 'Rejected'];
  d.getRange(5, 19, 1, tcols.length).setValues([tcols]).setBackground('#1f3a5f').setFontColor('#ffffff').setFontWeight('bold');
  EMPLOYMENT_TYPES.forEach((t, i) => {
    const r = 6 + i;
    d.getRange(r, 19).setValue(t);
    // 'Not stated' also counts rows with a blank L, so older rows still show up
    const typeCond = t === 'Not stated' ? `(((${L}="Not stated")+(${L}=""))*(${F}<>""))` : `(${L}="${t}")`;
    d.getRange(r, 20).setFormula(`=SUMPRODUCT(${typeCond})`);
    ['Applied', 'Interviewing', 'Offer', 'Rejected'].forEach((s, j) =>
      d.getRange(r, 21 + j).setFormula(`=SUMPRODUCT(${typeCond}*(${F}="${s}"))`));
    if (COLOR_EMPLOYMENT_TYPE && TYPE_COLORS[t]) d.getRange(r, 19).setBackground(TYPE_COLORS[t][0]).setFontColor(TYPE_COLORS[t][1]);
  });
  d.getRange(6, 19, EMPLOYMENT_TYPES.length, tcols.length).setBorder(true, true, true, true, true, true, '#e5e7eb', SpreadsheetApp.BorderStyle.SOLID);
  d.setColumnWidth(18, 24);
  d.setColumnWidth(19, 130);
  for (let c = 20; c <= 24; c++) d.setColumnWidth(c, 90);
  // Contract outreach: contract rows at each stage word at the start of O
  const cr = 6 + EMPLOYMENT_TYPES.length + 2;
  const O = `'${src}'!O2:O`, AB = `'${src}'!AB2:AB`;
  d.getRange(cr, 19).setValue('Contract outreach stage').setFontSize(13).setFontWeight('bold').setFontColor('#854d0e');
  d.getRange(cr + 1, 19, 1, 2).setValues([['Stage', 'Rows']]).setBackground('#854d0e').setFontColor('#ffffff').setFontWeight('bold');
  OUTREACH_STAGES.forEach((st, i) => {
    d.getRange(cr + 2 + i, 19).setValue(st);
    d.getRange(cr + 2 + i, 20).setFormula(`=SUMPRODUCT(REGEXMATCH(${L},"^Contract")*(LEFT(${O},${st.length})="${st}"))`);
  });
  const fr = cr + 2 + OUTREACH_STAGES.length;
  d.getRange(fr, 19).setValue('Follow-up 1 due').setFontWeight('bold');
  d.getRange(fr, 20).setFormula(
    `=SUMPRODUCT(ISNUMBER(${AB})*(${AB}<=TODAY())*REGEXMATCH(${O},"^(Emailed|Connected)"))`).setFontWeight('bold');
  d.getRange(cr + 2, 19, OUTREACH_STAGES.length + 1, 2).setBorder(true, true, true, true, true, true, '#e5e7eb', SpreadsheetApp.BorderStyle.SOLID);

  // Interviewing list
  d.getRange('B10').setValue('Interviewing: next steps').setFontSize(13).setFontWeight('bold').setFontColor('#065f46');
  d.getRange('B11:Q11').setBackground('#065f46').setFontColor('#ffffff').setFontWeight('bold');
  d.getRange('B11:D11').merge().setValue('Company');
  d.getRange('E11:H11').merge().setValue('Role');
  d.getRange('I11:Q11').merge().setValue('Outcome / next step');
  d.getRange('B12').setFormula(`=IFERROR(FILTER('${src}'!B2:B,${F}="Interviewing"),"None yet")`);
  d.getRange('E12').setFormula(`=IFERROR(FILTER('${src}'!A2:A,${F}="Interviewing"),"")`);
  d.getRange('I12').setFormula(`=IFERROR(FILTER('${src}'!O2:O,${F}="Interviewing"),"")`);
  d.getRange('B12:B30').setFontWeight('bold');
  d.getRange('B12:Q30').setFontSize(10);
  d.getRange('B12:Q30').applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY, false, false)
    .setFirstRowColor('#ffffff').setSecondRowColor('#f0fdf4');

  // Status breakdown + chart
  d.getRange('B33').setValue('Pipeline by status').setFontSize(13).setFontWeight('bold').setFontColor('#1f3a5f');
  const st = STATUSES;
  d.getRange('B34:C34').setValues([['Status', 'Count']]).setBackground('#1f3a5f').setFontColor('#ffffff').setFontWeight('bold');
  st.forEach((s, i) => {
    d.getRange(35 + i, 2).setValue(s);
    d.getRange(35 + i, 3).setFormula(`=COUNTIF(${F},B${35 + i})`);
  });
  d.getRange(35, 2, st.length, 2).setBorder(true, true, true, true, true, true, '#e5e7eb', SpreadsheetApp.BorderStyle.SOLID);
  const chart = d.newChart().setChartType(Charts.ChartType.BAR)
    .addRange(d.getRange(34, 2, st.length + 1, 2))
    .setPosition(33, 5, 0, 0)
    .setOption('legend', {position: 'none'})
    .setOption('colors', ['#1f3a5f'])
    .setOption('width', 620).setOption('height', 300)
    .setOption('title', 'Applications by status')
    .build();
  d.insertChart(chart);

  // Rejections by reason (column P)
  d.getRange('B45').setValue('Rejections by reason').setFontSize(13).setFontWeight('bold').setFontColor('#991b1b');
  const rs = REASONS;
  d.getRange('B46:C46').setValues([['Reason', 'Count']]).setBackground('#991b1b').setFontColor('#ffffff').setFontWeight('bold');
  rs.forEach((s, i) => {
    d.getRange(47 + i, 2).setValue(s);
    d.getRange(47 + i, 3).setFormula(`=COUNTIFS(${F},"Rejected",'${src}'!P2:P,B${47 + i})`);
  });
  d.getRange(47, 2, rs.length, 2).setBorder(true, true, true, true, true, true, '#e5e7eb', SpreadsheetApp.BorderStyle.SOLID);
  const chart2 = d.newChart().setChartType(Charts.ChartType.BAR)
    .addRange(d.getRange(46, 2, rs.length + 1, 2))
    .setPosition(45, 5, 0, 0)
    .setOption('legend', {position: 'none'})
    .setOption('colors', ['#991b1b'])
    .setOption('width', 620).setOption('height', 320)
    .setOption('title', 'Why we were rejected')
    .build();
  d.insertChart(chart2);
  // Applied with no reply (oldest first): follow up after FOLLOW_UP_DAYS
  d.getRange('B60').setValue('Waiting on a reply (Applied, oldest first)').setFontSize(13).setFontWeight('bold').setFontColor('#1e40af');
  d.getRange('B61:Q61').setBackground('#1e40af').setFontColor('#ffffff').setFontWeight('bold');
  d.getRange('B61:D61').merge().setValue('Company');
  d.getRange('E61:H61').merge().setValue('Role');
  d.getRange('I61:J61').merge().setValue('Applied');
  d.getRange('K61:L61').merge().setValue('Days');
  d.getRange('M61:Q61').merge().setValue('Follow up');
  const A = `'${src}'!A2:A`, B = `'${src}'!B2:B`, G = `'${src}'!G2:G`;
  const cond = `(${F}="Applied")*(${G}<>"")`;
  d.getRange('B62').setFormula(`=IFERROR(SORT(FILTER(${B},${cond}),FILTER(DATEVALUE(${G}),${cond}),TRUE),"None")`);
  d.getRange('E62').setFormula(`=IFERROR(SORT(FILTER(${A},${cond}),FILTER(DATEVALUE(${G}),${cond}),TRUE),"")`);
  d.getRange('I62').setFormula(`=IFERROR(SORT(FILTER(DATEVALUE(${G}),${cond}),FILTER(DATEVALUE(${G}),${cond}),TRUE),"")`);
  d.getRange('K62').setFormula(`=ARRAYFORMULA(IF(I62:I200="","",TODAY()-I62:I200))`);
  d.getRange('M62').setFormula(`=ARRAYFORMULA(IF(I62:I200="","",IF(TODAY()-I62:I200>${FOLLOW_UP_DAYS},"Overdue: follow up now","Follow up "&TEXT(I62:I200+${FOLLOW_UP_DAYS},"mmm d"))))`);
  d.getRange('I62:I200').setNumberFormat('yyyy-mm-dd');
  d.getRange('B62:Q200').setFontSize(10);
  d.getRange('B62:B200').setFontWeight('bold');
  d.getRange('B62:Q200').applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY, false, false)
    .setFirstRowColor('#ffffff').setSecondRowColor('#eff6ff');
  // card: overdue follow-ups (under the title row; the 8 cards fill B..Q)
  d.getRange('L2:M3').merge().setFormula(`="Overdue follow-ups: "&COUNTIFS(${F},"Applied",${G},"<"&TEXT(TODAY()-${FOLLOW_UP_DAYS},"yyyy-mm-dd"),${G},"<>")`)
    .setFontWeight('bold').setFontColor('#991b1b').setBackground('#fee2e2').setHorizontalAlignment('center');
  d.setFrozenRows(0);
}
