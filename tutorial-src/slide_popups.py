#!/usr/bin/env python3
"""Turn every <span class="slide-ref">…</span> pill into a button that opens the slide it
cites, so a reader never has to guess what "slide 47" looks like.

Pills cite slides by the number printed on the slide, which is rarely the PDF page number
(beamer decks emit one PDF page per overlay). This script therefore:

  1. reads each deck's footer to map printed number -> PDF page, always taking the *last*
     page of a build so the popup shows the finished slide;
  2. parses each pill into its citations, tracking whether the numbers are printed slide
     numbers or raw PDF pages ("pages 20-25, slide 28" mixes both);
  3. renders the primary slide of each pill once into a shared bank (slidebank.html), so a
     slide cited by ten pills is stored a single time;
  4. rewrites the pills into buttons naming the bank key they open.

Requires pdftoppm + ImageMagick convert. Idempotent: it rewrites pills and the bank from
scratch, so it is safe to rerun after editing any section.

    python3 slide_popups.py            # rebuild bank + rewrite pills
    python3 slide_popups.py --report   # resolve and report only, render nothing
"""
import base64
import glob
import os
import re
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
MARKT = 'marktoberdorf/slides'

# deck key -> (pdf path relative to the repo root, numbering style)
#   'printed' : slides carry their own number; map it to the final PDF page of the build
#   'pdf'     : deck prints no usable number, so a citation already names the PDF page
#
# Only PDF decks can appear here. PowerPoint decks are converted first by pptx_to_pdf.py.
# A section whose deck is absent is simply left out of SECTION_DECKS below: its pills stay as
# plain labels instead of becoming buttons, which is the graceful outcome, so leaving a deck
# out is always safe. Filenames are case sensitive and the lecturers' capitalisation is not
# consistent, so every path here is checked before any rendering starts.
DECKS = {
    'filliatre1':  (f'{MARKT}/Filliatre/Filliatre-1.pdf', 'pdf'),
    'filliatre2':  (f'{MARKT}/Filliatre/Filliatre-2.pdf', 'pdf'),
    'filliatre3':  (f'{MARKT}/Filliatre/Filliatre-3.pdf', 'pdf'),
    'filliatre4':  (f'{MARKT}/Filliatre/Filliatre-4.pdf', 'pdf'),
    'ryu1':        (f'{MARKT}/Ryu/ryu 1.pdf', 'pdf'),
    'ryu2':        (f'{MARKT}/Ryu/ryu 2.pdf', 'pdf'),
    'ryu3':        (f'{MARKT}/Ryu/ryu 3.pdf', 'pdf'),
    'ryu4':        (f'{MARKT}/Ryu/ryu 4.pdf', 'pdf'),
    'dodds':       (f'{MARKT}/Dodds/Mike Dodds - Doing Proof - Marktoberdorf 2026.pdf', 'pdf'),
    # Blanchette's decks carry a constant "4" in the footer, not a slide counter, so there is
    # no printed number to map: these are 'pdf' and their sections cite PDF page numbers.
    'blanchette1': (f'{MARKT}/Blanchette/mod2026-01-resolution.pdf', 'pdf'),
    'blanchette2': (f'{MARKT}/Blanchette/mod2026-02-superposition.pdf', 'pdf'),
    'blanchette3': (f'{MARKT}/Blanchette/mod2026-03-lambda-superposition.pdf', 'pdf'),
    'viper':       (f'{MARKT}/Mueller/AutomatingSeparationLogicWithViper.pdf', 'pdf'),
    # One Google Slides deck covers both of Protzenko's lectures: linearity and Rust up to
    # slide 24, the borrow calculus and Aeneas after it. No printed numbers, so 'pdf'.
    'protzenko':   (f'{MARKT}/Protzenko/Linearity, Rust and Verification (Marktoberdorf\'26).pdf', 'pdf'),
    'pretschner1': (f'{MARKT}/Pretschner/01_IntegrationTests.pdf', 'pdf'),
    'pretschner2': (f'{MARKT}/Pretschner/02_ScenariobasedTesting.pdf', 'pdf'),
    # Converted from PowerPoint by pptx_to_pdf.py. Hidden slides are exported too, so that
    # PDF page number equals slide number and the citations stay correct.
    'mitchell1':   (f'{MARKT}/Mitchell/Markt-26 day 1.pdf', 'pdf'),
    'mitchell2':   (f'{MARKT}/Mitchell/Markt-26 day 2.pdf', 'pdf'),
    'mitchell3':   (f'{MARKT}/Mitchell/Markt-26 day 3.pdf', 'pdf'),
    'mitchell4':   (f'{MARKT}/Mitchell/Markt-26 day 4.pdf', 'pdf'),
    # Grumberg's equations are OMML, which LibreOffice drops. pptx_to_pdf.py works around that
    # by swapping each equation for the picture PowerPoint saved beside it, which fixes
    # lectures 2 and 3 completely (verified by eye). Two decks resist it and stay out:
    # lecture 1 references its equation pictures but never saved them (Target="NULL"), and
    # lecture 4 hangs its pictures on placeholder shapes, whose image fill LibreOffice ignores.
    # Their sections keep plain labels, which is the graceful outcome.
    'grumberg2':   (f'{MARKT}/Grumberg/MARKT26-CHC-lecture2.pdf', 'pdf'),
    'grumberg3':   (f'{MARKT}/Grumberg/MARKT-CHC-lecture3.pdf', 'pdf'),
    # 'grumberg1': equation pictures were never saved into the file
    # 'grumberg4': pictures present but on placeholders LibreOffice will not fill
    # de Moura. Three of his four decks carry a real text layer; "Introduction to Lean and
    # Dependent Type Theory" is page images only, so section 25 cites nothing.
    'demoura2':    (f'{MARKT}/deMoura/Programming and Proving in Lean.pdf', 'pdf'),
    'demoura3':    (f'{MARKT}/deMoura/Software Verification in Lean.pdf', 'pdf'),
    'demoura4':    (f'{MARKT}/deMoura/Proof Automation and AI.pdf', 'pdf'),
}

