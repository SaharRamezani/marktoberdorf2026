#!/usr/bin/env python3
"""Static checks over the section files and the shell, run before build.py.

Per file: JavaScript syntax, JSON widget payloads, id prefixing and uniqueness, tag
balance, and the house style rules. Across files: no id is claimed twice, every section
declares the metadata build.py needs, and every data-day matches a group in schools.json.

The id prefix is not configured anywhere: it is taken from the id on the section's own h2,
so a new section file only has to be internally consistent.
"""
import glob
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser

SRC = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(SRC, 'schools.json')
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
        'param', 'source', 'track', 'wbr'}
REQUIRED_ATTRS = ('data-num', 'data-day', 'data-title')


class TagChecker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    self.errors.append(f'line {self.getpos()[0]}: </{tag}> closes over '
                                       f'unclosed {[t for t, _ in self.stack[i + 1:]]}')
                    del self.stack[i:]
                    break
            else:
                self.errors.append(f'line {self.getpos()[0]}: stray </{tag}>')


def check_style(src: str, problems: list) -> None:
    if '—' in src:
        lines = [i + 1 for i, l in enumerate(src.split('\n')) if '—' in l]
        problems.append(f'{len(lines)} line(s) contain em-dashes, e.g. lines {lines[:6]}')
    if 'trans-notes' in src:
        problems.append('transcription-fixes block still present')
    ext = re.findall(r'(?:src|href)="(https?://[^"]+)"', src)
    if ext:
        problems.append(f'external refs: {ext[:5]}')


def check_media_order(src: str, problems: list) -> None:
    """A small-screen rule that a later base rule silently beats is worse than no rule.

    A media query adds no specificity, so `@media (max-width:900px){#menu-btn{display:flex}}`
    loses to a plain `#menu-btn{display:none}` declared further down the file, and nothing
    warns you: the phone layout just quietly does not happen. That is how the menu button
    ended up invisible on mobile. The fix is to keep the whole small-screen layer after
    everything it overrides, and this is what holds it there.
    """
    start = src.find('<style>')
    if start < 0:
        return
    # Comments are stripped first so that a rule sitting under one is still seen.
    css = re.sub(r'/\*.*?\*/', lambda m: ' ' * len(m.group(0)), src[start:src.index('</style>')],
                 flags=re.S)

    spans = []
    for m in re.finditer(r'@media [^{]*\{', css):
        depth, i = 1, m.end()
        while depth and i < len(css):
            if css[i] == '{':
                depth += 1
            elif css[i] == '}':
                depth -= 1
            i += 1
        spans.append((m.start(), i, m.group(0)))

    def media_at(pos: int):
        for a, b, head in spans:
            if a <= pos < b:
                return (a, b, head)
        return None

    # Every rule in the sheet, in order. Enumerating once avoids the trap of matching rules
    # by their preceding brace: that brace belongs to the previous rule's match, so a scan
    # written that way silently sees only every other rule.
    rules = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        decl = m.group(2)
        for sel in m.group(1).split(','):
            sel = sel.strip()
            if sel and not sel.startswith('@'):
                rules.append((m.start(1) + m.group(1).index(sel.split()[0]), sel, decl))

    beaten = []
    for pos, sel, decl in rules:
        here = media_at(pos)
        if not here or 'max-width' not in here[2] or '!important' in decl:
            continue
        for pos2, sel2, _ in rules:
            if sel2 == sel and pos2 > here[1] and media_at(pos2) is None:
                beaten.append(sel)
                break
    if beaten:
        problems.append(f'small-screen rule(s) overridden by a later base rule, so they never '
                        f'apply: {sorted(set(beaten))[:6]}. Move the small-screen layer below '
                        f'the rules it overrides.')


def check_quiz(d: dict, where: str, problems: list) -> None:
    """A quiz that parses can still be unanswerable, so check its shape too.

    Every fill quiz once used the key 'accept' while the grader read 'answers', which meant no
    correct answer was ever accepted anywhere in the tutorial and nothing complained.
    """
    kind = d.get('type')
    if kind == 'fill':
        acc = d.get('accept') or d.get('answers')
        # the grader lowercases and collapses whitespace on both sides, so case here is free
        if not acc or not isinstance(acc, list):
            problems.append(f'{where}: fill quiz has no accept list')
        elif any(not isinstance(a, str) or not a.strip() for a in acc):
            problems.append(f'{where}: fill answers must be non-empty strings, got {acc}')
    elif kind == 'mc':
        opts, ans = d.get('options'), d.get('answer')
        if not isinstance(opts, list) or len(opts) < 2:
            problems.append(f'{where}: mc quiz needs at least two options')
        elif not isinstance(ans, int) or not 0 <= ans < len(opts):
            problems.append(f'{where}: mc answer {ans!r} is not an index into {len(opts)} options')
    elif kind == 'tf':
        if not isinstance(d.get('answer'), bool):
            problems.append(f'{where}: tf quiz answer must be true or false')
    elif kind is not None:
        problems.append(f'{where}: unknown quiz type {kind!r}')
    if kind and not d.get('explain'):
        problems.append(f'{where}: quiz has no explanation')


