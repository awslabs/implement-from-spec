# Principles and architecture smells: shared review dimensions

The language-neutral definitions and diff-level detection signals for design principles (PRN), architecture
smells (ARC) and code-smell families (SML). Every stack review file links here and states the stack-specific
form instead of restating a definition. Precedence: the project's rules (CLAUDE.md, AGENTS.md), its
specification and the approved plan override everything below; a deviation the project prescribes is not a
finding.

## Contents

- How to apply
- 1. Principles (PRN-01 to PRN-16)
- 2. Architecture smells (ARC-01 to ARC-21)
- 3. Code-smell families (SML-01 to SML-14)
- 4. Writing the stack-specific form
- 5. Out of scope / handled elsewhere
- Sources

## How to apply

**Reviewer groups.** Every entry here belongs to `implement-from-spec:code-reviewer`, inside the stack file's
design group (Java "Design", "Extensibility" and "Maintainability"; Python "Types and design"; the IaC files'
module, stack or construct design groups). The security reviewers (`implement-from-spec:iac-security-reviewer`,
`implement-from-spec:reviewing-terraform-security`) own none of it. When a smell also exposes data (a vendor
error with credentials leaking through ARC-01, a shared table readable by a module that should not see it
under ARC-12), security depth belongs to the owner the stack review file names: hand it over in one line
only when that reviewer was dispatched for the affected files; otherwise (Java and Python application code,
where the stack files make the code reviewer the security reviewer) the code reviewer investigates it
fully. One finding carries both the design cause and the security consequence.

**What to report.**
- Report what the change introduces or makes worse. Smells in unchanged code are reported `(pre-existing)`
  as `skills/code-reviewer/SKILL.md` describes, so the orchestrator can defer them
- A detection signal is a prompt to look, not a finding. The finding names a demonstrated violation, a
  concrete behavioural risk or an identifiable change cost the diff introduces or worsens ("adding a refund
  type now needs edits in `api/`, `service/` and `report/`"), and the "Fix" names the refactoring (the
  catalog names below, such as Move Function or Introduce Parameter Object) and where it lands. Never
  report a principle name alone
- Claims about the wider system ("widely used", "most modules", "changes often", a cycle) need evidence
  beyond the diff: name the changed dependency edge, the importers or callers found with a search, the full
  path of a cycle and its kind (import or build, provisioning, runtime call), and the `git log` entries for
  a churn claim. Without that evidence, omit the claim; keep the finding anchored to the changed line
- One root cause, one finding. Several entries often match the same code (PRN-03, PRN-13, ARC-13 and
  SML-11; PRN-04 and SML-06; ARC-04 and SML-02; ARC-07 and SML-12): use the most specific observable entry
  as the ID, name the others as rationale, and do not raise severity because several match. ARC entries
  cover dependency, ownership and deployment relationships between components; SML entries cover structure
  inside one component
- Put the shared ID after the group in the finding line, for example
  `[Major] src/orders/api.py:42 - Design (ARC-02) - the handler queries the orders table directly ...`
- Numeric thresholds (lines per function, parameters, fan-out) come from the project's rules or the stack
  file, never from this file
- Mark a finding `unsure` when it depends on intent the diff does not show (whether a second
  implementation is planned, whether two copies encode the same rule), and say what would settle it.
  A finding that depends on deployed state (what a stack exports, who imports it, what a live resource
  holds) is `unsure, needs runtime verification`: a diff cannot prove deployed state
- Any refactoring an IaC finding proposes (extracting a module, stack or construct, moving resources
  between them) must preserve resource identity or include the migration: a `moved` block in Terraform,
  unchanged logical IDs (a `Default` construct ID) or a `cdk refactor` deployed on its own in CDK, a
  retained resource imported into its new stack in CloudFormation, then the plan or change set checked. A
  remedy that would replace a stateful resource is itself a Blocker under the IaC `review.md` Blocker
  classes

**Principles pull against each other.** DRY against decoupling (PRN-01 and PRN-02 against ARC-12), YAGNI
against open-closed and dependency inversion (PRN-09 against PRN-04 and PRN-07), Law of Demeter against
Middle Man (PRN-10 against SML-10), small functions against simplicity (SML-01 against PRN-08). An
abstraction is justified by a present benefit the reviewer can name: it enforces an invariant, hides a
volatile detail, restricts a capability, gives a coherent concept one owner and name, is reused now, or is
a boundary the project's rules name (a port, an adapter layer) or a test seam they require. Without such a
benefit prefer the simpler change; the number of implementations alone settles nothing. When the project's
rules and the plan do not settle a tension, do not report the preference: report only a concrete cost,
marked `unsure`, at the severity that cost earns.

**Severity classes** (the plugin's four; the stack file's classes win where they differ). Severity follows
the consequence, never the location alone: crossing a package boundary or publishing an interface raises
severity only when the consequence is shown.
- **Blocker**: the smell breaks something stated as mandatory: an architecture invariant in CLAUDE.md, the
  specification or the approved plan worded as a rule (a layer rule, a dependency direction, data
  ownership), a published interface contract another component reads, or a documented failure turned into a
  silent success (PRN-14). Guidance the project words as a preference is at most Major. Without such a
  link a principle finding is never a Blocker
- **Major**: new structural debt that is expensive to undo after merge or that hides defects: a new
  dependency cycle, a layer skip, a vendor or persistence type in a domain or public interface, a business
  rule duplicated into a second place, a second writer to another module's records, a substitutability
  break, growth of a god component in shared code
- **Minor**: local design debt fixable inside the changed files (a long function, a long parameter list, a
  data clump, a temporary field, a middle man)
- **Nit**: naming, comment and shape polish with no structural effect

## 1. Principles

### PRN-01 DRY: one authoritative home for each piece of knowledge
- **Look for:** the same business rule, validation, constant, mapping table, schema or retry policy written
  out in two or more places in the change, or the change copying logic a shared module already owns; two
  definitions of one wire format (a model and a hand-built dict for the same payload)
- **Why it matters:** the copies drift; the next rule change fixes one and leaves the others wrong, which
  is a silent wrong result rather than a crash
- **Instead:** Extract Function or Extract Class into the module that owns the concept and call it from
  every site; derive secondary representations (schemas, docs, clients) from the one source
- **Severity:** Major when a business rule or contract is duplicated; Minor for duplicated mechanics
  inside one module. Not a finding when the copies have different owners or change authority: the same
  check at two trust boundaries (client and server, gateway and service), or one concept modelled
  separately in two bounded contexts (PRN-02)
- **Source:** https://media.pragprog.com/titles/tpp20/dry.pdf — "Every piece of knowledge must have a
  single, unambiguous, authoritative representation within a system." Also
  https://www.informit.com/articles/article.aspx?p=2952392&seqNum=2 — "If you need to change the
  duplicated code, you have to find and catch each duplication"

### PRN-02 Rule of three and acceptable duplication
- **Look for:** the opposite failure: a new shared helper or base class extracted from two call sites that
  only look alike, a helper that grew a mode parameter or flag so both callers fit, test code compressed
  into loops and shared fixtures until a failing test cannot be read on its own, a "common" module
  linking two bounded contexts (two services, two domains) that the project keeps separate, and a
  falsely uniform interface whose callers branch on the implementation or pass mode flags to get the
  semantics they need
- **Why it matters:** coincidental similarity is not shared knowledge; the wrong abstraction couples
  callers that change for different reasons and is harder to undo than the duplication was
- **Instead:** unify only copies shown to encode the same rule; the rule of three is a heuristic, and a
  third coincidental copy is still not shared knowledge. In tests prefer descriptive, self-contained cases
  (helpers for building values are fine); across bounded contexts duplicate the model and translate at
  the boundary
