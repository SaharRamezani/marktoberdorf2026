# Tutorial sources

Source tree for `../index.html`, an interactive study companion covering the
Marktoberdorf summer school of August 2026.

## Layout

```
tutorial-src/
├── schools.json          the list of schools, in display order: folder, title, dates,
│                         and the label for each data-day group. Adding a school means
│                         adding a folder and an entry here, nothing else.
├── shell.html            page skeleton: design tokens, CSS, hero/footer, shared JS
│                         (theme toggle, collapsible menu + scrollspy, menu search,
│                         per-section reading progress, text highlighting, saved
│                         questions, all in localStorage and covered by one JSON
│                         export/import, quiz / cnf-play / stepper / tabs components,
│                         image lightbox shared by figures and slide popups, and the
│                         small-screen layer: the menu becomes a drawer under 900px,
│                         tables are wrapped in scrolling boxes and wide diagrams are
│                         marked so they scroll instead of shrinking)
├── sections/             one self-contained <section> fragment per lecture
│   └── marktoberdorf/    30 sections, grouped by lecture series
│       ├── 01-deductive-verification.html      Jean-Christophe Filliâtre
│       ├── 02-weakest-preconditions.html       Jean-Christophe Filliâtre
│       ├── 03-ghost-code.html                  Jean-Christophe Filliâtre
│       ├── 04-verified-alpha-beta.html         Jean-Christophe Filliâtre
│       ├── 05-separation-logic-viper.html      Peter Müller
│       ├── 06-constrained-horn-clauses.html    Orna Grumberg
│       ├── 07-mosaic-theory-modular.html       Orna Grumberg
│       ├── 08-condition-synthesis.html         Orna Grumberg
│       ├── 09-ai-systems-evaluation.html       John C. Mitchell
│       ├── 10-ai-architectures.html            John C. Mitchell
│       ├── 11-agentic-security.html            John C. Mitchell
│       ├── 12-agent-meltdown.html              John C. Mitchell
│       ├── 13-integration-testing.html         Alexander Pretschner
│       ├── 14-scenario-based-testing.html      Alexander Pretschner
│       ├── 15-javascript-semantics.html        Sukyoung Ryu
│       ├── 16-wasm-spectec.html                Sukyoung Ryu
│       ├── 17-p4-spectec.html                  Sukyoung Ryu
│       ├── 18-other-languages.html             Sukyoung Ryu
│       ├── 19-linear-types-rust.html           Jonathan Protzenko
│       ├── 20-verifying-rust.html              Jonathan Protzenko
│       ├── 21-resolution-superposition.html    Jasmin Blanchette
│       ├── 22-superposition.html               Jasmin Blanchette
│       ├── 23-lambda-superposition.html        Jasmin Blanchette
│       ├── 24-formalizing-provers.html         Jasmin Blanchette
│       ├── 25-lean-dependent-types.html        Leonardo de Moura
│       ├── 26-lean-programming.html            Leonardo de Moura
│       ├── 27-lean-software-verification.html  Leonardo de Moura
│       ├── 28-lean-kernel-ai.html              Leonardo de Moura
│       ├── 31-proof-in-industry.html           Mike Dodds
│       └── 32-proof-and-ai.html                Mike Dodds
├── slidebank.html        generated: the slide images opened by the .slide-ref buttons
├── build.py              fills the four markers in shell.html (school metadata, front
│                         page schedule, sections, slide bank) and writes ../index.html
├── inject_slides.py      renders <img data-slide="deck:page"> placeholders into inline
│                         data URIs, using the deck table in slide_popups.py; idempotent,
│                         run before build.py
├── pptx_to_pdf.py        converts the PowerPoint decks to PDF (hidden slides included and
│                         equations flattened to pictures); only needed when a deck changes
├── flatten_omml.py       swaps each PowerPoint equation for the picture saved beside it, so
│                         LibreOffice cannot drop it; used by pptx_to_pdf.py
├── slide_popups.py       turns every slide-ref pill into a button that opens that slide,
│                         and regenerates slidebank.html from every pill in the tree
├── domtest.js            behavioural test: loads ../index.html in jsdom and drives it
│                         (menu, search, read flags, folding, ask panel, quizzes, pills)
└── check.py              static checks: JS syntax (node --check), JSON component blocks,
                          id prefixes and cross-file id collisions, required section
                          metadata, tag balance, house style rules
```

