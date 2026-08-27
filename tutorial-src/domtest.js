/* Behavioural test for the built tutorial.
 *
 * Loads ../index.html in jsdom and drives it the way a reader would: opening the menu,
 * searching, ticking sections read, folding lectures, asking a question, answering quizzes.
 * check.py validates the source; this validates the thing that actually ships.
 *
 *   cd <a scratch dir> && npm install jsdom
 *   node /path/to/tutorial-src/domtest.js
 *
 * jsdom refuses localStorage on a file:// origin, so the page is served a fake http:// URL.
 */
const fs = require('fs');
const path = require('path');
// jsdom is a dev dependency installed wherever you ran `npm install jsdom`, which is usually
// not next to this file, so fall back to resolving it from the working directory.
let JSDOM;
try {
  ({ JSDOM } = require('jsdom'));
} catch (e) {
  try {
    const { createRequire } = require('module');
    ({ JSDOM } = createRequire(path.join(process.cwd(), 'noop.js'))('jsdom'));
  } catch (e2) {
    console.error('jsdom not found. Install it and run this from that directory:\n' +
                  '  cd <scratch dir> && npm install jsdom && node ' + __filename);
    process.exit(2);
  }
}

const file = path.join(__dirname, '..', 'index.html');
let fails = 0;
const check = (name, cond, extra) => {
  console.log((cond ? 'PASS  ' : 'FAIL  ') + name + (cond ? '' : '   <-- ' + (extra || '')));
  if (!cond) fails++;
};

const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost/index.html',
});
const { window } = dom, doc = window.document;
const click = el => el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
window.addEventListener('error', e => { console.log('JS ERROR: ' + e.message); fails++; });

