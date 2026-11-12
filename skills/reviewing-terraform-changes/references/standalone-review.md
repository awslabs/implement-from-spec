# Standalone Terraform review

What the review skill adds to `implementing-terraform-from-spec`'s `review.md`,
`terraform-practices.md` and `review-focus.md` (read in place; this file does not restate them). It
applies standalone and when the implementing skill calls the review. The snapshot, the review state and
the fix rounds are contract section 9 and SKILL.md steps 1, 5 and 6.

## Contents

1. What counts as a Terraform change
2. Read-only checks (the quality gate)
3. Check groups without a plan or specification
4. Rollback evidence

## 1. What counts as a Terraform change

- In scope: `*.tf`, `*.tf.json`, `*.tftest.hcl`, `*.tfvars.example`, backend configuration files
  (`*.hcl` passed to `-backend-config`), `.terraform.lock.hcl`, `.tflint.hcl`, and policy or template
  files the configuration reads (`file()`, `templatefile()`, `jsondecode(file(...))` targets)
- Findings by path alone, never opened: a `*.tfstate` or `*.tfstate.backup` file, a real `*.tfvars` or
  `*.auto.tfvars` file, anything under `.terraform/`. Adding one to version control is a Blocker
  (`terraform-practices.md` section 3: no secrets in HCL or example tfvars; state holds secrets in plain
  text)
- Root modules: the directories the project's CLAUDE.md names as roots; otherwise the directories that
  hold a `backend` block or a `provider` block. A changed child module is validated through the roots
  that call it, and on its own when no root in the repository calls it
- Change modes map to the external script's arguments exactly as SKILL.md step 1 lists them. For a pull
  request: the user checks out the branch; the range is `$(git -C <repo> merge-base <target> HEAD)..HEAD`
  with `<target>` the branch the PR merges into. Never fetch, pull or check out a branch yourself

## 2. Read-only checks (the quality gate)

Run from the main conversation while the stages work; the reviewers never run them. Each command below
changes nothing in the repository; anything that would (an `init` in place, `fmt` without `-check`,
`tflint --fix`) is not run, and a check that wrote there would change the candidate, so `record-gate`
would refuse its result. Save each output to `<DIR>/gates/<name>.txt` and record checks 2 and 3 with
`record-gate` (SKILL.md step 3) under the names `terraform-fmt` and `terraform-validate:<root>`: `pass`
when green as defined below, `fail` when red, and `not-run` with `--reason` when the check could not run
to a result (binary missing or too old, download declined, the sandbox blocking the provider plugin),
never `fail`. Checks 2 and 3 are the quality gate; checks 4 and 5 are advisory tools outside it, not
recorded, whose findings go into the triage.

