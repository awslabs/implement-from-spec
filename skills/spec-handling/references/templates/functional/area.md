# Template: a functional area file, `specification/functional/<area>.md`

One file per area of behaviour (accounts, payments, reports). Group items under plain headings; no
heading carries an item ID. Each item follows format.md, section 3: the ID and title in bold, one
requirement with MUST and its exact values, `*Acceptance:*`, and `*Source:*` naming the paths that
evidence it (every baseline item; an item written for a request may name the paths the plan's tasks
create, since sync never adds one later).

```markdown
# Functional requirements: <area>

What <the system> does for <area>. Design: [ARCHITECTURE.md](../ARCHITECTURE.md), section <n>.

## <Group>

- **SPEC-F001 <Title>.** <Who or what> MUST <one observable behaviour, with its exact values: names,
  limits, status codes, units>. *Acceptance:* <what a test or a check observes>.
  *Source:* `<path>`, `<path>`
- **SPEC-F002 <Title>.** <Requirement>. *Acceptance:* <check>. *Source:* `<path>`

## <Group>

- **SPEC-F003 <Title>.** <Requirement>. *Acceptance:* <check>. *Source:* `<path>`
```

What makes a functional item: a route, command, event, job or rule a caller or an operator can observe;
a state and its allowed transitions; a validation and what it returns; a data invariant the code
enforces. Not an item: a helper function, a file layout, a library choice (those belong to the
architecture).