- **Severity:** Minor; Major when the forced abstraction couples modules the project's rules keep apart
- **Source:** https://media.pragprog.com/titles/tpp20/dry.pdf — "That’s a coincidence, not a
  duplication." https://en.wikipedia.org/wiki/Rule_of_three_(computer_programming), paraphrased: a
  second copy of similar code can stay, and the third copy is the time to extract it (secondary source;
  the rule is Don Roberts's, popularised by Fowler's Refactoring).
  https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction — "duplication is far cheaper than the wrong
  abstraction". https://testing.googleblog.com/2019/12/testing-on-toilet-tests-too-dry-make.html — "When
  writing unit tests and faced with a choice between the DRY and DAMP principles, lean more heavily toward
  DAMP." https://martinfowler.com/bliki/BoundedContext.html — "Different contexts may have completely
  different models of common concepts"

### PRN-03 Single Responsibility (SRP)
- **Look for:** one class or module in the change edited for unrelated reasons (persistence and pricing,
  HTTP parsing and business rules, rendering and calculation); one function that parses input, applies
  business rules, writes output and formats a report inline. Names joined with "And" or ending in
  "Manager", "Helper", "Util" are inspection hints only. An orchestrating function that reads, calls a
  decision and writes is the legitimate shape, not a finding
- **Why it matters:** code that changes for different reasons breaks together; a change requested by one
  stakeholder risks another's behaviour
- **Instead:** split along the reasons to change (Extract Class, Split Phase), so each piece has one owner
  and one test focus
- **Severity:** Minor; Major when the mix crosses a layer the project defines (see ARC-02, ARC-13)
- **Source:** https://blog.cleancoder.com/uncle-bob/2014/05/08/SingleReponsibilityPrinciple.html — "each
  software module should have one and only one reason to change".
  https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html — "Gather together the things that
  change for the same reasons. Separate things that change for different reasons"

### PRN-04 Open-Closed (OCP)
- **Look for:** a new variant (payment type, event type, region, provider) on a known extension axis
  that forces edits to unrelated or omission-prone places: the same `if`/`switch` chain changed in several
  places at once, a non-exhaustive chain whose default branch silently absorbs the new case, core code
  edited to accommodate a detail that could have been plugged in
- **Why it matters:** every new variant touches code that already worked and needs re-testing, and a missed
  branch is a silent wrong result
- **Instead:** a dispatch table, polymorphism or a registered handler where it shrinks the demonstrated
  change burden (Replace Conditional with Polymorphism), only once real variants exist (PRN-09). A closed
  set of variants matched exhaustively, with the compiler or type checker flagging a missing case, is
  acceptable and not a finding; plug-in mechanisms also need registration edits and tests
- **Severity:** Minor; Major when a missed branch would pass silently (see SML-06)
- **Source:** https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html — "A Module should be
  open for extension but closed for modification." and "Do we want to see if statement scattered through
  our code to deal with all the little details?"

### PRN-05 Liskov Substitution (LSP)
- **Look for:** an implementation or subclass that, against the base type's documented contract,
  strengthens a precondition (rejects inputs the base accepts), weakens a postcondition (returns less, or
  errors the contract excludes), breaks an invariant, allows state changes the base forbids (a mutable
  subtype of an immutable type), or adds side effects the contract excludes; callers that check the
  concrete type (`instanceof`, `isinstance`, a `kind` field) to work around one implementation. Not
  findings: an optional operation the interface documents as possibly unsupported, a covariant return
  type, and documented dispatch over a closed set of variants
- **Why it matters:** code written against the interface breaks when handed this implementation, and
  type checks spread to every caller
- **Instead:** honour the base contract fully or stop claiming the type (Replace Subclass with Delegate,
  a separate interface for the narrower capability). The finding names the broken promise and the client
  call that fails
- **Severity:** Major; Blocker when the broken substitution makes a specified path fail
- **Source:** https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html — "A program that uses
  an interface must not be confused by an implementation of that interface." and "If an implementation
  confuses the user of the base type, then if/switch statements will proliferate." Sonar RSPEC S2638
  "Method overrides should not change contracts". https://en.wikipedia.org/wiki/Liskov_substitution_principle
  (secondary, summarising Liskov and Wing 1994) — "Preconditions cannot be strengthened in the subtype",
  "Postconditions cannot be weakened in the subtype", and the history constraint

### PRN-06 Interface Segregation (ISP)
- **Look for:** a new or widened interface, protocol, port or client wrapper whose consumers each use a
  small subset; implementations that stub most methods; a module importing a large facade for one call; a
  test double forced to implement methods the test never touches
- **Why it matters:** consumers recompile, redeploy or re-test for changes to operations they never use,
  and fat interfaces invite stub implementations (PRN-05)
- **Instead:** split the interface by client role (a reader and a writer port, a narrow protocol per
  consumer)
- **Severity:** Minor; Major when a public or cross-module interface introduced by the change already
  forces stub implementations or unrelated consumers to change
- **Source:** https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html — "Keep interfaces small
  so that users don’t end up depending on things they don’t need"

### PRN-07 Dependency Inversion (DIP)
- **Look for:** domain or policy code whose types or calls name a volatile implementation detail (an SDK
  client or its request types, a database driver, an HTTP library, the filesystem), whether it constructs
  the dependency or receives it: injecting a concrete vendor client still leaves the policy depending on
  the vendor; business rules that import a framework or vendor module; volatile dependencies created inside
  the code that uses them, so tests must patch globals. Not findings: composition roots, the adapters
  themselves, and stable local values or helpers constructed in place
- **Why it matters:** high-level policy becomes hostage to low-level detail; swapping the store, the
  vendor or the transport means editing business code, and testing the policy needs that detail
- **Instead:** define a contract owned by the policy that needs it, implement it in the adapter layer so
  the detail conforms to the contract; dependency injection (constructor or parameter) is the usual way
  to wire it, not the principle itself; keep composition at the edge
- **Severity:** Major when it crosses an architectural boundary the project names; Minor inside one layer
- **Source:** https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html — "Depend in the
  direction of abstraction. High level modules should not depend upon low level details".
  https://martinfowler.com/articles/injection.html — "ensure that the configuration of services is
  separated from their use"

### PRN-08 KISS: the simplest design that passes
- **Look for:** layers of indirection, generic frameworks, metaprogramming, reflection or configuration
  engines where a direct call or a plain function would do; deep nesting and boolean-heavy conditions; a
  design pattern applied with one participant; cognitive complexity rising in a function the change
  touches
- **Why it matters:** every extra element must be read, tested and maintained, and complexity hides bugs
  from the reviewer and the tests
- **Instead:** remove what does not serve passing tests, revealing intention or removing duplication
  (Inline Function, Inline Class, Collapse Hierarchy)
- **Severity:** Minor; Major when the reviewer finds a defect or an untested specified path inside the
  added complexity (report that defect under its own group as well)
- **Source:** https://en.wikipedia.org/wiki/KISS_principle, paraphrased: a design aims to stay as simple
  as the problem allows (secondary source for the definition). Related guidance, not the origin of KISS:
  https://martinfowler.com/bliki/BeckDesignRules.html — "Passes the tests / Reveals intention / No
  duplication / Fewest elements" and "anything that doesn't serve the three prior rules should be
  removed". Sonar RSPEC S3776 "Cognitive Complexity of functions should not be too high"

### PRN-09 YAGNI
- **Look for:** code for a variant, option, extension point, parameter, plugin hook or configuration switch
  that no specification item or plan scope item asks for; an abstract base or interface with one
  implementation added "for later"; feature flags with one value; unused parameters
- **Why it matters:** presumptive features cost building, carrying and later removal, and are usually
  wrong when the real need arrives; they also add behaviour nothing verifies
- **Instead:** delete it and build it when an item asks; refactoring that makes the code easier to change
  is not a YAGNI violation
- **Severity:** Minor; Major when it adds unspecified behaviour (it is then also a specification-fidelity
  finding)
- **Source:** https://martinfowler.com/bliki/Yagni.html — "Yagni only applies to capabilities built into the
  software to support a presumptive feature, it does not apply to effort to make the software easier to
  modify"

### PRN-10 Law of Demeter
- **Look for:** call chains that navigate other objects' private structure (`a.getB().getC().doX()` where
  B and C are the collaborator's internals); a function receiving a large object only to dig one value out
  of it; new code that depends on how a collaborator stores its parts. Not findings: navigation of a
  published, immutable data schema or DTO (`order["customer"]["address"]["zip"]` on a documented payload),
  fluent builders and query DSLs, including those whose stages return different builder types