# section file (relative to sections/) -> deck meant by an unqualified citation, plus decks
# named by a qualifier. A qualifier is how a section that draws on more than one deck of a
# series says which one it means, as in "lecture 2 slide 7".
SECTION_DECKS = {
    'marktoberdorf/01-deductive-verification.html':  {'bare': 'filliatre1'},
    'marktoberdorf/02-weakest-preconditions.html':   {'bare': 'filliatre2'},
    'marktoberdorf/03-ghost-code.html':              {'bare': 'filliatre3'},
    'marktoberdorf/04-verified-alpha-beta.html':     {'bare': 'filliatre4'},
    'marktoberdorf/05-separation-logic-viper.html':  {'bare': 'viper'},
    # Section 6 (Grumberg lecture 1) and section 8 (lecture 4) are intentionally absent:
    # see the note in DECKS. Section 7 cites lectures 2 and 3, both of which now render.
    'marktoberdorf/07-mosaic-theory-modular.html': {'bare': 'grumberg2',
                                                    'lecture2': 'grumberg2',
                                                    'lecture3': 'grumberg3'},
    'marktoberdorf/09-ai-systems-evaluation.html':   {'bare': 'mitchell1'},
    'marktoberdorf/10-ai-architectures.html':        {'bare': 'mitchell2'},
    'marktoberdorf/11-agentic-security.html':        {'bare': 'mitchell3'},
    'marktoberdorf/12-agent-meltdown.html':          {'bare': 'mitchell4'},
    'marktoberdorf/13-integration-testing.html':     {'bare': 'pretschner1'},
    'marktoberdorf/14-scenario-based-testing.html':  {'bare': 'pretschner2'},
    'marktoberdorf/15-javascript-semantics.html':    {'bare': 'ryu1'},
    'marktoberdorf/16-wasm-spectec.html':            {'bare': 'ryu2'},
    'marktoberdorf/17-p4-spectec.html':              {'bare': 'ryu3'},
    'marktoberdorf/18-other-languages.html':         {'bare': 'ryu4'},
    'marktoberdorf/19-linear-types-rust.html':        {'bare': 'protzenko'},
    'marktoberdorf/20-verifying-rust.html':           {'bare': 'protzenko'},
    'marktoberdorf/21-resolution-superposition.html': {'bare': 'blanchette1'},
    'marktoberdorf/22-superposition.html':            {'bare': 'blanchette2'},
    'marktoberdorf/23-lambda-superposition.html':     {'bare': 'blanchette3'},
    # de Moura's first deck is page images only and Blanchette's fourth lecture had no deck,
    # so those sections carry no pills at all and are absent here by design.
    'marktoberdorf/26-lean-programming.html':        {'bare': 'demoura2'},
    'marktoberdorf/27-lean-software-verification.html': {'bare': 'demoura3'},
    'marktoberdorf/28-lean-kernel-ai.html':          {'bare': 'demoura4'},
    'marktoberdorf/31-proof-in-industry.html':       {'bare': 'dodds'},
    'marktoberdorf/32-proof-and-ai.html':            {'bare': 'dodds'},
}

