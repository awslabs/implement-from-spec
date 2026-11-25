# Template: `specification/ARCHITECTURE.md`

Write the document with these sections in this order and replace the guidance. It describes the system
as built, from the code and configuration read in this session, and names the items a section realises.
One diagram at most, as an image file beside the document; none is required.

```markdown
# Architecture: <Project name>

How <the system> is built: its components, data, data flows, and how it stays correct and secure.
Requirements: [SPECIFICATION.md](SPECIFICATION.md). Status: describes the system as built at commit
<hash> (with uncommitted changes to <paths, or a count>, if the tree was not clean).

## 1. Overview
Three to five sentences: the source of truth, the ways in, the ways out.

## 2. Components
One entry per component (service, function, job, queue, store, gateway): what it does, what it is built
with, and the source directory that holds it.

## 3. Data storage
Each store, what it holds, its keys or schema in words, who writes and who reads it.

## 4. How data flows
One subsection per main flow, as numbered steps from the trigger to the result, naming each component
and the items the flow realises.

## 5. How correctness is protected
The invariants the code enforces and where: transactions, locks, idempotency, ordering, validation at
boundaries.

## 6. Security
Access (who may call what, and how it is enforced), secrets, encryption, network exposure, audit.

## 7. Operations and deployment
What is observed (logs, metrics, alarms), what is scheduled, how the system is deployed; details are in
[DEPLOYMENT.md](DEPLOYMENT.md).
```