- **Why it matters:** the caller couples to the whole navigation path, so any change to an intermediate
  relationship breaks it
- **Instead:** ask the nearest collaborator for what you need (Hide Delegate), or move the behaviour to the
  object that has the data (Move Function). Pass a scalar when the container is incidental to the
  operation, and the whole object when its fields together form the operation's contract (Preserve Whole
  Object, SML-03). Do not answer every chain with a delegating method (SML-10)
- **Severity:** Minor; Major when the chain crosses a module boundary into another module's internals
  (ARC-17)
- **Source:** https://www.ccs.neu.edu/home/lieber/LoD.html — "Only talk to your friends" (the page's stated motto)
  https://www.informit.com/articles/article.aspx?p=2952392&seqNum=17 — "Navigating this way means the
  client is coupled to the structure of the navigation"

### PRN-11 Composition over inheritance
- **Look for:** a new subclass created to reuse a helper method; inheritance across module boundaries; a
  hierarchy deepened by the change; a subclass reaching into protected state of its parent; a base class
  whose behaviour varies by subclass flags
- **Why it matters:** subclasses depend on their parent's internals, so a parent change breaks children in
  other modules; deep trees are hard to follow
- **Instead:** hold a collaborator and delegate (Replace Subclass with Delegate, Replace Superclass with
  Delegate); keep inheritance for true is-a relationships whose base contract the child fully honours
  (PRN-05)
- **Severity:** Minor; Major when a subclass in another module or package depends on its parent's
  protected state or non-contract behaviour
- **Source:** https://en.wikipedia.org/wiki/Composition_over_inheritance, paraphrased: give a class its
  behaviour through objects it holds (has-a) rather than through a parent it extends (is-a) (secondary
  source).
  https://www.informit.com/articles/article.aspx?p=2952392&seqNum=19 — "Subclasses are always going to know
  more about their parents than their parents would like them to know." Sonar RSPEC S110 "Inheritance tree
  of classes should not be too deep"

### PRN-12 High cohesion, low coupling
- **Look for:** a change that needs coordinated edits in modules that should be independent; a module
  importing many others for one feature (high fan-out); a module whose functions share no data or
  purpose; a helper placed in the module it was convenient to edit rather than the one that owns its data
- **Why it matters:** coupling is the ripple of change: if changing one module requires changing another,
  every future change pays for both
- **Instead:** put things that change together in one place (Move Function, Move Field); narrow the
  surface between modules to a few explicit calls or messages
- **Severity:** Minor; Major for new coupling between top-level modules or services that the change
  shows (coordinated edits it needed, a new dependency on another module's internals)
- **Source:** https://martinfowler.com/ieeeSoftware/coupling.pdf — "If changing one module in a program
  requires changing another module, then coupling exists"
  https://www.informit.com/articles/article.aspx?p=2952392&seqNum=9 — "separate the code into zones to
  maximize the interaction inside a zone and minimize interaction between zones". Sonar RSPEC S1200
  "Classes should not be coupled to too many other classes"

### PRN-13 Separation of concerns
- **Look for:** one unit mixing concerns the project treats separately: I/O with logic, transport with
  rules, presentation with calculation, retries and logging threaded through domain code, configuration
  parsing inside business functions
- **Why it matters:** each concern can no longer be read, tested or changed in isolation, and a change to
  one silently affects another
- **Instead:** separate the phases (Split Phase: parse, decide, act), keep cross-cutting concerns in
  decorators, middleware or adapters, and keep the logic pure where the language allows
- **Severity:** Minor; Major when a layer or boundary the project defines is mixed (ARC-02, ARC-13)
- **Source:** https://www.cs.utexas.edu/users/EWD/transcriptions/EWD04xx/EWD447.html — "study in depth an
  aspect of one's subject matter in isolation for the sake of its own consistency".
  https://martinfowler.com/bliki/PresentationDomainDataLayering.html — "separate it into three broad
  layers: presentation (UI), domain logic (aka business logic), and data access"

### PRN-14 Fail fast
- **Look for:** invalid input, missing configuration or a broken invariant answered with a default, an
  empty result, a logged warning or a retry instead of an error; validation deferred to deep inside a call
  chain; a catch-all that continues; startup that succeeds with required settings absent
- **Why it matters:** the program keeps running after the error and fails later in a place unrelated to
  the cause, or never fails and stores wrong data
- **Instead:** reject each failure at the earliest point it is knowable, within its own failure domain:
  invalid configuration and broken programming invariants at startup or at the point of detection; an
  invalid request by rejecting that request with a typed error, not by stopping unrelated work; an
  expected operational failure (a dependency briefly unavailable) by a bounded retry, fallback or
  isolation the contract documents; an IaC value unknown until deployment at plan or deployment time.
  Checks on untrusted input and production requirements are always-on code, never assertions a runtime
  flag can disable (Java assertions are off by default; Python drops `assert` under `-O`)
- **Severity:** Major; Blocker when a documented error path ends in a success response or stored data
- **Source:** https://martinfowler.com/ieeeSoftware/failFast.pdf — "when a problem occurs, it fails
  immediately and visibly" and "Be sure to implement a global error handler so your overall stability
  doesn't suffer". https://peps.python.org/pep-0020/ — "Errors should never pass silently".
  https://docs.oracle.com/javase/8/docs/technotes/guides/language/assert.html — "By default, assertions are
  disabled at runtime." https://docs.python.org/3/reference/simple_stmts.html — "The current code generator
  emits no code for an assert statement when optimization is requested at compile time"

### PRN-15 Least astonishment
- **Look for:** a function whose name or signature hides what it does: a getter or query that writes,
  caches globally or calls the network; an argument mutated in place; a method that returns `null`, `None`
  or an empty value where siblings raise; inconsistent units, ordering or casing between sibling APIs; a
  default value that changes behaviour silently. A documented mutation or a caching query whose contract
  says so is not a finding
- **Why it matters:** callers act on what the name promises; a surprise becomes a bug in a caller the
  reviewer never sees
- **Instead:** make behaviour match the name and the siblings; separate queries from modifiers (Separate
  Query from Modifier); return new values rather than mutating inputs
- **Severity:** Minor; Major when the surprise is a hidden side effect on shared state or an external system
- **Source:** http://www.catb.org/esr/writings/taoup/html/ch01s06.html — "Rule of Least Surprise: In
  interface design, always do the least surprising thing"
  https://www.informit.com/articles/article.aspx?p=2952392&seqNum=6 — "use Separate Query from Modifier
  (306) to ensure callers don’t need to call code that has side effects"

### PRN-16 Explicit over implicit
- **Look for:** behaviour driven by naming conventions, import side effects, magic environment lookups deep
  in the code, ambient global context, dynamic attribute or reflection tricks, positional booleans at call
  sites (`book(customer, true)`), and implicit type coercions; guessing when input is ambiguous. A
  framework's documented conventions (routing, dependency injection, test discovery) and generated code
  are not findings
- **Why it matters:** readers and tools cannot see the dependency or the decision, so changes break it
  unknowingly
- **Instead:** pass dependencies and settings explicitly, name options (keyword arguments, enums, separate
  functions instead of flag arguments: Remove Flag Argument), reject ambiguous input
- **Severity:** Minor; Major when the implicit mechanism selects behaviour across a module boundary
- **Source:** https://peps.python.org/pep-0020/ — "Explicit is better than implicit." and "In the face of
  ambiguity, refuse the temptation to guess." https://martinfowler.com/bliki/FlagArgument.html — "Rather
  than use a flag argument, I prefer to define separate methods"

## 2. Architecture smells

These describe components, modules, packages, services and stacks rather than single functions. Read the
diff's imports, constructor arguments, module outputs and cross-stack references, not only its bodies.

### ARC-01 Leaking abstraction
- **Look for:** implementation details or vendor types crossing a layer or module boundary: an ORM entity,
  SDK response object, driver exception, HTTP request object, raw database row or provider-specific error
  code in a domain signature, a public API or a module's outputs; callers that must know the backing
  store's pagination, consistency or retry behaviour to use an interface correctly, when the interface
  promised to hide them. The finding needs a boundary that promised to hide the detail. Not findings: a
  provider-specific module or adapter whose purpose is that provider, a documented escape hatch, and
  pagination or consistency semantics the contract states on purpose
- **Why it matters:** every consumer now depends on the vendor or the storage choice, so replacing or
  upgrading it ripples through code that should not care; vendor errors reach users and logs unmapped
- **Instead:** translate at the boundary into the module's own types and errors (an adapter or
  anti-corruption layer); document the unavoidable leaks (latency, eventual consistency) in the interface.
  ARC-01 is the owner exposing too much; a consumer reaching past a sound interface is ARC-17
