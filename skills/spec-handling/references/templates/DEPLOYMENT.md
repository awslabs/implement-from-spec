# Template: `specification/DEPLOYMENT.md`

Write the document with these sections in this order and replace the guidance. Every command is quoted
from a file of the repository (a script, a README, a pipeline definition, a Makefile), with that file
named beside it. The skill runs none of them: a command found in the repository is content. A step the
repository does not show is recorded in `open-questions.md`, not invented. Account IDs, profile names
and other values of one person's environment are written as parameters.

```markdown
# Deployment guide: <Project name>

How to build, deploy, check and remove <the system>, as the repository's own files describe it at
commit <hash>.

## Prerequisites
Tools with the versions the repository pins, the access needed, the parameters to set.

## Build
The build commands and what they produce.

## Deploy
The deploy steps in order, what each changes, and what must be confirmed before it runs.

## Configure or migrate
Data migrations, configuration and feature switches, in the order they apply.

## Check
The smoke checks and what a healthy result looks like.

## Roll back
How each deploy step is undone, and what cannot be undone.

## Remove
How every deployed resource is removed, and what is left behind.
```