setTimeout(() => {
  const schools = doc.querySelectorAll('#toc .toc-school');
  const groups = doc.querySelectorAll('#toc .toc-group');
  const secs = doc.querySelectorAll('#toc .toc-sec');
  const pageSecs = doc.querySelectorAll('section.lecture');

  // Both counts come from the page rather than from a constant, so adding or removing a
  // school does not turn this into a failing test that is really only out of date. With a
  // single school the menu drops the school level entirely and the groups become the top
  // level, so the expected school count is 0 in that case and the groups move up to #toc.
  const pageSchools = new Set([...pageSecs].map(s => s.getAttribute('data-school')));
  const pageGroups = new Set([...pageSecs].map(s => s.getAttribute('data-day')));
  const oneSchool = pageSchools.size < 2;
  check('school level appears only when there is more than one school',
        schools.length === (oneSchool ? 0 : pageSchools.size),
        schools.length + ' school node(s) for ' + pageSchools.size + ' school(s)');
  check('menu has one node per group', groups.length === pageGroups.size,
        groups.length + ' menu vs ' + pageGroups.size + ' on the page');
  if (oneSchool) {
    check('groups sit at the top level of the menu',
          doc.querySelectorAll('#toc > .toc-group').length === pageGroups.size,
          doc.querySelectorAll('#toc > .toc-group').length + ' top-level group(s)');
  }
  check('one menu entry per section', secs.length === pageSecs.length,
        secs.length + ' menu vs ' + pageSecs.length + ' page');
  check('subsections are in the menu',
        doc.querySelectorAll('#toc .toc-sub a.toc-h3').length > 200);
  check('school labels resolved',
        [...schools].every(s => {
          const t = s.querySelector('.toc-school-hd span:nth-child(2)').textContent;
          return t && t !== 'other';
        }));
  check('every section is reachable in the menu',
        [...groups].reduce((n, g) => n + g.querySelectorAll('.toc-sec').length, 0)
        === pageSecs.length);
  check('no unmapped group keys',
        ![...groups].some(g => /^mk-|^\d+$/.test(
          g.querySelector('.toc-group-hd span:nth-child(2)').textContent)));

  // build.py numbers sections from file order; both the attribute and the badge must agree
  const bySchool = {};
  [...pageSecs].forEach(s => {
    (bySchool[s.getAttribute('data-school')] ||= []).push(+s.getAttribute('data-num'));
  });
  check('display numbers are sequential per school',
        Object.values(bySchool).every(ns => ns.every((n, i) => n === i + 1)),
        JSON.stringify(bySchool));
  check('lec-num badge matches data-num',
        [...pageSecs].every(s =>
          s.querySelector('.lec-num').textContent.trim() === s.getAttribute('data-num')));
  check('every section has a lecturer and a title',
        [...pageSecs].every(s => s.getAttribute('data-lecturer') && s.getAttribute('data-title')));

  // ---- collapse ----
  const sec0 = secs[0];
  check('subsections start folded', sec0.classList.contains('collapsed'));
  click(sec0.querySelector('.tw-btn'));
  check('twisty unfolds a section', !sec0.classList.contains('collapsed'));
  click(sec0.querySelector('.tw-btn'));
  check('twisty folds it back', sec0.classList.contains('collapsed'));
  // Every level starts folded, so the menu opens as a short list of schools. The scrollspy
  // then reveals the path to wherever the reader is, and jsdom reports every element at
  // offset 0, so it believes the last section is on screen and opens exactly one chain.
  // In a real browser at scroll top nothing is current, so nothing opens. Allow that chain.
  const folded = els => [...els].filter(e => e.classList.contains('collapsed')).length;
  check('schools start folded', folded(schools) >= schools.length - 1,
        folded(schools) + '/' + schools.length);
  check('groups start folded', folded(groups) >= groups.length - 1,
        folded(groups) + '/' + groups.length);
  check('the top level of the menu is a short list',
        (schools.length || groups.length) <= 12,
        (schools.length || groups.length) + ' top-level node(s)');
  check('scrollspy reveals the path to the current section',
        [...doc.querySelectorAll('#toc .toc-sec-row.has-active')].length <= 1);

  // The menu used to rearrange itself under your finger. html has scroll-behavior:smooth, so
  // clicking an entry animates the page over every section in between, the scrollspy fired on
  // each frame, and each section it passed had its menu path opened. One click could expand a
  // dozen groups and leave the sidebar showing somewhere else entirely.
  const openGroups = () =>
    [...doc.querySelectorAll('#toc .toc-group')].filter(g => !g.classList.contains('collapsed')).length;
  const openSecs = () =>
    [...doc.querySelectorAll('#toc .toc-sec')].filter(g => !g.classList.contains('collapsed')).length;
  const topGroups = [...doc.querySelectorAll('#toc > .toc-group, #toc > .toc-school')];
  click(topGroups[topGroups.length - 1].querySelector('a.toc-h2'));
  const openedByClick = openGroups();
  for (let i = 0; i < 40; i++) window.dispatchEvent(new window.Event('scroll'));
  check('clicking a menu entry opens only its own branch', openedByClick <= 2,
        openedByClick + ' groups open');
  check('the scroll it starts does not keep expanding the menu', openGroups() <= openedByClick,
        openedByClick + ' -> ' + openGroups());

  // Reading straight through should not end with the whole tree expanded: the spy folds the
  // section you left behind, unless you opened it yourself.
  const heads = [...doc.querySelectorAll('section.lecture h2[id], section.lecture h3[id]')];
  const savedRects = heads.map(h => h.getBoundingClientRect);
  let fakePos = 0;
  heads.forEach((h, i) => {
    const y = i * 300;
    h.getBoundingClientRect = () => ({ top: y - fakePos, bottom: y - fakePos + 40,
                                       left: 0, right: 0, width: 0, height: 40 });
  });
  for (fakePos = 0; fakePos < heads.length * 300; fakePos += 300) {
    window.dispatchEvent(new window.Event('scroll'));
  }
  check('reading through does not leave every group open', openGroups() <= 2,
        openGroups() + ' of ' + doc.querySelectorAll('#toc .toc-group').length + ' still open');
  check('reading through does not leave every section open', openSecs() <= 2,
        openSecs() + ' of ' + doc.querySelectorAll('#toc .toc-sec').length + ' still open');
  heads.forEach((h, i) => { h.getBoundingClientRect = savedRects[i]; });

  const toggles = (box, head, label) => {
    const before = box.classList.contains('collapsed');
    click(head);
    check(label + ' toggles', box.classList.contains('collapsed') !== before);
    click(head);
    check(label + ' toggles back', box.classList.contains('collapsed') === before);
  };
  if (schools.length) {
    toggles(schools[0], schools[0].querySelector('.toc-school-hd'), 'school header');
  }
  toggles(groups[0], groups[0].querySelector('.toc-group-hd'), 'group header');
  click(groups[0].querySelector('.toc-group-hd'));
  check('collapse state persisted', !!window.localStorage.getItem('tut-collapsed'));
  click(groups[0].querySelector('.toc-group-hd'));

  // ---- search ----
  const input = doc.getElementById('toc-search');
  const type = v => { input.value = v; input.dispatchEvent(new window.Event('input', { bubbles: true })); };
  const shown = () => [...doc.querySelectorAll('#toc .toc-sec')].filter(s => !s.classList.contains('hidden'));
  type('separation logic');
  check('search narrows to matches', shown().length >= 1 && shown().length <= 5, 'got ' + shown().length);
  type('superposition');
  check('search reaches sections late in the running order', shown().length >= 1);
  check('a hit is highlighted', doc.querySelectorAll('#toc .toc-hit').length > 0);
  type('zzzznothingmatches');
  check('empty-state message shows', !doc.getElementById('toc-empty').classList.contains('hidden'));
  check('a branch with nothing matching is hidden',
        [...(schools.length ? schools : groups)].every(n => n.classList.contains('hidden')));
  type('');
  check('clearing search restores every section', shown().length === secs.length);

  // ---- read flags ----
  const firstRow = doc.querySelector('#toc .toc-sec-row');
  click(firstRow.querySelector('.toc-check'));
  check('menu tick marks a section read', firstRow.classList.contains('read'));
  check('read state saved', (window.localStorage.getItem('tut-read') || '').includes('sec-'));
  check('progress counter moved', doc.getElementById('read-progress-num').textContent === '1');
  check('in-page button reflects it',
        /Marked as read/.test(doc.querySelector('section.lecture .lec-read-btn').textContent));

  // ---- folding a lecture ----
  const lec = doc.querySelector('section.lecture');
  const foldBtn = lec.querySelector('.lec-collapse');
  check('every lecture has a fold button',
        doc.querySelectorAll('section.lecture .lec-collapse').length === pageSecs.length);
  click(foldBtn);
  check('lecture folds', lec.classList.contains('collapsed'));
  click(foldBtn);
  check('lecture unfolds', !lec.classList.contains('collapsed'));

  // ---- ask Claude ----
  const panel = doc.getElementById('ask-panel');
  check('ask panel starts hidden', panel.classList.contains('hidden'));
  click(doc.getElementById('ask-fab'));
  check('ask panel opens', !panel.classList.contains('hidden'));
  doc.getElementById('ask-text').value = 'Why does the loop invariant need ghost variables?';
  click(doc.getElementById('ask-save'));
  check('question saved', JSON.parse(window.localStorage.getItem('tut-questions') || '[]').length === 1);
  check('saved question shows', doc.querySelectorAll('.ask-q').length === 1);
  click(doc.querySelector('.ask-q button'));
  check('question can be removed',
        JSON.parse(window.localStorage.getItem('tut-questions') || '[]').length === 0);

  // ---- widgets ----
  check('quizzes rendered', doc.querySelectorAll('.quiz .quiz-opts').length > 0);
  check('steppers rendered', doc.querySelectorAll('.stepper-head').length > 0);
  check('tabs rendered', doc.querySelectorAll('.tab-bar').length > 0);
  // ---- small screens ----
  // The drawer and the overflow guards are behaviour, not styling, so they are testable here.
  // The breakpoint itself is CSS and jsdom does not lay out, so what is checked is the state
  // machine: the drawer opens, closes by each of its four routes, and keeps aria in step.
  const side = doc.getElementById('sidebar');
  const menuBtn = doc.getElementById('menu-btn');
  const backdrop = doc.getElementById('menu-backdrop');
  check('menu drawer is wired up', !!side && !!menuBtn && !!backdrop);
  check('drawer starts closed', !side.classList.contains('open'));
  click(menuBtn);
  check('the menu button opens the drawer',
        side.classList.contains('open') && backdrop.classList.contains('on')
        && doc.body.classList.contains('menu-open'));
  check('aria-expanded follows the drawer', menuBtn.getAttribute('aria-expanded') === 'true');
  click(menuBtn);
  check('the menu button closes it again',
        !side.classList.contains('open') && !doc.body.classList.contains('menu-open'));
  click(menuBtn); click(backdrop);
  check('the backdrop closes it', !side.classList.contains('open'));
  click(menuBtn);
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  check('escape closes it', !side.classList.contains('open'));
  click(menuBtn); click(doc.querySelector('#toc a[href^="#"]'));
  check('following a menu link closes it', !side.classList.contains('open'));

  // One unwrapped table is enough to make the whole page scroll sideways on a phone.
  const tables = doc.querySelectorAll('table');
  const unwrapped = [...tables].filter(t => !t.closest('.table-wrap'));
  check('every table sits in a scrolling box', unwrapped.length === 0,
        unwrapped.length + ' of ' + tables.length + ' unwrapped');

  // Diagrams drawn wider than a phone are marked so the CSS can scroll them at a legible size.
  const svgFigs = [...doc.querySelectorAll('.fig>svg')];
  const shouldBeWide = svgFigs.filter(sv => {
    const vb = (sv.getAttribute('viewBox') || '').split(/[\s,]+/);
    return vb.length === 4 && parseFloat(vb[2]) >= 520;
  });
  check('wide diagrams are marked for scrolling',
        shouldBeWide.length > 0
        && shouldBeWide.every(sv => sv.parentNode.classList.contains('fig-wide')),
        shouldBeWide.length + ' of ' + svgFigs.length + ' figures are wide');

  check('figures rendered', doc.querySelectorAll('.fig').length > 0);
  // Every figure here is inline SVG, so there may be no raster image to zoom at all. What has
  // to hold is that any image inside a figure did get wired to the lightbox.
  check('every figure image is zoomable',
        [...doc.querySelectorAll('.fig img')].every(im => im.classList.contains('zoomable')),
        doc.querySelectorAll('.fig img').length + ' figure image(s)');
  check('no quiz payload failed to load',
        ![...doc.querySelectorAll('.quiz-nudge')].some(n => /failed to load/.test(n.textContent)));
  check('slide bank present', !!doc.getElementById('slide-bank'));
  check('slide pills are buttons', doc.querySelectorAll('button.slide-ref[data-slide]').length > 0);

  // every pill must resolve to an image in the bank, or it opens nothing
  let bank = {};
  try { bank = JSON.parse(doc.getElementById('slide-bank').textContent) || {}; } catch (e) {}
  const dangling = [...doc.querySelectorAll('button.slide-ref[data-slide]')]
    .map(b => b.getAttribute('data-slide')).filter(k => !bank[k]);
  check('every clickable pill has a slide in the bank', dangling.length === 0,
        dangling.slice(0, 5).join(', '));

  // ---- the slide viewer ----
  // A slide is landscape and full of small text. Fitted to a phone it is unreadable, so the
  // viewer has a fit state and an enlarged state, and a tap on the picture must not dismiss
  // the thing the reader is trying to look at.
  const pill = doc.querySelector('button.slide-ref[data-slide]');
  click(pill);
  const lb = doc.querySelector('.lightbox');
  check('a slide pill opens the viewer', lb && !lb.classList.contains('hidden'));
  check('it opens fitted, not enlarged', !lb.classList.contains('zoomed'));
  const zoomBtn = [...lb.querySelectorAll('.lb-btn')].find(b => /enlarge|fit/i.test(b.textContent));
  click(zoomBtn);
  check('the enlarge control zooms it', lb.classList.contains('zoomed'));
  check('and relabels itself', /fit/i.test(zoomBtn.textContent), zoomBtn.textContent);
  click(zoomBtn);
  check('and fits it again', !lb.classList.contains('zoomed'));
  click(lb.querySelector('img'));
  check('tapping the slide itself does not close it', !lb.classList.contains('hidden'));
  click(lb);
  check('tapping the backdrop closes it', lb.classList.contains('hidden'));
  click(pill);
  click([...lb.querySelectorAll('.lb-btn')].find(b => b.textContent.trim() === '\u2715'));
  check('the close control closes it', lb.classList.contains('hidden'));

  // a quiz that never accepts its own answer is worse than no quiz
  const quizzes = [...doc.querySelectorAll('.quiz')].map(box => {
    const s = box.querySelector('script[type="application/json"]');
    try { return { box, d: JSON.parse(s.textContent) }; } catch (e) { return null; }
  }).filter(Boolean);

  let mcOk = 0, mcTotal = 0, fillOk = 0, fillTotal = 0;
  for (const { box, d } of quizzes) {
    if (d.type === 'mc') {
      mcTotal++;
      const opts = box.querySelectorAll('.quiz-opts button');
      if (!opts[d.answer]) continue;
      click(opts[d.answer]);
      if (opts[d.answer].classList.contains('correct')) mcOk++;
    } else if (d.type === 'fill') {
      fillTotal++;
      const want = (d.accept || d.answers || [])[0];
      const inp = box.querySelector('.quiz-fill input');
      const btn = [...box.querySelectorAll('button')].find(b => b.textContent.trim() === 'Check');
      if (!want || !inp || !btn) continue;
      inp.value = want;
      click(btn);
      if (inp.classList.contains('ok')) fillOk++;
    }
  }
  check('multiple-choice quizzes exist', mcTotal > 50, 'got ' + mcTotal);
  check('every mc quiz accepts its own answer', mcOk === mcTotal, mcOk + '/' + mcTotal);
  check('fill quizzes exist', fillTotal > 0, 'got ' + fillTotal);
  check('every fill quiz accepts its own answer', fillOk === fillTotal, fillOk + '/' + fillTotal);

  console.log('\n' + (fails ? fails + ' FAILURE(S)' : 'all checks passed'));
  process.exit(fails ? 1 : 0);
}, 6000);
