#!/usr/bin/env python3
"""Replace <img data-slide="deck:page"> placeholders in sections/*/*.html with inline
data URIs rendered from the source PDFs. Requires pdftoppm + ImageMagick convert.
Idempotent: files without placeholders are left untouched."""
import base64
import glob
import os
import re
import subprocess
import sys
import tempfile

# The decks live in one place only, the DECKS table in slide_popups.py, so a renamed or
# replaced deck never has to be edited in two files.
from slide_popups import DECKS

SRC = os.path.dirname(os.path.abspath(__file__))
PDFS = {key: os.path.join('..', path) for key, (path, _style) in DECKS.items()}
KEYS = '|'.join(sorted(PDFS, key=len, reverse=True))


def render(deck: str, page: int, workdir: str) -> str:
    pdf = os.path.normpath(os.path.join(SRC, PDFS[deck]))
    base = os.path.join(workdir, f'{deck}-{page:03d}')
    subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-png', '-r', '110',
                    '-singlefile', pdf, base], check=True)
    png8, jpg = base + '-8.png', base + '.jpg'
    subprocess.run(['convert', base + '.png', '-resize', '1400x>', '-colors', '256',
                    'png8:' + png8], check=True)
    subprocess.run(['convert', base + '.png', '-resize', '1400x>', '-quality', '86',
                    jpg], check=True)
    return png8 if os.path.getsize(png8) <= os.path.getsize(jpg) else jpg


def main() -> None:
    with tempfile.TemporaryDirectory() as workdir:
        for path in sorted(glob.glob(os.path.join(SRC, 'sections', '*', '*.html'))):
            src = open(path).read()
            if 'data-slide="' not in src:
                continue

            def sub(m: 're.Match') -> str:
                deck, page = m.group(2), int(m.group(3))
                img = render(deck, page, workdir)
                mime = 'image/png' if img.endswith('.png') else 'image/jpeg'
                uri = f'data:{mime};base64,' + base64.b64encode(open(img, 'rb').read()).decode()
                print(f'  {os.path.basename(path)}: {deck}:{page} '
                      f'({os.path.getsize(img)//1024} KB)')
                return f'<img{m.group(1)}src="{uri}"{m.group(4)}>'

            out = re.sub(r'<img([^>]*?)data-slide="(' + KEYS + r'):(\d+)"([^>]*?)>', sub, src)
            open(path, 'w').write(out)
    print('done')


if __name__ == '__main__':
    main()