1. **Binaries**, read-only:

       python3 -I "${CLAUDE_PLUGIN_ROOT}/core/deps/doctor.py" --stack terraform --project <repo> --json

   Exit 69 names the gap (terraform missing or older than the plugin's minimum). In a review that is not
   a stop: the checks that need the binary are recorded as `not-run` with that reason (below), and the
   review continues. Point the user to `/implement-from-spec:setup`; never install anything. Also compare
   `terraform version` with the roots' `required_version`: an older binary cannot validate them, which
   is "not run: terraform <v> is older than required_version <c>", not a red result

2. **Format**: `terraform -chdir=<repo> fmt -check -recursive -diff`. Exit 0 is green; exit 3 lists the
   files that are not formatted (red, with the diff as evidence); any other exit is a parse error,
   reported as red with its message

3. **Validate**: "Validation requires an initialized working directory with any referenced plugins and
   modules installed", and it "does not validate remote services, such as remote state or provider
   APIs" (developer.hashicorp.com/terraform/cli/commands/validate). For each affected root:
   - Already initialised (the root has a `.terraform/` directory) and the change adds no module call,
     module source or provider: `terraform -chdir=<root> validate -no-color` in place
   - Otherwise `init` is needed, and `init` writes `.terraform/` and the dependency lock file, so it runs
     in a scratch copy outside the repository. First try it with downloads impossible: when one of the
     platform's implied local mirror directories exists (Linux: `/usr/local/share/terraform/plugins`,
     `/usr/share/terraform/plugins`, `~/.local/share/terraform/plugins`, `~/.terraform.d/plugins`; macOS:
     `~/.terraform.d/plugins`, `~/Library/Application Support/io.terraform/plugins`, `/Library/Application
     Support/io.terraform/plugins`), write a CLI configuration with only a `filesystem_mirror` for it and
     run `init` with `TF_CLI_CONFIG_FILE` pointing at it. The configuration has no `direct` method, which
     is how a mirror is used exclusively: "you must either remove the `direct` installation method
     altogether or use its `exclude` argument" (developer.hashicorp.com/terraform/cli/config/config-file,
     `provider_installation`), so nothing is fetched from a registry and this needs no question. When it succeeds, validate as below. Only when no
     mirror directory exists or `init` reports a provider missing from the mirror, ask the user once:
     "validate needs a provider download into a scratch copy outside the repository; allow it? (yes /
     no)", and on yes run `init` without that configuration. The scratch copy holds the working tree
     without version-control data, state, real tfvars or `.terraform/`:

         scratch="$(mktemp -d "${TMPDIR:-/tmp}/tf-validate.XXXXXX")"
         rsync -a --exclude .git --exclude .claude --exclude .terraform --exclude '*.tfstate*' --exclude '*.tfvars' \
               "<repo>/" "$scratch/"
         printf 'provider_installation {\n  filesystem_mirror {\n    path = "%s"\n  }\n}\n' "<mirror dir>" \
               > "$scratch.tfrc"
         TF_CLI_CONFIG_FILE="$scratch.tfrc" \
           terraform -chdir="$scratch/<root>" init -backend=false -input=false [-lockfile=readonly]
         terraform -chdir="$scratch/<root>" validate -no-color

     When `validate` fails with "Failed to load plugin schemas" while `init` succeeded, the provider plugin
     could not open its local socket: Claude Code's macOS sandbox blocks Unix sockets. Record it as not
     run, never as `fail`, which makes verification incomplete and leaves the recommendation to the
     findings; never report it as passed or as a defect in the change:

         python3 -I "${CLAUDE_PLUGIN_ROOT}/core/scripts/review-snapshot.py" record-gate <DIR> \
             --name "terraform-validate:<root>" --status not-run \
             --command "terraform -chdir=$scratch/<root> validate -no-color" \
             --reason "the sandbox blocks the provider plugin's local socket"

     `-lockfile=readonly` when the copy has a `.terraform.lock.hcl`, so the check uses the locked
     provider versions ("suppress the lockfile changes, but verify checksums against the information
     already recorded", developer.hashicorp.com/terraform/cli/commands/init). `-backend=false` never
     touches the remote state. On no: "not run: provider download declined"
   - For the committed-range mode, validate the tree at `<b>`. When the working tree differs from it,
     build the scratch copy from the commit instead (`git -C <repo> archive <b> | tar -x -C "$scratch"`,
     which writes nothing in the repository; `git worktree add` would) and validate there

4. **TFLint**, when installed and the project configures it (`.tflint.hcl`) or its CI runs it:
   `tflint --chdir=<root>` (or `tflint --recursive` from the repository root). Rulesets missing from
   the plugin directory need `tflint --init`, which downloads them: ask as for validate, or report "not
   run: rulesets not installed". Never pass `--fix`

5. **Checkov**, when installed: `checkov -d <repo> --framework terraform --quiet --compact
   --skip-download`. `--skip-download` keeps it from contacting the vendor's platform. Each failed check
   is a *(tool)* finding for the triage; confirm it in the code like any other, and reject the ones the
   project's rules or specification prescribe

6. **Never, without the user's explicit yes in this conversation**: `terraform plan` (reads live state
   under the project's AWS profile), `terraform test` (run blocks apply unless they say
   `command = plan`), `terraform init` in the repository, `terraform providers lock`. Never at all in
   this skill: `apply`, `destroy`, `import`, `taint`, `untaint`, `state` subcommands, `force-unlock`,
   `init -migrate-state`, `workspace new|delete`, mutating `aws` calls

