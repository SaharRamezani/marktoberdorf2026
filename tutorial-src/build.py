#!/usr/bin/env python3
"""Assemble ../index.html from shell.html plus the per-school section folders.

The shell carries the CSS, the JavaScript and four markers that this script fills in:

    <!-- SCHOOLMETA -->   school config as JSON, read by the menu builder
    <!-- SCHEDULE -->     front-page cards, one per school, generated from the sections
    <!-- SECTIONS -->     the section files themselves, in school then filename order
    <!-- SLIDEBANK -->    the generated slide images (see slide_popups.py)

Section files declare their own metadata on the opening tag (data-num, data-day,
data-title, data-lecturer, data-time). This script adds data-school from the folder the
file sits in, so a section never has to repeat which school it belongs to. To add a
school: create sections/<dir>/, add an entry to schools.json, and run this.
"""
import glob
import html
import json
import os
import re
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
# The output is index.html at the repo root so that GitHub Pages serves it at the site's
# root URL. Pages has no way to nominate a different default file: without an index.html
# the root URL is a 404, whatever else the repository contains.
OUT = os.path.join(os.path.dirname(SRC), 'index.html')
CONFIG = os.path.join(SRC, 'schools.json')

MARKERS = {
    'sections': '<!-- SECTIONS -->',
    'schedule': '<!-- SCHEDULE -->',
    'meta': '<!-- SCHOOLMETA -->',
    'bank': '<!-- SLIDEBANK -->',
}

SECTION_RE = re.compile(r'<section class="lecture"\s([^>]*)>')
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


LECNUM_RE = re.compile(r'(<div class="lec-num">)([^<]*)(</div>)')


def read_section(path: str, school: str, num: int) -> dict:
    """Parse one section file, tag it with its school, and give it its display number.

    The number comes from the file's position in the folder, not from the file itself, so
    inserting a lecture in the middle of a series does not mean renumbering the ones after
    it. Sort order is the filename, which is why the files are named 01-, 02- and so on.
    """
    src = open(path).read().strip()
    m = SECTION_RE.search(src)
    if not m:
        sys.exit(f'error: {path} does not open with <section class="lecture" ...>')
    # Cheap structural guard. check.py is the real validator, but its exit code is easy to lose
    # in a pipeline, and a half-written section must never reach index.html. These two checks
    # catch the ways a fragment actually breaks: truncation, and stray closing tags from a bad
    # find-and-replace.
    if not src.endswith('</section>'):
        sys.exit(f'error: {path} does not end with </section>. It is truncated or corrupted; '
                 f'run check.py for the details. Nothing was written.')
    if src.count('<button') != src.count('</button>'):
        sys.exit(f'error: {path} has {src.count("<button")} <button> and '
                 f'{src.count("</button>")} </button>. Run check.py. Nothing was written.')
    attrs = dict(ATTR_RE.findall(m.group(1)))
    if 'id' not in attrs:
        sys.exit(f'error: {path} has no id on its section tag')

    tag = f'<section class="lecture" data-school="{school}" {m.group(1)}>'
    tag = re.sub(r'data-num="[^"]*"', f'data-num="{num}"', tag)
    if 'data-num=' not in tag:
        tag = tag.replace('<section class="lecture"', f'<section class="lecture" data-num="{num}"', 1)
    src = src.replace(m.group(0), tag, 1)
    src = LECNUM_RE.sub(lambda mm: mm.group(1) + str(num) + mm.group(3), src, count=1)

    return {
        'file': os.path.basename(path),
        'id': attrs['id'],
        'num': str(num),
        'day': attrs.get('data-day', ''),
        'title': attrs.get('data-title', ''),
        'lecturer': attrs.get('data-lecturer', ''),
        'time': attrs.get('data-time', ''),
        'html': src,
    }