- **Severity:** Major when the type crosses into domain code or a public contract; Minor inside the adapter
- **Source:** https://www.joelonsoftware.com/2002/11/11/the-law-of-leaky-abstractions/ — "All non-trivial
  abstractions, to some degree, are leaky" (related guidance: some leakage is unavoidable, so the finding
  rests on the broken promise, not on leakage as such)
  https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer — "Use this pattern to
  ensure that dependencies on outside subsystems don't limit an application's design." Leaky Encapsulation,
  https://github.com/tushartushar/smells (data/smells.txt, after Suryanarayana et al. 2014) — an
  abstraction that "exposes" or "leaks" implementation details through its public interface (quoted words
  are the catalog's)

### ARC-02 Broken layering and layer skipping
- **Look for:** where the project or the codebase has a service layer, a presentation or handler layer
  calling persistence or an external client directly, bypassing it; a lower layer importing a higher one
  (repository importing a controller type, domain importing a web framework); new imports that break the
  project's stated dependency direction. A handler that owns its persistence is the normal shape of a
  transaction-script or vertical-slice codebase, not a skip
- **Why it matters:** the layer in the middle exists to insulate the outer layer from changes in the inner
  one; a skip removes that insulation and duplicates the rules the skipped layer enforces
- **Instead:** route the call through the owning layer, or add the missing service operation; for an upward
  reference, invert it with a callback or port (PRN-07)
- **Severity:** Major; Blocker when it violates a layer rule written in the project's rules or plan
- **Source:** https://martinfowler.com/bliki/PresentationDomainDataLayering.html — "presentation depends on
  the domain, which then depends on the data source." https://martinfowler.com/ieeeSoftware/coupling.pdf —
  "the domain model insulates the UI from changes in the database". Strict Layers Violated and Upward
  References between Layers, https://github.com/tushartushar/smells (after Lippert and Roock 2006) — "a
  layer skips the one directly beneath it and accesses a layer further below instead"

### ARC-03 Cyclic dependencies
- **Look for:** a new import, reference or build dependency that closes a loop between modules, packages,
  services, stacks or modules of infrastructure code (A imports B and B now imports A, directly or
  through C); deferred or function-local imports added to dodge an import cycle; two services calling each
  other synchronously. The finding shows the whole path and names the graph: import or build,
  provisioning (stack or module references), or runtime calls
- **Why it matters:** an import or build cycle stops the modules being built and tested separately; a
  provisioning cycle blocks deployment order; a runtime call cycle couples availability and invites
  call loops even when each side deploys alone. Every change can ripple around the loop to its origin
- **Instead:** move the shared piece into a third module both depend on, or invert one edge with an
  interface (PRN-07); an event removes the build edge but not the semantic dependency, so use it only
  where asynchronous semantics fit
- **Severity:** Major; Blocker when the cycle breaks build or deployment order or a dependency rule the
  project states
- **Source:** https://www.designite-tools.com/products-cs — "two or more architecture components depend on
  each other directly or indirectly". http://butunclebob.com/ArticleS.UncleBob.PrinciplesOfOod — "The
  dependency graph of packages must have no cycles." https://martinfowler.com/ieeeSoftware/coupling.pdf —
  "every change breeds other changes that come back to the original package"

### ARC-04 God component
- **Look for:** a module, package, service or stack that the change grows further when it already holds
  most of the system's code or responsibilities; a single "core", "common" or "main" unit that every feature
  edits; a file or stack that keeps absorbing unrelated features. "Already holds most" needs measured
  evidence (file and line counts, the responsibilities listed), not an impression
- **Why it matters:** everything changes in one place, so every change risks every feature, merges
  collide and the unit becomes the deployment and review bottleneck
- **Instead:** split by feature or reason to change (Extract Class, extract module or stack), moving the
  new code into its own unit first; an IaC split preserves resource identity (How to apply)
- **Severity:** Major when the change adds a new responsibility to it; Minor for growth within an existing
  responsibility
- **Source:** https://www.designite-tools.com/products-cs — "a component is excessively large either in the
  terms of LOC or number of classes". Related tool heuristic with a different predicate (dependency count,
  not size): Sonar RSPEC S6539 "Classes should not depend on an excessive number of classes (aka Monster
  Class)"

### ARC-05 Hub-like dependency
- **Look for:** a module that many others depend on and that itself depends on many others, growing in both
  directions in the change: a shared "utils" or "types" package that imports feature code, a central
  registry or configuration module everyone imports and that imports everyone. Count the importers with
  a search before calling a module widely used
- **Why it matters:** a change to the hub or to anything it depends on ripples to all its dependants, so
  it becomes the most fragile and most edited point in the system
- **Instead:** split the hub by consumer, move feature-specific parts back to the features, and keep the
  remaining shared core free of outgoing dependencies on features
- **Severity:** Major when the change adds outgoing dependencies from a widely used module; Minor otherwise
- **Source:** https://arxiv.org/pdf/1904.11755 — "arises when an abstraction has (outgoing and incoming)
  dependencies on a large number of other abstractions"

### ARC-06 Unstable dependency
- **Look for:** a structurally stable module (many dependants, few dependencies: a shared library,
  domain core, base stack or module) gaining a dependency on a structurally unstable one (few dependants,
  many dependencies: typically a feature module). Show both sides' dependants and dependencies from a
  search; recent churn is supporting evidence, not the definition. Floating versions, branch references
  and pre-releases are reproducibility problems for the stack's dependency-pinning checks, not this entry
- **Why it matters:** the stable module now has to change whenever the unstable one does, which spreads
  the volatility to everything that depends on the stable module
- **Instead:** depend in the direction of stability: invert the dependency behind an interface owned by the
  stable side (PRN-07), or move the needed piece into the stable module
- **Severity:** Major; Minor when the dependant itself is unstable
- **Source:** https://www.designite-tools.com/products-cs — "a component depends on other components that
  are less stable than itself". http://butunclebob.com/ArticleS.UncleBob.PrinciplesOfOod — "Depend in the
  direction of stability". Martin's instability metric, as summarised (secondary) at
  https://en.wikipedia.org/wiki/Software_package_metrics — "I = Ce / (Ce + Ca)", efferent over total
  coupling

### ARC-07 Scattered functionality and shotgun surgery across modules
- **Look for:** one concern (authorisation, auditing, tenant scoping, currency rounding, retry policy,
  tagging) implemented again in each module the change touches; one feature change spread as small edits
  across many modules; a module that hosts another concern's fragment next to its own. Deliberate
  defence in depth (authorisation checked at the gateway and again in the service against one policy
  owner) is not scattering; copies of the policy itself are
- **Why it matters:** the concern has no owner, the copies diverge, and the next change misses one site
- **Instead:** give the concern one owning module or cross-cutting mechanism (middleware, decorator,
  shared construct or module) and call it; pull the scattered fragments together (Move Function, Combine
  Functions into Class)
- **Severity:** Major when a security, data-integrity or contract concern is scattered; Minor otherwise
- **Source:** https://www.designite-tools.com/products-cs — "multiple components are responsible for
  realizing the same high-level concern". Garcia et al. 2009, section 5.2,
  https://jgarcia.ics.uci.edu/wp-content/uploads/10.1.1.183.9958.pdf — "this smell scatters a single
  concern across multiple components"