## Workflow

```bash
python3 check.py           # validate sections and shell
python3 inject_slides.py   # replace any data-slide placeholders with rendered slides
python3 slide_popups.py    # only after adding/editing slide-ref pills (slow: renders PDFs)
python3 build.py           # regenerate ../index.html
```

`slide_popups.py --report` resolves every pill and prints what it would render without
touching a file, which is the quick way to check a new citation is understood. It also
validates every deck path up front, so a renamed deck fails in a second rather than ten
minutes into a render.

The output is a single self-contained file: open it in any browser, no server needed.

### Testing the built page

`check.py` validates the sources. `domtest.js` validates what actually ships: it loads
`../index.html` in jsdom and drives it as a reader would, then asserts on the result.

```bash
cd /tmp/scratch && npm install jsdom     # once; jsdom is not vendored
node /path/to/tutorial-src/domtest.js
```

It covers the menu tree, search, read flags, lecture folding, the ask panel, and the widgets,
and it checks three things that have silently broken before: that every clickable slide pill
resolves to an image actually present in the bank, that every multiple-choice quiz accepts its
own declared answer, and that every fill-in quiz does too. That last one was broken across the
whole tutorial for a long time, because the sections wrote `accept` while the grader read
`answers`, and nothing complained.

## How a section is wired in

A section declares its own metadata on its opening tag, and everything else is derived:

```html
<section class="lecture" id="sec-mk-1" data-time="" data-num="1" data-day="mk-dv"
         data-title="Deductive Verification with Why3"
         data-lecturer="Jean-Christophe Filliatre">
```

`build.py` adds `data-school` from the folder the file sits in, so a section never repeats
which school it belongs to. `data-day` selects the group label from `schools.json`. The menu,
the front page cards and the reading-progress counter are all built from these attributes at
run time, so there is no second place to update when a section is added, renamed or moved.

`data-num` and the `<div class="lec-num">` are **overwritten at build time** from the file's
position in its folder, so a section's displayed number always matches its place in the running
order. Inserting a lecture in the middle of a series is therefore just a matter of dropping in a
file whose name sorts to the right place; nothing after it has to be renumbered. Write a sensible
number in the file anyway so it reads correctly on its own. Filenames are spaced out (01, 02, 03,
05, 06, …) precisely to leave room for insertions.

To add a lecture: create the file, give every id inside it a prefix that nothing else uses, set
`data-day` to one of the groups in `schools.json`, and run `check.py`. To add a school: create
`sections/<dir>/`, add an entry to `schools.json`, and run `build.py`.

## Conventions

- Each section is one `<section class="lecture">`. Every id inside it starts with a prefix
  taken from the id on its own `h2` (`mk1-`, `mkd1-`, and so on); `check.py` derives the prefix
  rather than storing a list, and also fails if two files claim the same id.
- Every `h3` needs an id, because the menu's third level is built from them.
- Styling only through the CSS classes and custom properties defined in `shell.html`; never
  hard-code colors (light/dark themes flip via CSS variables).
- Interactive components are declarative: a `div` with class `quiz` / `cnf-play` / `stepper` /
  `tabs` plus a JSON `<script type="application/json">` payload or `.step` / `.tab` children.
  Custom widgets are IIFE `<script>` blocks at the end of their section.
- House style: no em-dashes; en-dashes only in numeric ranges.

## Slide popups

A pill written as `<span class="slide-ref">slide 12</span>` becomes a button that opens the
slide image. `slide_popups.py` maps the citation to a PDF page, renders it once into
`slidebank.html`, and rewrites the pill. Decks are listed in its `DECKS` table in one of two
numbering styles: `printed`, where the number printed on the slide is mapped to the last PDF
page of that build, and `pdf`, where the citation already names the PDF page. Every section
here was written citing PDF pages, so every deck currently in the table is `pdf`.

