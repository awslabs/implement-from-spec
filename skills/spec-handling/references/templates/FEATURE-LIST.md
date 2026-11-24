# Template: `specification/FEATURE-LIST.md`

Write the document with these sections and replace the guidance. Plain words for readers who do not
read code: no item IDs in the running text, no code names where an everyday word exists. It describes
the system as built.

```markdown
# Feature list: <Project name>

What <the system> does, in plain words. It describes the system as built; the formal requirements are
in [SPECIFICATION.md](SPECIFICATION.md).

## 1. What the system is
One paragraph: what it is for, who uses it, what it leaves to other systems.

## 2. <Feature area>
Short bullets: what a user or another system can do, the limits that apply, what happens when a rule is
broken.

## 3. <Feature area>
As above, one numbered section per area, in the order a reader meets them.

## <n>. Access and roles
Who may do what.

## <n+1>. Safety, availability and limits
What protects the data, what the system is sized for, what happens when a part fails.

## <n+2>. Not included and known limitations
What the system does not do, and the limitations its owner has accepted, each in one line.
```
