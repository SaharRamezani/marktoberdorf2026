#!/usr/bin/env python3
"""Rewrite a .pptx so its equations survive conversion to PDF.

PowerPoint stores an equation twice: `mc:Choice Requires="a14"` holds the real OMML markup, and
`mc:Fallback` holds a picture of the same equation for readers that cannot do OMML. LibreOffice
takes the Choice branch and then renders almost none of it, which is why a converted slide can
show arrows and labels pointing at blank space.

This produces a copy of the deck with every `mc:AlternateContent` block replaced by its own
`mc:Fallback`, leaving only the picture, which LibreOffice renders correctly. The output is fit
for rendering to images only; it is not a deck to edit.

Whether this helps depends on the deck. Some files reference the fallback picture but never
saved it, leaving `Target="NULL"` in the slide relationships; there is nothing to recover in
that case and the script says so.

    python3 flatten_omml.py in.pptx out.pptx
"""
import re
import sys
import zipfile

OPEN, CLOSE = '<mc:AlternateContent', '</mc:AlternateContent>'


def spans(s):
    """(start, end) of each top-level mc:AlternateContent block, in document order."""
    out, i = [], 0
    while True:
        a = s.find(OPEN, i)
        if a < 0:
            return out
        depth, j = 0, a + len(OPEN)
        while True:
            na, nc = s.find(OPEN, j), s.find(CLOSE, j)
            if nc < 0:
                return out                       # malformed; leave the rest alone
            if 0 <= na < nc:
                depth, j = depth + 1, na + len(OPEN)
            elif depth:
                depth, j = depth - 1, nc + len(CLOSE)
            else:
                out.append((a, nc + len(CLOSE)))
                i = nc + len(CLOSE)
                break


def fallback_of(block):
    m = re.search(r'<mc:Fallback[^>]*>', block)
    end = block.rfind('</mc:Fallback>')
    return block[m.end():end] if m and end > m.end() else None


def flatten(xml):
    changed = 0
    for a, b in reversed(spans(xml)):
        body = fallback_of(xml[a:b])
        if body is not None:
            xml, changed = xml[:a] + body + xml[b:], changed + 1
    return xml, changed


def dangling(z):
    """Count image relationships whose target was never saved."""
    n = 0
    for name in z.namelist():
        if re.match(r'ppt/slides/_rels/', name):
            n += sum(1 for m in re.finditer(r'Type="[^"]*/image"[^>]*Target="([^"]+)"',
                                            z.read(name).decode('utf8'))
                     if m.group(1) == 'NULL')
    return n


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]
    with zipfile.ZipFile(src) as z:
        bad = dangling(z)
        edits, total = {}, 0
        for n in z.namelist():
            if re.match(r'ppt/(slides|notesSlides)/\w+\.xml$', n):
                new, changed = flatten(z.read(n).decode('utf8'))
                if changed:
                    edits[n], total = new.encode('utf8'), total + changed
        with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as out:
            for item in z.infolist():
                out.writestr(item, edits.get(item.filename, z.read(item.filename)))
    print(f'{total} equation block(s) replaced by their picture across {len(edits)} slide(s)')
    if bad:
        print(f'  warning: {bad} image reference(s) in this deck have Target="NULL", so those '
              f'pictures were never saved and cannot be recovered here.')


if __name__ == '__main__':
    main()