# A pill is either still an authored span or a button from an earlier run. Matching both is
# what makes this script idempotent: every run rebuilds the whole bank from every pill, so a
# rerun after editing one section cannot drop the slides belonging to all the others.
PILL_RE = re.compile(r'<span class="slide-ref">(?P<span>.*?)</span>'
                     r'|<button type="button" class="slide-ref"[^>]*>(?P<btn>.*?)</button>',
                     re.S)


def pill_text(m):
    return m.group('span') if m.group('span') is not None else m.group('btn')
# A citation is either a keyword ("slide"/"page") or a number/range. Scanning them in order
# lets one pill mix the two: the most recent keyword says whether the numbers that follow
# are printed slide numbers or raw PDF pages.
TOKEN_RE = re.compile(r'(?P<word>slides?|pages?)'
                      r'|(?P<range>\b\d{1,3}\s*[–-]\s*\d{1,3}\b)'
                      r'|(?P<num>\b\d{1,3}\b)', re.I)


def printed_to_page(pdf_path):
    """Map the number printed on each slide to the last PDF page that shows it."""
    text = subprocess.run(['pdftotext', '-layout', pdf_path, '-'],
                          capture_output=True, text=True).stdout
    pages = text.split('\f')

    # A beamer footer reads "12 / 31". Lock onto the most common denominator so that a
    # stray "24(1/2)" in a bibliography cannot be mistaken for a slide number.
    denoms = {}
    for page in pages:
        for m in re.finditer(r'\b\d{1,3}\s*/\s*(\d{1,3})\b', page):
            denoms[m.group(1)] = denoms.get(m.group(1), 0) + 1
    total = max(denoms, key=denoms.get) if denoms else None

    numbers = []
    for page in pages:
        lines = [l.strip() for l in page.strip().split('\n') if l.strip()]
        found = None
        for line in reversed(lines[-3:]):           # the footer sits at the bottom
            if total:
                m = re.search(r'\b(\d{1,3})\s*/\s*' + re.escape(total) + r'\b', line)
                if m:
                    found = int(m.group(1))
                    break
            if re.fullmatch(r'\d{1,3}', line):      # decks that print a bare number
                found = int(line)
                break
        numbers.append(found)

    # Keep only a non-decreasing run, so a stray match cannot rewrite an earlier slide.
    cleaned, high = [], 0
    for n in numbers:
        if n is not None and n >= high:
            cleaned.append(n)
            high = n
        else:
            cleaned.append(None)

    mapping = {}
    for i, n in enumerate(cleaned, start=1):
        if n is not None:
            mapping[n] = i                          # a later page of a build wins
    return mapping