### ARC-08 Feature envy across modules
- **Look for:** a function in one module that encodes another module's domain knowledge (its rules,
  invariants or internal structure) by reading that module's data or getters to compute something; logic
  that would make more sense next to the data it reads. Serialisers, mappers, adapters and reporting
  projections read another representation extensively by design and are not findings unless they depend
  on internals
- **Why it matters:** the logic lives away from the data it depends on, so every change to that data
  ripples into a module that should not know its shape
- **Instead:** move the logic to the module that owns the data (Move Function, Extract Function first if
  only part envies), and ask that module for the result
- **Severity:** Minor; Major when it reaches into another module's internals (ARC-17)
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=9 — "a function in one module
  spends more time communicating with functions or data inside another module than it does within its own
  module"

### ARC-09 Ambiguous interface
- **Look for:** a single generic entry point that takes a type string, command name, untyped map or event
  envelope and dispatches internally (`handle(action, payload)`, `process(event: dict)`, one Lambda or
  endpoint routing many operations by a field) whose operations and payloads are only discoverable by
  reading its dispatch code and are not checked against a schema. An envelope or multiplexed endpoint
  with a complete, published and validated schema per message type is not a finding
- **Why it matters:** callers and tools cannot see which operations exist or what each needs, so contract
  drift goes unnoticed and static analysis cannot trace execution
- **Instead:** one explicit, typed operation per use case, with a typed payload; where an envelope is
  required, a discriminated union with one handler per type
- **Severity:** Major for a new public or cross-module interface; Minor internal to a module
- **Source:** Garcia et al. 2009, section 5.3,
  https://jgarcia.ics.uci.edu/wp-content/uploads/10.1.1.183.9958.pdf —
  "interfaces that offer only a single, general entry-point into a component" and "components use general
  types such as strings or integers to perform dynamic dispatch"

### ARC-10 Dense structure
- **Look for:** a change that adds dependencies between many peer modules at once, so that most modules
  now know most others; no visible layering or grouping in the new import graph. Show the import graph
  of the affected modules (a search per module), not an impression
- **Why it matters:** with dependencies everywhere no module can change, build or be understood alone, and
  every later change has an unpredictable reach
- **Instead:** introduce structure: layers, a small set of shared kernels, events between groups, and
  remove the dependencies the feature does not need
- **Severity:** Major
- **Source:** https://www.designite-tools.com/products-cs — "components have excessive and dense
  dependencies without any particular structure"

### ARC-11 Implicit coupling through shared mutable state
- **Look for:** modules communicating through module-level variables, singletons, class-level mutable
  fields, static caches, environment variables written at runtime, shared temporary files or a shared
  in-memory map, instead of through calls or messages; state set by one module and read by another without
  either declaring it
- **Why it matters:** the dependency is invisible in signatures, so one module's change breaks another
  "at a distance", and concurrent requests or invocations race on the shared value
- **Instead:** pass state explicitly or behind one owning interface (Encapsulate Variable), make shared
  values immutable after startup, and keep per-request state per request
- **Severity:** Major; Blocker when the state is shared across requests, users or invocations and can leak
  or corrupt data
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=5 — "it can be modified from
  anywhere in the code base, and there’s no mechanism to discover which bit of code touched it".
  https://www.informit.com/articles/article.aspx?p=2952392&seqNum=19 — "Modules that whisper to each other
  by the coffee machine need to be separated"

### ARC-12 Implicit coupling through shared database tables
- **Look for:** a module or service depending on the private schema of records, collections, objects or
  keys another module owns; a schema change in one module that another module's queries depend on; a
  second writer to the same records without a shared owner; reporting code joining across another
  module's tables. Ownership is of records, schemas and capabilities, not necessarily a whole database or
  bucket; a queue's producer and consumer sharing it, and access through a published contract, are not
  findings
- **Why it matters:** the schema becomes an unversioned shared contract, so each owner must coordinate
  every change and the modules can block or corrupt each other at runtime
- **Instead:** one owner per store; others go through the owner's interface, an event, or a published
  read model; where sharing is the project's decision, make the shared schema an explicit, versioned
  contract
- **Severity:** Major; Blocker when it violates a data-ownership rule the project states
- **Source:** https://martinfowler.com/bliki/IntegrationDatabase.html — "the database becomes a point of
  coupling between the applications that access it".
  https://microservices.io/patterns/data/shared-database.html — "coordinate schema changes with the
  developers of other services that access the same tables"

### ARC-13 Logic in transport
- **Look for:** business rules, calculations or decisions inside controllers, request handlers, Lambda
  handlers, message listeners, CLI entry points, templates or serialisation code; a handler that cannot be
  tested without the transport's event or request object
- **Why it matters:** the rules cannot be tested or reused without the transport, and a second entry point
  (a queue, a batch job) duplicates them (PRN-01)
- **Instead:** move substantial or reused rules out of the transport into a function the transport calls
  after parsing and validating, and map the result; how many functions the handler calls is the
  project's choice
- **Severity:** Major when a rule is duplicated by, or needed by, a second entry point; Minor otherwise and
  for trivial mapping logic
- **Source:** https://alistair.cockburn.us/hexagonal-architecture/ — "One of the great bugaboos of software
  applications over the years has been infiltration of business logic into the user interface code"

### ARC-14 Anaemic domain model
- **Look for:** domain types that are only fields with getters and setters while services elsewhere
  enforce their invariants; the same invariant checked in several services; setters that let callers put
  an entity into an invalid state
- **Why it matters:** invariants scatter across services, so one caller forgets them; the type promises
  a model it does not enforce
- **Instead:** move the behaviour that guards the data into the type (Move Function, Remove Setting
  Method); keep plain immutable records for results, messages and DTOs, which are the legitimate exception
- **Severity:** Minor; Major when an invariant is enforced in some paths and not others. A transaction-script
  or functional style the codebase follows is not a finding, documented or not; the finding is the
  scattered or missing invariant
- **Source:** https://martinfowler.com/bliki/AnemicDomainModel.html — "little more than bags of getters and
  setters" and "Domain Models aren't always the best tool".
  https://www.informit.com/articles/article.aspx?p=2952392&seqNum=22 — "Data classes are often a sign of
  behavior in the wrong place"

### ARC-15 Configuration sprawl
- **Look for:** settings that vary by environment hard-coded in code (URLs, account or resource
  identifiers, Regions, timeouts, limits, feature switches); the same setting defined in several files or
  formats; new configuration read ad hoc in many places instead of through the project's one settings
  object; defaults that differ between the code and the deployment files. In IaC, account IDs, Regions and
  names in an environment's own declaration (a root module's `tfvars`, a stage's context, a parameter
  file) are configuration in its proper place; the finding is a literal inside a reusable module, construct
  or template
- **Why it matters:** environments drift, a change must be found in every copy, and a wrong value is
  discovered only in production
- **Instead:** one typed settings source loaded and validated at startup (PRN-14), injected where needed;
  environment values from the deployment, not the code
- **Severity:** Minor; Major for an environment-specific identifier or endpoint hard-coded in code
- **Source:** https://12factor.net/config — "strict separation of config from code" and "a tendency for
  config files to be scattered about in different places and different formats". Sonar RSPEC S1075 "URIs
  should not be hardcoded", S109 "Magic numbers should not be used"

### ARC-16 Connector envy
- **Look for:** business components implementing their own communication plumbing: hand-rolled retries,
  backoff, serialisation, routing, connection handling or protocol details next to domain logic, often
  duplicated per component
- **Why it matters:** interaction concerns tangle with business concerns, each copy handles failure
  differently, and changing the transport means editing every component
- **Instead:** delegate interaction to one client, adapter or connector (with the project's retry and
  timeout policy) and keep components calling it; the use case keeps the decisions only it can make, such
  as its idempotency key and whether an operation is safe to retry
- **Severity:** Major when retry or failure handling is duplicated; Minor otherwise
- **Source:** https://github.com/tushartushar/smells (data/smells.txt, after Garcia et al. 2009, section
  5.1) — "components encompass extensive interaction-related functionality that should be delegated to a
  connector"

