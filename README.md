# Marktoberdorf Summer School 2026

Interactive study notes from the Marktoberdorf Summer School, August 2026, built from the
lectures, the speakers' own slide decks and recordings of the talks.

**Read them here: <https://saharramezani.github.io/marktoberdorf2026/>**

The whole thing is one self-contained HTML page. Nothing to install and no server needed:
you can also clone the repository and open `index.html` in any browser.

## What is in it

Thirty sections, grouped by lecture series rather than by day:

- Deductive program verification (Jean-Christophe Filliâtre)
- Separation logic and Viper (Peter Müller)
- Constrained Horn clauses (Orna Grumberg)
- AI systems: evaluation and security (John C. Mitchell)
- Testing cyber-physical systems (Alexander Pretschner)
- Mechanized language semantics (Sukyoung Ryu)
- Verified systems programming in Rust (Jonathan Protzenko)
- Automated theorem proving (Jasmin Blanchette)
- Lean and proof automation (Leonardo de Moura)
- Proof in industry (Mike Dodds)

Every cited slide opens as a picture where it is mentioned, and the page carries quizzes,
steppers and other widgets to work through. You can mark sections as read, highlight
passages and save questions; all of that lives in your own browser and travels through one
JSON export.

## Layout

```
index.html      the tutorial, generated and self-contained
tutorial-src/   the sources it is built from, plus the build and test scripts
marktoberdorf/  the lecturers' slide decks
```

Building it is documented in [tutorial-src/README.md](tutorial-src/README.md).

## Credits

The content follows the lectures and the speakers' own decks. Slide images remain © their
authors and are reproduced with attribution for private study only. Warm thanks to all the
lecturers and to the school organizers.

This is a personal study aid, not an official publication of the school, and any mistake in
it is mine rather than a lecturer's.