def parse_pill(text, decks):
    """Resolve one pill into an ordered list of (deck, number, mode) citations."""
    plain = re.sub(r'<[^>]+>', '', text)
    plain = plain.replace('&ndash;', '–').replace('&nbsp;', ' ')
    out = []
    for chunk in plain.split('·'):
        low = chunk.lower()
        # "lecture 2 slide 7" names one deck of a multi-lecture series. Strip the qualifier
        # before scanning numbers, or the series number itself reads as a citation.
        lec = re.match(r'\s*lectures?\s+(\d+)\s*', low)
        if lec and ('lecture' + lec.group(1)) in decks:
            deck = decks['lecture' + lec.group(1)]
            chunk = chunk[lec.end():]
        elif '2026' in low:
            deck = decks.get('2026', decks['bare'])
        elif '2019' in low:
            deck = decks.get('2019', decks['bare'])
        elif 'companion' in low:
            deck = decks.get('companion', decks['bare'])
        else:
            deck = decks['bare']
        mode = None                                  # set by the first keyword we meet
        for m in TOKEN_RE.finditer(chunk):
            if m.group('word'):
                mode = 'pdf' if m.group('word').lower().startswith('page') else 'printed'
            elif m.group('range'):
                a, b = (int(x) for x in re.split(r'\s*[–-]\s*', m.group('range')))
                span = range(a, b + 1) if a <= b and b - a <= 30 else (a, b)
                for n in span:
                    out.append((deck, n, mode or DECKS[deck][1]))
            else:
                out.append((deck, int(m.group('num')), mode or DECKS[deck][1]))
    return out


def render(pdf_path, page, workdir):
    """Render one PDF page small enough that hundreds of them can be embedded."""
    base = os.path.join(workdir, f'pop-{page:04d}')
    subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-png', '-r', '68',
                    '-singlefile', pdf_path, base], check=True)
    png8, jpg = base + '-8.png', base + '.jpg'
    subprocess.run(['convert', base + '.png', '-resize', '840x>', '-colors', '96',
                    'png8:' + png8], check=True)
    subprocess.run(['convert', base + '.png', '-resize', '840x>', '-quality', '68',
                    jpg], check=True)
    best = png8 if os.path.getsize(png8) <= os.path.getsize(jpg) else jpg
    mime = 'image/png' if best.endswith('.png') else 'image/jpeg'
    data = base64.b64encode(open(best, 'rb').read()).decode()
    return f'data:{mime};base64,{data}', os.path.getsize(best)


def load_bank():
    """Read the bank written by an earlier run, so images can be reused.

    Used for two things: reusing the slides of a deck whose file has since gone missing, and
    reporting how many were carried over. Returns {} if there is no bank yet.
    """
    path = os.path.join(SRC, 'slidebank.html')
    if not os.path.exists(path):
        return {}
    m = re.search(r'<script[^>]*id="slide-bank">(\{.*\})</script>', open(path).read(), re.S)
    if not m:
        return {}
    try:
        import json
        return json.loads(m.group(1))
    except ValueError:
        return {}