### ARC-17 Module API bypassed
- **Look for:** imports of another module's internal, private or implementation packages (`_internal`,
  `impl`, underscore-prefixed names, non-exported paths), reflection or monkey-patching to reach hidden
  members, or reading another stack's or module's resources by name instead of its declared outputs. A
  name-based lookup the owner documents as its contract (a published parameter path, a named resource the
  owner promises to keep) is not a bypass; replacing it with a CloudFormation export adds its own
  lifecycle coupling, because an imported export cannot be changed or deleted
- **Why it matters:** the client silently extends the module's public interface, so the owner can no
  longer change its internals without breaking unknown callers
- **Instead:** use the published interface; when it lacks the operation, add it to the owning module in
  the same change
- **Severity:** Major
- **Source:** Subsystem-API Bypassed, https://github.com/tushartushar/smells (after Lippert and Roock
  2006) — "Bypassing the subsystem-API and directly accessing the internal implementation of the
  component". Sonar RSPEC S3011 "Reflection should not be used to increase accessibility of classes,
  methods, or fields".
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html — "After
  another stack imports an output value, you can't delete the stack that is exporting the output value or
  modify the exported output value"

### ARC-18 Extraneous adjacent connector
- **Look for:** two components linked by two kinds of connector for the same interaction (a direct call
  and an event, a queue and a shared table, an API call and a file drop), often added as a shortcut beside
  an existing path, where both carry overlapping authoritative effects. Not findings: separate connectors
  for commands and for notifications, and a transactional outbox, which writes storage and then relays
  to messaging precisely to make one interaction reliable
- **Why it matters:** the two paths have different ordering, failure and retry semantics, so behaviour
  depends on which path ran, and replacing either component means changing both
- **Instead:** pick one connector per interaction and remove the shortcut; if both are needed, make one
  the source of truth, reconcile the other, and document why
- **Severity:** Major when the two paths can deliver conflicting results; Minor otherwise
- **Source:** Garcia et al. 2009, section 5.4,
  https://jgarcia.ics.uci.edu/wp-content/uploads/10.1.1.183.9958.pdf — "occurs when two connectors of
  different types are used to link a pair of components" and "the beneficial effects of each individual
  connector may cancel each other out"

### ARC-19 Temporal coupling and hidden lifecycle protocols
- **Look for:** a changed API that only works if callers invoke `configure`, `initialize`, `open` or
  `commit` in an undocumented order; an object usable in a half-initialised state; one module setting
  state another assumes already exists; deployment steps that rely on declaration order or sleeps rather
  than a declared dependency or readiness check
- **Why it matters:** each operation is valid alone and fails when reordered, retried or run
  concurrently, and the required protocol is invisible to callers and to deployment tools
- **Instead:** require what the object needs at construction (or from a factory that returns it ready),
  give a multi-step protocol one operation that owns the sequence, and in IaC declare genuine
  dependencies and readiness explicitly
- **Severity:** Minor for local protocol complexity; Major when a reachable caller or deployment order can
  violate the sequence; Blocker when the diff shows a specified path or the deployment failing
- **Source:** https://blog.ploeh.dk/2011/05/24/DesignSmellTemporalCoupling/ — "an implicit relationship
  between two, or more, members of a class requiring clients to invoke one member before the other"

### ARC-20 Incompatible boundary evolution and lockstep deployment
- **Look for:** a removed or renamed API field, event field, module input or output, or stack output that
  an existing consumer reads; tightened accepted values, or changed units, meaning or defaults, with no
  migration path; one change editing two independently deployed components so that neither works with
  the other's previous version (both must release together)
- **Why it matters:** each release is valid alone and the system fails during staged rollout, mixed
  versions or rollback, and lockstep releases bring the cost of distribution without its independence
- **Instead:** keep the old shape working while consumers move (expand, migrate, contract), make readers
  tolerant of additions, and version a contract only as a last resort; find the known consumers with a
  search and state the deployment order. Components that always change together may belong together
- **Severity:** Major for a demonstrated incompatible change without migration; Blocker when it breaks a
  published contract or an export still imported (the IaC `review.md` Blocker classes). Whether a deployed
  consumer still reads the old shape is `unsure, needs runtime verification`
- **Source:** https://martinfowler.com/bliki/ParallelChange.html — "a pattern to implement
  backward-incompatible changes to an interface in a safe manner, by breaking the change into three
  distinct phases: expand, migrate, and contract". https://martinfowler.com/articles/microservices.html —
  "if you find yourself repeatedly changing two services together, that's a sign that they should be
  merged" and "only use versioning as a last resort"

### ARC-21 Cross-system consistency without a protocol
- **Look for:** one logical operation that writes a database and publishes an event, updates two
  independently committed stores, or calls an external side effect before the local commit, with no
  durable retry, reconciliation or compensation when the process fails between the steps
- **Why it matters:** each step succeeds locally while the whole operation loses an event, duplicates an
  effect or leaves records permanently inconsistent
- **Instead:** name the consistency boundary and use a transaction that spans it, a transactional outbox,
  an idempotent workflow or a compensating step; make partial failure and recovery part of the contract
- **Severity:** Major for a partial-failure gap the diff shows; Blocker when it violates an atomicity or
  data-integrity guarantee the specification states
- **Source:** https://microservices.io/patterns/data/transactional-outbox.html — "How to atomically update
  the database and send messages to a message broker?" and "messages are guaranteed to be sent if and only
  if the database transaction commits"

## 3. Code-smell families

Fowler and Beck's catalog, cited from the second edition's chapter 3 as published by InformIT
(`https://www.informit.com/articles/article.aspx?p=2952392&seqNum=<n>`). A smell is a prompt to look, not a
verdict; the fix is the named refactoring from https://refactoring.com/catalog/.

### SML-01 Long function
- **Look for:** a function the change makes longer than the project's or stack file's threshold, or one
  that mixes levels of abstraction; blocks preceded by explanatory comments; nested loops with inline
  conditions
- **Why it matters:** long functions are harder to read, test and reuse, and they hide the steps that
  should have names
- **Instead:** Extract Function for a step that has a name of its own, named for intent; Decompose
  Conditional. Keeping a cohesive sequence together with a better explanation is valid when extraction
  would only fragment it
- **Severity:** Minor; Major when the function mixes I/O and logic in a way the stack file calls out
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=3 — "the longer a function
  is, the more difficult it is to understand". Sonar RSPEC S138 "Functions should not have too many lines
  of code"

### SML-02 Large class or module
- **Look for:** a class or module gaining fields and methods for an unrelated purpose; groups of fields
  with a common prefix (`deposit_amount`, `deposit_currency`); fields used by only some methods
- **Why it matters:** a class doing too much accumulates duplication and becomes everyone's edit point
  (inside one component; a whole module, package, service or stack is ARC-04)
- **Instead:** Extract Class around each field group; Extract Superclass only for a true is-a
- **Severity:** Minor; Major when the class is shared across modules
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=20 — "When a class is trying
  to do too much, it often shows up as too many fields." Sonar RSPEC S1448 "Classes should not have too many
  methods", S1820 "Classes should not have too many fields"

### SML-03 Long parameter list
- **Look for:** a function or constructor gaining parameters past the stack file's threshold; parameters
  always passed together; boolean flag parameters that select behaviour; values pulled out of an object
  only to be passed separately
- **Why it matters:** callers must know the role and position of each parameter, and swapped arguments of
  the same type compile and run wrong
- **Instead:** Introduce Parameter Object, Preserve Whole Object, Remove Flag Argument, Combine Functions
  into Class
- **Severity:** Minor
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=4 — "long parameter lists are
  often confusing in their own right". Sonar RSPEC S107 "Functions, methods and lambdas should not have too
  many parameters"

### SML-04 Primitive obsession
- **Look for:** money as floats, identifiers, emails or phone numbers as plain strings, units implied by
  variable names, status codes as bare strings or integers, range checks (`low < x < high`) repeated at
  call sites, where the diff shows the consequence: a mixed-up identifier or unit, missing semantic
  validation, or the same check scattered across call sites
- **Why it matters:** the type system cannot stop a mixed-up identifier, a wrong unit or an invalid value,
  and the validation is repeated or forgotten