A check of the gate that could not run is recorded the same way, `--status not-run --command "<the
command>" --reason "<the reason quoted above>"` ("terraform <v> is older than required_version <c>",
"provider download declined"): `state` then reports verification incomplete with `<name> not run:
<reason>`, never Blocked by itself. A result recorded by mistake stays in `gates.json`: record the right
one after it (`state` reads each name's latest result), never edit, rewrite or delete the file. A missing
optional tool is "not run: not installed", never "clean". When a check runs against a scratch copy, say
so in its report line.

## 3. Check groups without a plan or specification

When neither a plan nor specification files are in scope, this rule holds verbatim
(`references/dispatch.json` copies this section into every reviewer's brief):

    No plan and no specification are in scope. Group 1 (Specification fidelity): review the change
    against what it claims to do (commit messages, PR description, comments and names, read after the
    code) and against the project's documented contracts when they exist (CLAUDE.md, README,
    docs/); report anything added that nothing asks for and anything that silently changes an existing
    output, variable or resource; write "not applicable: no plan or specification" only when nothing
    states an intent. Group 6 (Invariants): the CLAUDE.md architecture invariants when the file exists;
    otherwise the defaults in terraform-practices.md, and write "no project invariants documented". All
    other groups apply unchanged.

With a plan or specification, `review.md` applies unchanged.

## 4. Rollback evidence

The report's `Rollback:` line rests on the code and on plan output, never on the author's word, and
states code rollback and data recovery separately: reverting the configuration and applying it again
restores configuration, not the data a destroy or a replacement removed. A report never says the change
destroys nothing: without a plan, the destroy and replacement analysis is from the code, and the report
says so.

- **Evidence that counts**: a plan the user pasted or approved (`terraform show` lines with `# forces
  replacement`, `-/+` or `+/-`, and the destroy count); the change's `moved`, `removed` (with
  `lifecycle { destroy = false }`) and `import` blocks; `lifecycle { prevent_destroy = true }` and
  `create_before_destroy` on the touched resources; arguments that force replacement on the provider page;
  data protection settings such as `deletion_protection`, `skip_final_snapshot` with
  `final_snapshot_identifier`, `force_destroy` on buckets, versioning, backup and point-in-time recovery
- **not applicable**: the change alters no managed object (tests, documentation, `.tflint.hcl`, an
  example tfvars, a module no root calls yet)
- **supported (<evidence>)**: code: revert the commit and the operator applies the previous configuration;
  data: no existing stateful resource is destroyed or replaced, shown by a plan or by the code (renames
  carry `moved`, no forced-replacement argument changes on a data store), and the touched data stores keep
  `prevent_destroy` or deletion protection. Name the evidence, for example `supported (code: revert and
  apply; data: plan 2 to add, 1 to change, 0 to destroy; aws_dynamodb_table.orders prevent_destroy)`. A
  change that only adds objects is supported: a revert destroys those objects with what was written to
  them after the apply, which is the inverse of the change, not stranded writes; say so in the evidence
  (`data: plan 3 to add, 0 to destroy; a revert destroys the two new queues and their messages`). A
  change that alters the shape of persisted data or a contract the previous configuration reads (a key,
  attribute or field moved, renamed, nested or retyped; an item, message or output format) is never
  additive, even when it also adds objects: it is judged under unsafe below
- **unsafe (<finding>)**: a finding shows a stateful resource destroyed or replaced without a protection
  that stops it (`prevent_destroy` does not survive a deleted block), `force_destroy = true` or
  `skip_final_snapshot = true` on data the change can remove, or a change whose revert strands writes made
  after it (the previous configuration cannot read data in an object that survives the revert, or a revert
  destroys data that the items, the plan or the project's rules require to survive a rollback); name the
  F-number and the data recovery it needs (a final snapshot, a backup, PITR), or "no recovery path" when
  none exists
- **unknown (<what settles it>)**: a forced-replacement argument may change on an existing object and no
  plan is available, or the provider page does not say whether the argument forces replacement: name the
  operator's `terraform plan` command for the root