def main():
    report_only = '--report' in sys.argv

    # Check every deck up front. Discovering a missing or renamed file halfway through a ten
    # minute render, with the bank already half rebuilt, is a bad way to find out.
    #
    # A deck that has gone missing is not automatically fatal. Its images may already be in
    # the bank from an earlier run, in which case they are reused and the sections that cite
    # it keep working; that beats stripping a hundred slides out of the page because a file
    # was moved. Only a deck with nothing banked stops the run.
    old_bank = load_bank()
    banked = {k.split(':')[0] for k in old_bank}
    missing = [k for k, (name, _) in DECKS.items()
               if not os.path.exists(os.path.join(ROOT, name))]
    frozen = {k for k in missing if k in banked}
    fatal = [k for k in missing if k not in banked]
    if fatal:
        sys.exit('error: deck file(s) not found and nothing banked for them, nothing rendered:\n  '
                 + '\n  '.join(f'{k}: {DECKS[k][0]}' for k in fatal)
                 + '\nFilenames are case sensitive. Fix the path in DECKS, or run '
                   'pptx_to_pdf.py if the deck is still a PowerPoint file.')
    for k in sorted(frozen):
        print(f'  warning: {DECKS[k][0]} is missing; reusing the '
              f'{sum(1 for x in old_bank if x.startswith(k + ":"))} image(s) already in the '
              f'bank. Restore the file to render anything new from it.')
    unknown = sorted({d for m in SECTION_DECKS.values() for d in m.values()} - set(DECKS))
    if unknown:
        sys.exit(f'error: SECTION_DECKS refers to deck key(s) not in DECKS: {unknown}')
    for name in SECTION_DECKS:
        if not os.path.exists(os.path.join(SRC, 'sections', name)):
            sys.exit(f'error: SECTION_DECKS names a section that does not exist: {name}')

    maps = {key: printed_to_page(os.path.join(ROOT, name))
            for key, (name, style) in DECKS.items()
            if style == 'printed' and key not in frozen}

    def to_page(deck, num, mode):
        if mode == 'pdf' or DECKS[deck][1] == 'pdf':
            return num
        return maps[deck].get(num)

    wanted, per_file, unresolved = [], {}, []
    for path in sorted(glob.glob(os.path.join(SRC, 'sections', '*', '*.html'))):
        name = os.path.relpath(path, os.path.join(SRC, 'sections')).replace(os.sep, '/')
        decks = SECTION_DECKS.get(name)
        if not decks:
            continue
        src = open(path).read()
        pills = []
        for m in PILL_RE.finditer(src):
            inner = pill_text(m)
            key = None
            for deck, num, mode in parse_pill(inner, decks):
                page = to_page(deck, num, mode)
                if page is None:
                    unresolved.append((name, deck, num,
                                       re.sub(r'<[^>]+>', '', inner).strip()))
                    continue
                key = f'{deck}:{page}'               # the first citation is the primary
                break
            if key and key not in wanted:
                wanted.append(key)
            pills.append((m.span(), inner, key))
        per_file[path] = (src, pills)

    total = sum(len(p) for _, p in per_file.values())
    linked = sum(1 for _, p in per_file.values() for _, _, k in p if k)
    print(f'{total} pills, {linked} resolve to a slide, {len(wanted)} distinct to render')
    if unresolved:
        print(f'  {len(unresolved)} unresolved citation(s):')
        for row in unresolved[:12]:
            print(f'    {row[0]}: {row[1]} {row[2]}  (pill: "{row[3]}")')
    if report_only:
        return

    bank, total_bytes = {}, 0
    with tempfile.TemporaryDirectory() as workdir:
        by_deck = {}
        for key in wanted:
            deck, page = key.rsplit(':', 1)
            by_deck.setdefault(deck, []).append(int(page))
        for deck, pages in sorted(by_deck.items()):
            if deck in frozen:
                kept = 0
                for page in sorted(pages):
                    uri = old_bank.get(f'{deck}:{page}')
                    if uri:
                        bank[f'{deck}:{page}'] = uri
                        total_bytes += len(uri)
                        kept += 1
                print(f'  {deck}: {kept} slides reused from the bank (file missing)')
                continue
            pdf = os.path.join(ROOT, DECKS[deck][0])
            for page in sorted(pages):
                uri, size = render(pdf, page, workdir)
                bank[f'{deck}:{page}'] = uri
                total_bytes += size
            print(f'  {deck}: {len(pages)} slides')

    entries = ',\n'.join(f'"{k}":"{v}"' for k, v in sorted(bank.items()))
    open(os.path.join(SRC, 'slidebank.html'), 'w').write(
        '<!-- generated by slide_popups.py: slides opened by the .slide-ref buttons -->\n'
        '<script type="application/json" id="slide-bank">{\n' + entries + '\n}</script>\n')
    print(f'slidebank.html: {len(bank)} slides, {total_bytes // 1024} KB of images')

    for path, (scanned, pills) in per_file.items():
        # Rewrite the exact text the offsets were computed against, not whatever is on disk
        # now. Re-reading here once corrupted two sections that were being edited in another
        # process while this script ran: the offsets were stale and the buttons landed inside
        # unrelated tags. If the file moved under us, skip it and say so rather than mangle it.
        if open(path).read() != scanned:
            print(f'  warning: {os.path.basename(path)} changed while this ran; '
                  f'its pills were left alone. Rerun once it is stable.')
            continue
        src = scanned
        for (start, end), inner, key in reversed(pills):
            if not key:
                continue
            src = (src[:start]
                   + f'<button type="button" class="slide-ref" data-slide="{key}"'
                     f' title="Open this slide">{inner.strip()}</button>'
                   + src[end:])
        open(path, 'w').write(src)
    print(f'rewrote pills in {len(per_file)} section files')


if __name__ == '__main__':
    main()
