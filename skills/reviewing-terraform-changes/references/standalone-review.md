# Standalone Terraform review

What a review outside `implementing-terraform-from-spec` adds to that skill's `review.md`,
`terraform-practices.md` and `review-focus.md` (read in place; this file does not restate them).

## Contents

1. What counts as a Terraform change
2. Read-only checks
3. Check groups without a plan or specification

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

## 2. Read-only checks

Run from the main conversation while the stages work. Each command below changes nothing in the
repository; anything that would (an `init` in place, `fmt` without `-check`, `tflint --fix`) is not run.

1. **Binaries**, read-only:

       python3 -I "${CLAUDE_PLUGIN_ROOT}/core/deps/doctor.py" --stack terraform --project <repo> --json

   Exit 69 names the gap (terraform missing or older than the plugin's minimum). In a review that is not
   a stop: the checks that need the binary are reported as not run with that reason, and the review
   continues. Point the user to `/implement-from-spec:setup`; never install anything. Also compare
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
   - Otherwise `init` is needed, and `init` installs providers from the network and writes
     `.terraform/` and the dependency lock file. Ask the user once: "validate needs a provider download
     into a scratch copy outside the repository; allow it? (yes / no)". On yes, copy the working tree
     without version-control data, state, real tfvars or `.terraform/`:

         scratch="$(mktemp -d)"
         rsync -a --exclude .git --exclude .terraform --exclude '*.tfstate*' --exclude '*.tfvars' \
               "<repo>/" "$scratch/"
         terraform -chdir="$scratch/<root>" init -backend=false -input=false [-lockfile=readonly]
         terraform -chdir="$scratch/<root>" validate -no-color

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

A missing optional tool is "not run: not installed", never "clean". When a check runs against a scratch
copy, say so in its report line.

## 3. Check groups without a plan or specification

Give the reviewers this rule verbatim when neither a plan nor specification files are in scope:

    No plan and no specification are in scope. Group 1 (Specification fidelity): review the change
    against what it claims to do (commit messages, PR description, comments and names, read after the
    code) and against the project's documented contracts when they exist (CLAUDE.md, README,
    docs/); report anything added that nothing asks for and anything that silently changes an existing
    output, variable or resource; write "not applicable: no plan or specification" only when nothing
    states an intent. Group 6 (Invariants): the CLAUDE.md architecture invariants when the file exists;
    otherwise the defaults in terraform-practices.md, and write "no project invariants documented". All
    other groups apply unchanged.

With a plan or specification, `review.md` applies unchanged.