- **Instead:** Replace Primitive with Object: a value type, enum or constrained type that validates once.
  Where the language has no nominal types (Terraform's types are `string`, `number`, `bool` and
  structural collections), a string with a `validation` block, a schema or a typed object variable is the
  equivalent; an ARN as a string with that validation is normal IaC
- **Severity:** Minor; Major for money, identifiers crossing a trust boundary, or closed sets the
  specification enumerates, when the semantics (currency, rounding, allowed values) are not enforced
  elsewhere
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=11 — "calculations that treat
  monetary amounts as plain numbers" and "people call them “stringly typed” variables".
  https://developer.hashicorp.com/terraform/language/expressions/type-constraints — "a primitive type is a
  simple type that isn't made from any other types"

### SML-05 Data clumps
- **Look for:** the same three or four values travelling together through several signatures or appearing
  together as fields in several classes (start and end dates, host and port and timeout, amount and
  currency)
- **Why it matters:** each place re-implements the group's rules, and the missing concept never gets the
  behaviour that belongs to it
- **Instead:** Extract Class for the clump, then Introduce Parameter Object; test: deleting one value makes
  the others meaningless
- **Severity:** Minor
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=10 — "Bunches of data that
  hang around together really ought to find a home together"

### SML-06 Repeated switches on type
- **Look for:** the same `switch`, `match` or `if`/`elif` chain on a type code, kind field or class repeated
  in several places; the change adding a new case to more than one of them
- **Why it matters:** each new variant requires finding and updating every switch, and a missed one is a
  silent wrong result
- **Instead:** Replace Conditional with Polymorphism, or one dispatch table owned by the type. Exhaustive
  matches on a closed (sealed or enumerated) type that the compiler or type checker verifies are
  acceptable, one or several, because a missed case fails the build
- **Severity:** Minor; Major when a copy the change did not update would silently mishandle the new case
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=12 — "whenever you add a
  clause, you have to find all the switches and update them" and "it isn't the simple red flag that it
  often was fifteen years ago"

### SML-07 Speculative generality
- **Look for:** abstract classes, hooks, parameters or plugin points with one user and no present benefit
  (How to apply); code used only by its tests, unless it is a public entry point consumed outside the
  repository; unused parameters "for later"; a lazy element (a function named the same as its body reads,
  a class that is one simple function). A small helper whose name reveals intent is not a lazy element
- **Why it matters:** the machinery must be understood and maintained while delivering nothing, and it is
  usually shaped wrong for the real need (PRN-09)
- **Instead:** Collapse Hierarchy, Inline Function, Inline Class, Remove Dead Code, Change Function
  Declaration to drop unused parameters
- **Severity:** Minor
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=15 — "Speculative generality
  can be spotted when the only users of a function or class are test cases." Sonar RSPEC S1172 "Unused
  function parameters should be removed".
  https://www.informit.com/articles/article.aspx?p=2952392&seqNum=14 — "a function that's named the same as
  its body code reads, or a class that is essentially one simple function"

### SML-08 Temporary field
- **Look for:** a field set only on some code paths or only during one operation, `None`/`null` the rest of
  the time, often used to pass values between helper methods
- **Why it matters:** readers expect an object to need all its fields; a field that is sometimes unset
  invites null errors and hidden ordering dependencies
- **Instead:** pass the value as a parameter or return value, or Extract Class for the operation that needs
  it; Introduce Special Case for the unset state
- **Severity:** Minor; Major when the field is on an object shared across requests (see ARC-11)
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=16 — "a class in which a field
  is set only in certain circumstances"

### SML-09 Message chains
- **Look for:** long chains of navigation calls or nested key lookups, or the same navigation repeated at
  several call sites (the code-level form of PRN-10)
- **Why it matters:** each caller is coupled to the whole navigation path
- **Instead:** Hide Delegate at the right point, or Extract Function and Move Function to push the use down
  the chain
- **Severity:** Minor
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=17 — "You may see these as a
  long line of getThis methods, or as a sequence of temps"

### SML-10 Middle man
- **Look for:** a class, wrapper or service whose methods mostly forward to one other object unchanged;
  wrapper layers added by the change that add no policy, translation or protection
- **Why it matters:** indirection without value is extra code to read and keep in sync with the delegate
- **Instead:** Remove Middle Man and call the real object; keep the wrapper only when it is an adapter that
  translates (ARC-01) or enforces a boundary
- **Severity:** Minor
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=18 — "You look at a class’s
  interface and find half the methods are delegating to this other class"

### SML-11 Divergent change
- **Look for:** one module edited by the change for two unrelated reasons (a storage change and a pricing
  change in the same file) where those reasons recur; a module the `git log` shows changing for many
  different features (cite the commits). A batch of unrelated edits in one change proves nothing alone
- **Why it matters:** contexts that change separately are tangled, so a change to one forces understanding
  and re-testing the other (the change-history form of PRN-03)
- **Instead:** Split Phase when the two aspects form a sequence; otherwise Extract Class and Move Function
  into one module per context
- **Severity:** Minor
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=7 — "Divergent change occurs
  when one module is often changed in different ways for different reasons"

### SML-12 Shotgun surgery
- **Look for:** a small logical change that needed many small edits across many files or classes in the
  diff (one new field threaded by hand through every layer, one rule tweaked in five places)
- **Why it matters:** the next change of the same kind will miss a site; the scattering is the defect
  (ARC-07 at component scale)
- **Instead:** Move Function and Move Field to gather the changing parts into one module; Combine Functions
  into Class or into Transform
- **Severity:** Minor; Major when the scattered edits implement a rule that must stay consistent
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=8 — "every time you make a
  change, you have to make a lot of little edits to a lot of different classes"

### SML-13 Refused bequest
- **Look for:** a subclass that ignores most inherited behaviour, overrides methods to do nothing or throw,
  or does not want to support the parent's interface
- **Why it matters:** refusing the interface breaks substitution (PRN-05); refusing only implementation is
  usually harmless
- **Instead:** Replace Subclass with Delegate or Replace Superclass with Delegate when the interface is
  refused
- **Severity:** no finding when only implementation is refused; Major when the interface is refused
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=23 — "We don’t mind refusing
  implementations—but refusing interface gets us on our high horses." and "Nine times out of ten this smell
  is too faint to be worth cleaning"

### SML-14 Comments as deodorant
- **Look for:** comments explaining what a confusing block does, comments restating code, commented-out
  code, and comments that state a rule the code could check
- **Why it matters:** the comment covers code that should be clearer, and it rots when the code changes
- **Instead:** Extract Function named for the comment, Change Function Declaration to rename, Introduce
  Assertion for internal rules whose correctness does not depend on assertions being enabled (always-on
  checks for input and production requirements, PRN-14); keep comments that explain why (a workaround, an
  invariant, a specification item), and improving an explanation is a valid fix
- **Severity:** Nit; Minor for commented-out code or a comment that now contradicts the code
- **Source:** https://www.informit.com/articles/article.aspx?p=2952392&seqNum=24 — "comments are often used
  as a deodorant". Sonar RSPEC S125 "Sections of code should not be commented out"

## 4. Writing the stack-specific form

Stack review files cite these IDs instead of redefining them. For each shared entry a stack file uses:

- Give the construct a reviewer sees in that stack's diff, by name, not the definition again. Shapes to
  follow:
  - ARC-02 in Java: a `@RestController` injecting a repository in a codebase with a service layer; in
    Python: a Lambda handler calling a DynamoDB `Table` directly past the project's service layer; in
    Terraform: a root module re-declaring resources a child module it calls is meant to own (a root module
    composing modules and declaring its own environment resources is the normal shape); in CDK: an
    application stack re-creating low-level resources a shared construct the project uses already owns;
    in CloudFormation: a template reading another stack's resources by hard-coded name where the owner
    publishes no such contract (ARC-17)
  - ARC-01 in Java or Python: an SDK exception or response type in a service signature; in Terraform: a
    reusable module whose outputs or variables expose provider details its callers were meant not to need
    (a whole resource object passed through a typed object variable is a legitimate Terraform pattern); in
    CDK: a construct whose public API is meant to hide its L1 resource but exposes it (the documented
    `node.defaultChild` escape hatch is not a leak); in CloudFormation: outputs exporting implementation
    details consumers then depend on
  - ARC-03 in Java: package cycles; in Python: circular imports papered over with function-local imports;
    in IaC: two stacks or modules referencing each other's outputs
  - PRN-01 and PRN-02 in IaC: copy-pasted resource blocks against a module, `for_each`, loop or construct,
    and the acceptable duplication of per-environment values
  - ARC-15 in IaC: literals for account identifiers, Regions or names inside reusable modules, constructs
    or templates rather than variables, parameters or context
  - OO-only entries (PRN-05, PRN-11, SML-13 and similar) are inapplicable to declarative templates unless
    the stack has a meaningful form (CDK construct classes do); a stack file omits them rather than
    inventing one
