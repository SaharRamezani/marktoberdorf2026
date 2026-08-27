#!/usr/bin/env python3
"""Convert the PowerPoint decks under ../marktoberdorf/slides/ to PDF, so slide_popups.py
can render them.

Two things happen here that a bare soffice call does not do.

Hidden slides are exported. LibreOffice skips them by default, which silently shifts every
page after the first hidden one, and the sections cite slide numbers.

Equations are flattened to their pictures first (see flatten_omml.py). LibreOffice reads the
OMML branch of an equation and renders almost none of it, so a converted slide can show arrows
and labels pointing at blank space. Replacing each equation with the picture PowerPoint saved
beside it fixes that, where the picture was in fact saved.

Every deck is verified after conversion: the PDF must have exactly as many pages as the
pptx has slides. A mismatch is reported and the exit status is non-zero.

    python3 pptx_to_pdf.py            # convert any deck whose PDF is missing or stale
    python3 pptx_to_pdf.py --force    # reconvert everything
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import flatten_omml

SRC = os.path.dirname(os.path.abspath(__file__))
DECK_DIR = os.path.normpath(os.path.join(SRC, '..', 'marktoberdorf', 'slides'))
# LibreOffice writes into $HOME; keep it out of the real profile so a running instance of
# the desktop app cannot collide with this one.
PROFILE = os.path.join(SRC, '.lo-profile')
FILTER = ('pdf:impress_pdf_Export:'
          '{"ExportHiddenSlides":{"type":"boolean","value":"true"}}')


def slide_count(pptx: str) -> int:
    with zipfile.ZipFile(pptx) as z:
        return len([n for n in z.namelist()
                    if re.match(r'ppt/slides/slide\d+\.xml$', n)])


def page_count(pdf: str) -> int:
    out = subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout
    m = re.search(r'Pages:\s+(\d+)', out)
    return int(m.group(1)) if m else -1


def convert(pptx: str) -> None:
    """Flatten equations to pictures, convert, and leave the PDF beside the original deck."""
    env = dict(os.environ, HOME=PROFILE)
    out_dir = os.path.dirname(pptx)
    with tempfile.TemporaryDirectory() as tmp:
        flat = os.path.join(tmp, os.path.basename(pptx))
        with zipfile.ZipFile(pptx) as z:
            edits = {}
            for n in z.namelist():
                if re.match(r'ppt/(slides|notesSlides)/\w+\.xml$', n):
                    new, changed = flatten_omml.flatten(z.read(n).decode('utf8'))
                    if changed:
                        edits[n] = new.encode('utf8')
            with zipfile.ZipFile(flat, 'w', zipfile.ZIP_DEFLATED) as o:
                for item in z.infolist():
                    o.writestr(item, edits.get(item.filename, z.read(item.filename)))
        subprocess.run(['soffice', '--headless', '--convert-to', FILTER,
                        '--outdir', tmp, flat], check=True, capture_output=True, env=env)
        produced = os.path.join(tmp, os.path.splitext(os.path.basename(pptx))[0] + '.pdf')
        shutil.move(produced, os.path.join(out_dir, os.path.basename(produced)))


def main() -> None:
    force = '--force' in sys.argv
    if not subprocess.run(['which', 'soffice'], capture_output=True).returncode == 0:
        sys.exit('error: soffice not found. Install it with:\n'
                 '  sudo apt install libreoffice-impress')
    os.makedirs(PROFILE, exist_ok=True)

    decks = sorted(glob.glob(os.path.join(DECK_DIR, '*', '*.pptx')))
    if not decks:
        sys.exit(f'error: no .pptx files under {DECK_DIR}')

    problems = 0
    for pptx in decks:
        pdf = pptx[:-5] + '.pdf'
        name = os.path.relpath(pptx, DECK_DIR)
        fresh = (os.path.exists(pdf)
                 and os.path.getmtime(pdf) >= os.path.getmtime(pptx))
        if fresh and not force:
            print(f'  skip     {name} (PDF is up to date)')
            continue
        convert(pptx)
        slides, pages = slide_count(pptx), page_count(pdf)
        if slides == pages:
            print(f'  ok       {name}: {pages} pages')
        else:
            print(f'  MISMATCH {name}: {slides} slides but {pages} pages, '
                  f'so slide numbers and page numbers disagree')
            problems += 1

    print(f'\n{len(decks)} deck(s), {problems} problem(s)')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