Grumberg's and Mitchell's decks were delivered as PowerPoint. `pptx_to_pdf.py` converts them,
and `slide_popups.py` then treats the results like any other PDF deck. Run it after replacing
a deck:

```bash
sudo apt install libreoffice-impress   # once
python3 pptx_to_pdf.py                 # converts anything whose PDF is missing or stale
```

It exports hidden slides on purpose. LibreOffice drops them by default, which shifts every
page after the first hidden slide, and two of these six decks contain hidden slides, so the
default export would have pointed 35 citations at the wrong picture. The script checks page
count against slide count for every deck and fails if they disagree.

**Equations need a workaround.** LibreOffice reads the OMML branch of a PowerPoint equation and
renders almost none of it, which leaves a slide whose arrows and labels point at blank space.
PowerPoint saves a picture of each equation beside the markup, so `flatten_omml.py` rewrites the
deck to keep only that picture, and `pptx_to_pdf.py` does this automatically before converting.
That fixes most decks outright.

Two failure modes survive it, and both are worth recognising:

```bash
# were the equation pictures actually saved? Target="NULL" means no.
python3 - <<'EOF'
import zipfile, re, glob
for f in sorted(glob.glob('../marktoberdorf/slides/*/*.pptx')):
    z = zipfile.ZipFile(f)
    null = sum(1 for n in z.namelist() if re.match(r'ppt/slides/_rels/', n)
               for m in re.finditer(r'Type="[^"]*/image"[^>]*Target="([^"]+)"',
                                    z.read(n).decode('utf8')) if m.group(1) == 'NULL')
    print(f'{null:4d} dangling  {f}')
EOF
```

A deck with dangling references never stored its equation pictures, so nothing can recover them.
Separately, a deck may hang the picture on a placeholder shape, whose image fill LibreOffice
ignores even after flattening. In both cases the honest move is to leave the deck out of `DECKS`
so the affected sections keep plain labels. Always render one equation-heavy page and look at it
before trusting a converted deck.

A pill may name one deck of a multi-lecture series, as in
`<span class="slide-ref">lecture 2 slide 7</span>`. Map the qualifier in `SECTION_DECKS` with a
`lecture2` or `lecture3` key beside `bare`.

## Credits

Content follows the lectures and the speakers' own decks, in `../marktoberdorf/slides/`.

Marktoberdorf: Jean-Christophe Filliâtre (*The Why and How of Deductive Program
Verification*), Peter Müller (*Automating Separation Logic Proofs with Viper*), Orna Grumberg
(*Constrained Horn Clauses and their Applications*, including joint work with Omer Rappoport
and Yakir Vizel), John C. Mitchell (*Evaluation and Security of AI-Based Systems*), and
Alexander Pretschner (*Integration Testing*, *Scenario-Based Tests for Cyber-Physical
Systems*, joint work with Michael Wolf, Florian Hauer, Nicola Kolb, Tabea Schmidt and Thomas
Hutzelmann), Sukyoung Ryu (*Mechanized Specifications Adopted by Real-World PLs*, four
lectures, joint work with Jihyeok Park and colleagues) and Mike Dodds (*Doing Proof: Today,
Tomorrow, Next Year*).

Jonathan Protzenko (*Linearity, Rust and Verification*, one deck covering both of his
lectures, joint work with Son Ho, Guillaume Boisseau, Aymeric Fromherz and the Aeneas
collaborators), Jasmin Blanchette (*Resolution*, *Superposition*, *Lambda-Superposition*) and
Leonardo de Moura (*Programming and Proving in Lean*, *Software Verification in Lean*, *Proof
Automation and AI*).

Two sections carry no slide pills: 24, because Blanchette's fourth lecture had no deck, and 25,
because de Moura's introductory deck exists only as page images with no text layer.

Slide images © their authors, reproduced with attribution for private study only. This is a
personal study aid, not an official publication of the school.