- State the stack's threshold where the shared entry defers to it (lines, parameters, fan-out), with its
  source; thresholds live only in the stack file
- Cite the stack's tool rule IDs (Sonar language rules, linters, architecture-test rules) that detect the
  form, so the reviewer can tell what the build already caught
- Keep the shared severity unless the stack has a reason to move it, and say the reason (the Java file
  makes duplicated retry loops a Major, for example); the stack's `review.md` Blocker classes win
- Any IaC remedy that moves resources follows the identity rule in How to apply and points at the stack's
  own lifecycle checks (Terraform `moved` blocks, CDK logical IDs, CloudFormation logical IDs and
  replacement)
- Reference this file as `${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md` and the
  entry as its ID in the check's Why or Source field, for example "JAVA-ARC-04 (stack form of ARC-01)";
  one stack check may name several shared IDs ("stack form of ARC-01 and PRN-07") and still yields one
  finding. Cite only IDs that exist here

## 5. Out of scope / handled elsewhere

- Security exposure (injection, secrets, IAM, network reachability, data in logs): the stack file's security
  group and `implement-from-spec:iac-security-reviewer` / `implement-from-spec:reviewing-terraform-security`
- Error-handling mechanics, concurrency, resource management, performance and test smells: each stack
  file's own groups; PRN-14 here covers only the design choice to fail fast
- Formatting, naming conventions and mechanical metrics a linter or quality gate already enforces: the
  stack's linters; report them here only when the change introduces them and the gate did not run
- Specification fidelity (behaviour no item asks for, an item not delivered): the stack file's first group;
  PRN-09 points there when speculative code adds unspecified behaviour
- Architecture invariants stated in the project's rules: those are the project's checks, and this file only
  raises their severity (Blocker when violated)

## Sources

Each entry is a definition (the principle's or smell's origin), related guidance, a tool heuristic (a
linter or detector rule, whose predicate may differ from the definition) or a secondary source (marked).
Plugin policy (severity, evidence and reporting rules) is this file's own and cites no source.

- Hunt and Thomas, The Pragmatic Programmer, 20th anniversary edition, "DRY" extract:
  https://media.pragprog.com/titles/tpp20/dry.pdf
- Fowler and Beck, Refactoring 2nd edition, chapter 3 "Bad Smells in Code" (InformIT):
  https://www.informit.com/articles/article.aspx?p=2952392 (seqNum 2 to 24)
- Fowler, catalog of refactorings: https://refactoring.com/catalog/
- Fowler bliki: https://martinfowler.com/bliki/Yagni.html, https://martinfowler.com/bliki/BeckDesignRules.html,
  https://martinfowler.com/bliki/AnemicDomainModel.html, https://martinfowler.com/bliki/IntegrationDatabase.html,
  https://martinfowler.com/bliki/PresentationDomainDataLayering.html,
  https://martinfowler.com/bliki/BoundedContext.html, https://martinfowler.com/bliki/FlagArgument.html
- Fowler, "Reducing Coupling", IEEE Software: https://martinfowler.com/ieeeSoftware/coupling.pdf
- Shore, "Fail Fast", IEEE Software: https://martinfowler.com/ieeeSoftware/failFast.pdf
- Martin: https://blog.cleancoder.com/uncle-bob/2014/05/08/SingleReponsibilityPrinciple.html,
  https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html,
  http://butunclebob.com/ArticleS.UncleBob.PrinciplesOfOod
- Spolsky, "The Law of Leaky Abstractions":
  https://www.joelonsoftware.com/2002/11/11/the-law-of-leaky-abstractions/
- Garcia, Popescu, Edwards, Medvidovic, "Toward a Catalogue of Architectural Bad Smells", QoSA 2009:
  https://jgarcia.ics.uci.edu/wp-content/uploads/10.1.1.183.9958.pdf
- Designite architecture smells (Sharma): https://www.designite-tools.com/products-cs
- Sharma, taxonomy of software smells (with Lippert and Roock, Suryanarayana et al. entries):
  https://github.com/tushartushar/smells
- Arcelli Fontana, Lenarduzzi, Roveda, Taibi, "Are Architectural Smells Independent from Code Smells?":
  https://arxiv.org/pdf/1904.11755
- Lieberherr, Law of Demeter: https://www.ccs.neu.edu/home/lieber/LoD.html
- Dijkstra, EWD447 "On the role of scientific thought":
  https://www.cs.utexas.edu/users/EWD/transcriptions/EWD04xx/EWD447.html
- Raymond, The Art of Unix Programming, Rule of Least Surprise:
  http://www.catb.org/esr/writings/taoup/html/ch01s06.html
- PEP 20, The Zen of Python: https://peps.python.org/pep-0020/
- The Twelve-Factor App, Config: https://12factor.net/config
- Richardson, Shared database pattern: https://microservices.io/patterns/data/shared-database.html
- Microsoft Azure Architecture Center, Anti-corruption Layer pattern:
  https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer
- Cockburn, Hexagonal architecture: https://alistair.cockburn.us/hexagonal-architecture/
- Metz, "The Wrong Abstraction": https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction
- Google Testing Blog, "Tests Too DRY? Make Them DAMP!":
  https://testing.googleblog.com/2019/12/testing-on-toilet-tests-too-dry-make.html
- Fowler, "Inversion of Control Containers and the Dependency Injection pattern":
  https://martinfowler.com/articles/injection.html
- Fowler, "Parallel Change": https://martinfowler.com/bliki/ParallelChange.html; Lewis and Fowler,
  "Microservices": https://martinfowler.com/articles/microservices.html
- Seemann, "Design Smell: Temporal Coupling":
  https://blog.ploeh.dk/2011/05/24/DesignSmellTemporalCoupling/
- Richardson, Transactional outbox pattern: https://microservices.io/patterns/data/transactional-outbox.html
- Oracle, "Programming With Assertions":
  https://docs.oracle.com/javase/8/docs/technotes/guides/language/assert.html; Python language
  reference, the `assert` statement: https://docs.python.org/3/reference/simple_stmts.html
- HashiCorp, Terraform module composition and refactoring, type constraints:
  https://developer.hashicorp.com/terraform/language/modules/develop/composition,
  https://developer.hashicorp.com/terraform/language/modules/develop/refactoring,
  https://developer.hashicorp.com/terraform/language/expressions/type-constraints
- AWS CDK guide, escape hatches and refactoring: https://docs.aws.amazon.com/cdk/v2/guide/cfn-layer.html,
  https://docs.aws.amazon.com/cdk/v2/guide/refactor.html
- AWS CloudFormation, cross-stack references and resource import:
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html,
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-import-existing-stack.html
- Wikipedia (secondary sources): https://en.wikipedia.org/wiki/Rule_of_three_(computer_programming),
  https://en.wikipedia.org/wiki/Composition_over_inheritance, https://en.wikipedia.org/wiki/KISS_principle,
  https://en.wikipedia.org/wiki/Liskov_substitution_principle,
  https://en.wikipedia.org/wiki/Software_package_metrics
- Sonar rule metadata (RSPEC keys S107, S109, S110, S125, S138, S1075, S1172, S1200, S1448, S1820, S2638,
  S3011, S3776, S6539), read from the SonarSource analyzer repositories:
  https://github.com/SonarSource/sonar-python and https://github.com/SonarSource/sonar-java
