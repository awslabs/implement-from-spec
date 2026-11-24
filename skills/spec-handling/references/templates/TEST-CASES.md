# Template: `specification/TEST-CASES.md`

Write the document with these sections in this order and replace the guidance. It lists groups of test
cases, not individual tests: the item-by-item mapping is the generated `TRACEABILITY.md`. A scenario no
test covers is listed under "Not covered", never described as covered.

```markdown
# Test cases: <Project name>

Which scenarios the tests cover and where they live. Requirements: [SPECIFICATION.md](SPECIFICATION.md);
the mapping of tests to items: [TRACEABILITY.md](TRACEABILITY.md) (generated).

## How the system is tested
The levels (unit, integration, infrastructure plan tests, tests against a deployed environment), the
directory of each, what each runs against, and the command that runs it, quoted from the repository.

## Functional test groups

### <Area>
The scenarios covered, in two to five sentences, and the items they prove (SPEC-F001, SPEC-F002).

- `<test file>`
- `<test file>`

## Non-functional test groups

### <Area>
As above, for the constraints (SPEC-NF001).

- `<test file>`

## Not covered
Each scenario or item no test covers, in one line, with the reason when it is known.
```
