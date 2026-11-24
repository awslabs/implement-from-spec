# Template: a non-functional area file, `specification/non-functional/<area>.md`

One file per kind of constraint (security, reliability, performance, observability, cost, delivery).
Same item form as the functional files. In a baseline, write a non-functional item only where code or
configuration evidences it, and with the value found there; a target nobody set is an open question,
never an item.

```markdown
# Non-functional requirements: <area>

The constraints <the system> keeps for <area>.

- **SPEC-NF001 <Title>.** <The system or a named part> MUST <one constraint with its exact value: the
  authentication it requires, the encryption it sets, the timeout, the limit, the alarm threshold>.
  *Acceptance:* <the configuration inspected, the test or the report that shows it>.
  *Source:* `<path>`
- **SPEC-NF002 <Title>.** <Constraint>. *Acceptance:* <check>. *Source:* `<path>`
```

Where to look for evidence: authentication and authorization (route or method settings, policies, role
definitions); encryption in transit and at rest; network exposure; timeouts, retries, limits and
quotas; durability, backups and recovery settings; logs, metrics, traces and alarms; infrastructure as
code and how it deploys; test coverage rules; cost guards (budgets, capacity floors and ceilings).
