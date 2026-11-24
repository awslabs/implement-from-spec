# Template: the index, `specification/SPECIFICATION.md`

Write the index with these parts in this order and replace the guidance. The `Format:` line stands on a
line of its own, exactly as shown: `spec-layout.py` recognises the layout by it. Every item of the item
files is named here, and no other ID is (format.md, section 2).

```markdown
# Specification: <Project name>

Version 0.1.0, YYYY-MM-DD, owner <name or team>. Status: baseline derived from the code at commit
<hash>; items are as built until the owner confirms them.
Format: implement-from-spec specification format 1.

This specification states what <the system> must do (functional, `SPEC-Fnnn`) and how well
(non-functional, `SPEC-NFnnn`). Every item is a requirement with an acceptance check. Code and tests
name the item IDs they implement or verify.

Terms: **<term>** is <meaning>; **<term>** is <meaning>.

## Documents

- [Architecture](ARCHITECTURE.md): how the system is built
- [Deployment](DEPLOYMENT.md): how it is built, deployed, checked and removed
- [Feature list](FEATURE-LIST.md): what it does, in plain words
- [Test cases](TEST-CASES.md): which scenarios the tests cover
- [Traceability](TRACEABILITY.md): which tests and code cite each item (generated)
- [Open questions](open-questions.md): what is not settled

## Functional items

- SPEC-F001 <Title>: [functional/<area>.md](functional/<area>.md)
- SPEC-F002 <Title>: [functional/<area>.md](functional/<area>.md)

## Non-functional items

- SPEC-NF001 <Title>: [non-functional/<area>.md](non-functional/<area>.md)

## Conventions

- An ID names one requirement for the life of the project: never reused, never renumbered. A reversed
  item is struck through with its reason and date, not removed
- A change that adds, changes or strikes a requirement changes its item in the same change as the code
- A question the work depends on is recorded in `open-questions.md` and blocks that work until it is
  answered and written as an item
- `TRACEABILITY.md` is generated; it is never edited by hand
```