def load() -> tuple:
    cfg = json.load(open(CONFIG))
    schools = []
    for key in cfg['order']:
        meta = cfg['schools'][key]
        paths = sorted(glob.glob(os.path.join(SRC, 'sections', meta['dir'], '*.html')))
        if not paths:
            print(f'  warning: no section files in sections/{meta["dir"]}/')
        schools.append({'key': key, 'meta': meta,
                        'sections': [read_section(p, key, i)
                                     for i, p in enumerate(paths, 1)]})
    return cfg, schools


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def render_schedule(schools: list) -> str:
    """Front-page cards: one per school, sections grouped by their data-day."""
    out = []
    for school in schools:
        meta, secs = school['meta'], school['sections']
        out.append(f'<article class="school-card" id="card-{school["key"]}">')
        out.append(f'  <p class="kicker">{esc(meta["where"])} · {esc(meta["when"])}</p>')
        out.append(f'  <h2>{esc(meta["name"])}</h2>')
        out.append(f'  <p class="school-blurb">{esc(meta["blurb"])}</p>')
        groups = meta.get('groups', {})
        notes = meta.get('notes', {})
        for day, label in groups.items():
            in_day = [s for s in secs if s['day'] == day]
            if not in_day and day not in notes:
                continue
            out.append(f'  <p class="sched-day">{esc(label)}</p>')
            if day in notes:
                out.append(f'  <p class="sched-note">{esc(notes[day])}</p>')
            if not in_day:
                continue
            out.append('  <nav class="sched" aria-label="' + esc(label) + '">')
            for s in in_day:
                time = f'<span class="time">{esc(s["time"])}</span>' if s['time'] else ''
                out.append(
                    f'    <a href="#{s["id"]}">{time}'
                    f'<p class="t"><span class="num">{esc(s["num"])}</span>{esc(s["title"])}</p>'
                    f'<span class="who">{esc(s["lecturer"])}</span></a>')
            out.append('  </nav>')
        out.append('</article>')
    return '\n'.join(out)


def render_sections(schools: list) -> str:
    """Section bodies, preceded by a banner that names the school they belong to."""
    parts = []
    for school in schools:
        meta = school['meta']
        if not school['sections']:
            continue
        parts.append(
            f'<div class="school-banner" id="school-{school["key"]}" '
            f'data-school="{school["key"]}">\n'
            f'  <span class="school-banner-tag">Summer school</span>\n'
            f'  <h2>{esc(meta["name"])}</h2>\n'
            f'  <p>{esc(meta["where"])} · {esc(meta["when"])}</p>\n'
            f'</div>')
        for s in school['sections']:
            parts.append(f'<!-- ===== {meta["dir"]}/{s["file"]} ===== -->\n' + s['html'])
    return '\n\n'.join(parts)


def render_meta(schools: list) -> str:
    """Config the menu builder needs, as an inert JSON island."""
    payload = [{'key': s['key'], 'name': s['meta']['name'], 'short': s['meta']['short'],
                'where': s['meta']['where'], 'when': s['meta']['when'],
                'groups': s['meta'].get('groups', {})} for s in schools]
    return ('<script type="application/json" id="school-meta">'
            + json.dumps(payload, ensure_ascii=False) + '</script>')


def main() -> None:
    cfg, schools = load()
    shell = open(os.path.join(SRC, 'shell.html')).read()
    for name, marker in MARKERS.items():
        if marker not in shell and name != 'bank':
            sys.exit(f'error: {marker} missing from shell.html')

    bank_path = os.path.join(SRC, 'slidebank.html')
    bank = open(bank_path).read().strip() if os.path.exists(bank_path) else ''
    if bank and MARKERS['bank'] not in shell:
        sys.exit(f'error: {MARKERS["bank"]} missing from shell.html but slidebank.html exists')

    html_out = shell
    for marker, body in ((MARKERS['meta'], render_meta(schools)),
                         (MARKERS['schedule'], render_schedule(schools)),
                         (MARKERS['sections'], render_sections(schools)),
                         (MARKERS['bank'], bank)):
        if marker in html_out:
            html_out = html_out.replace(marker, body)

    open(OUT, 'w').write(html_out)
    total = sum(len(s['sections']) for s in schools)
    print(f'wrote {OUT}: {os.path.getsize(OUT) // 1024} KB')
    for s in schools:
        print(f'  {s["key"]}: {len(s["sections"])} sections')
    extra = f', slide bank {os.path.getsize(bank_path) // 1024} KB' if bank else ''
    print(f'  {total} sections total{extra}')


if __name__ == '__main__':
    main()