def check_scripts(src: str, name: str, problems: list) -> None:
    for m in re.finditer(r'<script type="application/json">(.*?)</script>', src, re.S):
        line = src[:m.start()].count(chr(10)) + 1
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            problems.append(f'JSON block at line {line}: {e}')
            continue
        if isinstance(payload, dict) and 'type' in payload:
            check_quiz(payload, f'quiz at line {line}', problems)
    for k, body in enumerate(re.findall(r'<script>(.*?)</script>', src, re.S)):
        tmp = os.path.join(SRC, f'_chk-{name}-{k}.js')
        open(tmp, 'w').write(body)
        r = subprocess.run(['node', '--check', tmp], capture_output=True, text=True)
        if r.returncode != 0:
            problems.append(f'script #{k} fails node --check: {r.stderr.strip()[:300]}')
        os.remove(tmp)


def check_tags(src: str, problems: list) -> None:
    stripped = re.sub(r'<script.*?</script>', '<script></script>', src, flags=re.S)
    tc = TagChecker()
    tc.feed(stripped)
    if tc.stack:
        problems.append(f'unclosed tags at EOF: {[t for t, p in tc.stack][:10]}')
    problems += tc.errors[:10]


def check(path: str, label: str, seen_ids: dict, groups: set) -> int:
    """Check one file. seen_ids maps an id to the file that already used it."""
    name = os.path.basename(path)
    src = open(path).read()
    problems = []
    is_section = 'class="lecture"' in src

    ids = re.findall(r'\sid="([^"]+)"', src)
    if is_section:
        h2 = re.search(r'<h2 id="([^"]+)"', src)
        if not h2:
            problems.append('section has no <h2 id="...">, so no id prefix can be derived')
        else:
            pref = h2.group(1).split('-')[0] + '-'
            bad = [i for i in ids if not (i.startswith(pref) or i.startswith('sec-'))]
            if bad:
                problems.append(f'ids without prefix {pref}: {bad[:8]}')

        tag = re.search(r'<section class="lecture"([^>]*)>', src)
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', tag.group(1))) if tag else {}
        missing = [a for a in REQUIRED_ATTRS if a not in attrs]
        if missing:
            problems.append(f'section tag is missing {missing}')
        if groups and attrs.get('data-day') and attrs['data-day'] not in groups:
            problems.append(f'data-day "{attrs["data-day"]}" is not a group in schools.json')
        if not src.rstrip().endswith('</section>'):
            problems.append('file does not end with </section>')

    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        problems.append(f'duplicate ids inside this file: {sorted(dup)[:8]}')
    for i in ids:
        if i in seen_ids and seen_ids[i] != label:
            problems.append(f'id "{i}" is already used by {seen_ids[i]}')
        seen_ids.setdefault(i, label)

    check_scripts(src, name, problems)
    check_tags(src, problems)
    check_style(src, problems)
    if name == 'shell.html':
        check_media_order(src, problems)

    print(f'--- {label}: {len(src) // 1024} KB')
    for p in problems:
        print(f'  PROBLEM: {p}')
    if not problems:
        print('  clean')
    return len(problems)


def main() -> None:
    groups = set()
    if os.path.exists(CONFIG):
        cfg = json.load(open(CONFIG))
        for meta in cfg['schools'].values():
            groups |= set(meta.get('groups', {}))

    seen_ids = {}
    total = 0
    files = sorted(glob.glob(os.path.join(SRC, 'sections', '*', '*.html')))
    if not files:
        sys.exit('error: no section files found under sections/*/')
    for f in files:
        label = os.path.relpath(f, os.path.join(SRC, 'sections'))
        total += check(f, label, seen_ids, groups)
    total += check(os.path.join(SRC, 'shell.html'), 'shell.html', seen_ids, groups)

    print(f'\n{len(files)} sections checked, {total} problem(s)')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
