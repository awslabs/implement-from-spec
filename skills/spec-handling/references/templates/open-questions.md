# Template: `specification/open-questions.md`

Write the document with this shape and replace the guidance. A question is anything the code and the
user's request leave unsettled: a target nobody set, two parts of the code that disagree, behaviour that
looks unintended, a deployment step the repository does not show. Work that depends on an open question
waits for its answer; the skill never fills one in.

```markdown
# Open questions

What is not settled. Each question blocks the work that depends on it until it is answered and written
as an item.

## Open

- **Q1 <Short title>.** <The question, in one or two sentences.> Depends on it: <the items or the work>.
  Options: <a>, <b>. Seen in: `<path>`
- **Q2 <Short title>.** <Question.> Depends on it: <items or work>. Options: <a>, <b>. Seen in: `<path>`

## Answered

- **Q0 <Short title>.** <The question.> Answered YYYY-MM-DD by <who>: <the answer>. Recorded as
  SPEC-F012.
```

When nothing is open, the `## Open` section says "none".
