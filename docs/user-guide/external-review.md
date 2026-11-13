# External review

Every implementing skill reviews its change in two parallel stages. The Claude stage runs generic
subagents that load the plugin's reviewer skills. The external stage sends the same change to a model of another family, because a
model reviewing code it may have written shares that code's blind spots. The external reviewer is optional
and **off by default**: until you enable it, nothing is sent to a non-Claude model and the Claude stage
reviews alone. Enabled, it is OpenAI GPT-6 Astra on Amazon Bedrock, called in your AWS account with your
AWS credentials, or your own reviewer command.

The skills run the external stage on every review through `core/scripts/spec-external-review.py`. The
script reads the plugin's settings itself and decides whether anything is sent; with the default it sends
nothing and prints "External review: off (configuration)". The skills pass no setting values and never
change one. Each review starts with one preparation call, `core/scripts/review-prepare.py`, which pins the
snapshot, classifies its risk and writes every reviewer's brief. With the setting off it also runs the
external-review script itself, so no runner subagent starts; enabled, a read-only runner subagent runs
the script in parallel with the Claude reviewers and returns its output verbatim.

## The review around it: snapshot, isolation, state and fix rounds

Both stages review one review snapshot, and every result binds to it (contract section 9).

- **Snapshot.** Before the reviewers start, `core/scripts/review-snapshot.py` records what is reviewed:
  each changed file's hash, the plan and specification files, and the policy files (`CLAUDE.md`,
  `AGENTS.md`, `REVIEW.md`) as they were at the base revision. The report opens with
  `Snapshot: <id> (valid)`; an edit after the review, or a policy copy in the snapshot that no longer
  matches what it recorded, makes it `invalidated: <paths>` and the review incomplete. Quality-gate
  results, and the outputs the infrastructure reviews read (a synthesised template, a change set or plan),
  are attached to the snapshot by `review-snapshot.py` and never outlive it
- **Policy from the base.** The reviewers, and the external reviewer through `--policy-dir`, read the
  policy files from the snapshot, not from your work tree, so a change cannot be reviewed under rules it
  rewrote. A change to a policy file is reviewed with the change and asks for your approval
  (`Approval required: human (policy file changed: <path>)`)
- **Risk.** `core/scripts/review-risk.py` raises the tier to `high` for policy, CI and automation files,
  security-relevant content, destructive data changes and weakened tests, and names the security
  reviewers that must run (CloudFormation or CDK templates and Terraform files in an application-code
  change). It only adds scrutiny and never changes an external-review setting
- **Isolation.** A hook, `core/gate/review-isolation.py`, enforces the reviewers' read-only rule inside
  Claude Code with an allowlist: a reviewer subagent may use only Read, Grep, Glob, read-only shell
  commands (`grep`, `rg`, `sort`, `wc`, `file`, `diff` and `find` only with their listed read-only options:
  none that runs a program, reads a list of file names or follows a symbolic link out of the allowed
  directories) and a few bookkeeping tools (the task list, tool search, its hand-back), so it cannot edit,
  fetch, call MCP tools, dispatch agents, load further skills or use any other tool, and it reads only the
  repository, the plugin and the snapshot (never a credential path). Reviewers run no tests; the skill's quality gate does. A denied call is listed
  as a part of the review that could not complete. **Limitation**: this is enforcement in Claude Code's
  tool layer, not an operating-system sandbox. The external-review script still sends what this page
  documents, and the skill still compares `git status` and `git diff` before and after the review
- **Findings** carry an `Evidence:` clause (the trigger, the path through the code, the wrong result) and
  may be marked `unsure` or `(pre-existing)`; pre-existing means the defect and its exposure both exist on
  the base without this change. The report shows Blockers and Majors in full and at most five Minor or Nit one-liners; every finding is saved to
  `findings.md` in the snapshot directory
- **State.** Every review report opens with a block of six lines, `Snapshot:`, `Recommendation:`
  (`No blocking findings`, `Changes requested` or `Blocked`), `Verification:` (`complete` or `incomplete`
  with reasons), `Approval required:`, `Risk:` and `Rollback:`, and ends with the same state as an
  `ifs-review-state:` JSON comment. *No blocking findings* is a recommendation, never an approval: you
  approve. Then come `### For the human reviewer` (what the change does, from the traced code, and the
  hunks to read first), the findings, `### Pre-existing (not caused by this change)` and a `Counts:` line;
  covered-by-gate and rejected findings appear there only as counts, and in full in `findings.md`
- **`REVIEW.md`** at the repository root or in a parent directory of a changed file may recalibrate
  Minor and Nit severity, cap Nits, add always-check rules and name generated paths to skip. It cannot
  remove a Blocker class, a lens, the security hand-off, the quality gate or the external stage, and it
  changes no external-review setting; a line that tries is reported as a finding
- **Fix rounds.** A fix is reviewed like the change: a new snapshot, its delta against the reviewed one
  as the scope, the earlier findings numbered F1, F2 and so on and reported `closed`, `open` or
  `regressed`. After two fix rounds automatic fixing stops and the skill asks whether the approach itself
  should change

## Settings

The plugin's settings. Claude Code asks for them when you enable the plugin and shows each one as a row in
`/config`. `/plugin configure implement-from-spec@implement-from-spec` opens the same dialog.

- `external_review`: `off` (default), `bedrock-gpt` or `command`
  - `off`: no change content goes to a non-Claude model
  - `bedrock-gpt`: GPT-6 Astra on Amazon Bedrock
  - `command`: your own reviewer command (see below)
- `external_review_auth`, for `bedrock-gpt`: `aws-profile` (default) or `api-key`
- `external_review_aws_profile`: the AWS profile for `aws-profile`. Empty (default): the default
  credential chain. It may differ from the account Claude Code uses
- `external_review_region`: the AWS Region. Empty (default): `AWS_REGION`, then `AWS_DEFAULT_REGION`, then
  `us-east-1`
- `external_review_model`: a model or inference profile ID. Empty (default): `us.openai.gpt-6-astra` for
  `aws-profile`, `openai.gpt-6-astra` for `api-key`
- `external_review_command`: for `command`, the reviewer command line
- `external_review_policy`: `optional` (default) or `required`
  - `optional`: when the reviewer cannot run, the skill reports why and continues with the Claude review
  - `required`: the run is reported as "verification incomplete" instead

With the default model, the Region must be one the model is served in, or the script refuses before any
call: `us-east-1`, `us-east-2`, `us-west-1`, `us-west-2`, `ca-central-1` or `ca-west-1` for `aws-profile`
(the US cross-Region inference profile), and `us-east-1` or `us-west-2` for `api-key`.

### Turn it on, or off again

Before you enable it, read "What is sent, and what is withheld" below and run a secret scanner on the
repository. In `/config`, set the plugin's "External reviewer" row to `bedrock-gpt` (or `command`). From
the shell:

```
echo '{"external_review": "bedrock-gpt"}' | claude plugin configure implement-from-spec@implement-from-spec --values-stdin
```

`claude plugin configure` needs Claude Code 2.1.285 or later and asks you to restart Claude Code. The
script reads the saved value on its next run. `/implement-from-spec:setup external-review` then checks the
tools the chosen authentication needs. To turn it off again, set the row back to `off` (or
`{"external_review": "off"}`); for one session, start Claude Code with
`IMPLEMENT_FROM_SPEC_EXTERNAL_REVIEW=off`. A misspelt mode is not taken as `off`: the script reports the
stage as not run with the invalid value and sends nothing.

### Where the script reads them, and overrides

Each value comes from the first source that sets it:

1. A flag on the script: `--external-review`, `--external-review-auth`, `--external-review-aws-profile`,
   `--external-review-region`, `--external-review-model`, `--external-review-command`,
   `--external-review-policy`
2. The environment: `IMPLEMENT_FROM_SPEC_<KEY>` (for example `IMPLEMENT_FROM_SPEC_EXTERNAL_REVIEW=bedrock-gpt`),
   then `EVAL_IMPLEMENT_FROM_SPEC_<KEY>` (the form `claude plugin eval` passes into its sessions, which
   receive only `EVAL_*` variables), then `CLAUDE_PLUGIN_OPTION_<KEY>`
3. The plugin's saved options (`pluginConfigs`) in the managed settings file, else in your user
   `settings.json`. Like Claude Code, the script ignores `pluginConfigs` in project and local settings
4. The default (`external_review = off`)

Only you set flags and variables; a skill never does on its own. A repository's committed
`.claude/settings.json` can also set variables in its `env` block, which Claude Code applies once you
trust the folder, and so could enable the reviewer; read a repository's settings file before you trust
it (source: "Settings files and precedence", https://code.claude.com/docs/en/settings, read 2026-10-19:
"most `env` values apply only after each teammate trusts the folder"). Settings delivered by MDM, the registry,
a server, or `claude --settings` are not visible to a script: override them with a variable. To see every
value and where it came from, without reading or sending anything, ask Claude to run the script with
`--show-config`.

## Authentication

Authentication applies only once `external_review` is `bedrock-gpt`.

### `aws-profile` (default)

The script calls the Bedrock Converse API through the AWS CLI (`aws bedrock-runtime converse`), signed
with SigV4. SSO profiles work, and no key is involved.

- Needs the AWS CLI v2 on PATH
- With a profile set, the profile alone decides who signs: the static key and profile variables are
  removed from the reviewer's environment
- `/implement-from-spec:setup external-review` checks the CLI

### `api-key`

The script runs the plugin's `core/scripts/bedrock-gpt`, which calls the Responses API on the `bedrock-mantle`
endpoint with an Amazon Bedrock API key.

- Export the key as `IMPLEMENT_FROM_SPEC_BEDROCK_API_KEY` in the shell that starts Claude Code. Never put it
  in a file
- Use a short-term key. AWS documents them as lasting up to 12 hours, inheriting the permissions of the
  identity that generated them, and recommended for production; long-term keys are for exploration only
- Needs bash, curl and jq
- `<plugin-root>/core/scripts/bedrock-gpt --info` prints the model, Region and endpoint without a network
  call. The client is not on the Bash tool's PATH, so nothing calls it without the review script's filters

**`AWS_BEARER_TOKEN_BEDROCK` is never used.** Claude Code itself authenticates to Bedrock with that
variable, and the AWS CLI would prefer it over your profile. The script removes it, together with
`AWS_BEARER_TOKEN_*`, `AWS_BEDROCK_API_KEY` and `BEDROCK_API_KEY`, from every reviewer's environment, so
enabling the reviewer never changes how Claude Code authenticates.

### AWS account prerequisites

- For `aws-profile`: `bedrock:InvokeModel` on the inference profile and on the foundation model
- For `api-key`: the identity that generated the key needs access to the model on `bedrock-mantle`
- GPT-6 Astra is a third-party model served from AWS Marketplace. Amazon Bedrock subscribes the account on
  the first call, which needs `aws-marketplace:Subscribe`, `aws-marketplace:Unsubscribe` and
  `aws-marketplace:ViewSubscriptions` and a valid payment method for Marketplace purchases. The first call
  also accepts the model's licence agreement
- The setup can take up to 15 minutes; until it completes, calls may return `AccessDeniedException`

Sources: the Amazon Bedrock User Guide pages "Request access to models", "API keys" and the GPT-6 Astra
model card, read 2026-10-16.

#### A least-privilege policy for `aws-profile`

Give the reviewer its own identity (a profile in `external_review_aws_profile`), separate from the role
that deploys, and scope it to the one model. The inference profile alone is not enough: a policy that
names an inference profile must also name the foundation model in each Region the profile routes to.
Replace `<region>` and `<account>`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeTheReviewerProfile",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:<region>:<account>:inference-profile/us.openai.gpt-6-astra"
    },
    {
      "Sid": "InvokeTheModelOnlyThroughTheProfile",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:*::foundation-model/openai.gpt-6-astra",
      "Condition": {
        "StringLike": {
          "bedrock:InferenceProfileArn": "arn:aws:bedrock:<region>:<account>:inference-profile/us.openai.gpt-6-astra"
        }
      }
    }
  ]
}
```

`Converse` needs `bedrock:InvokeModel` and nothing more. For the first call only, add
`aws-marketplace:Subscribe`, `aws-marketplace:Unsubscribe` and `aws-marketplace:ViewSubscriptions` (see
above), or let an administrator make the first call, and remove them afterwards.

#### Revoking access

- `aws-profile`: remove the policy from the reviewer's identity; for a role, also revoke its active
  sessions, which cuts off credentials already issued
- `api-key`: a short-term key cannot be deactivated or deleted on its own. To stop one before it
  expires, deny `bedrock:CallWithBearerToken` and `bedrock-mantle:CallWithBearerToken` to the identity
  that generated it, or invalidate that identity's sessions with a `Deny` on `aws:TokenIssueTime`. Both
  actions must be denied: denying only `bedrock:CallWithBearerToken` leaves the `bedrock-mantle` endpoint
  open. A long-term key can also be set inactive, reset or deleted in the Bedrock console or through IAM

#### Audit

- `aws-profile`: Amazon Bedrock logs `Converse` as a CloudTrail management event, and CloudTrail logs
  management events by default, so each review call appears in the account's CloudTrail Event history
  with the identity that signed it
- `api-key`: on `bedrock-mantle`, the Responses API call (`CreateInference`) is a CloudTrail data event,
  which is not logged by default and costs extra; configure an advanced event selector for
  `AWS::BedrockMantle::Project` on a trail to record it. Every `bedrock-mantle` event records
  `callWithBearerToken`

Sources, read 2026-10-16: "Prerequisites for inference profiles"
(https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html), "Inference using
Converse API" (https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html), "Handle
compromised long-term and short-term Amazon Bedrock API keys"
(https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-revoke.html), "Monitor Amazon Bedrock API
calls using CloudTrail" (https://docs.aws.amazon.com/bedrock/latest/userguide/logging-using-cloudtrail.html)
and "Monitor bedrock-mantle API calls using CloudTrail"
(https://docs.aws.amazon.com/bedrock/latest/userguide/logging-cloudtrail-mantle.html).

### `command`

`external_review_command` is split into arguments like a shell line and run without a shell. It reads the
prompt on stdin and prints the answer on stdout. Exit 69 from the command means "not run"; any other
non-zero exit is a failure. The reviewer's environment has the Bedrock bearer variables removed, as for
the other modes.

## What is sent, and what is withheld

Sent: the binding-rules files (`--rules`, by default the repository's `CLAUDE.md` and `AGENTS.md`), the
approved plan, the skill's review focus, the specification files in scope (`--context`) and the change.
The skills pass `--policy-dir`, the review snapshot's policy directory: the rules files are then read
from there, as they were at the base revision, instead of from the work tree, and without `--rules` every
`CLAUDE.md`, `AGENTS.md` and `REVIEW.md` in it is sent. It is the only rules input allowed outside `--repo` (the review focus comes from the plugin, and a pasted
diff is read from where `--diff-file` names it), and
it must be exactly the `policy/` directory of a snapshot of this repository (`<snapshot home>/<id12>/policy`,
its `manifest.json` naming `--repo`); `--rules` paths are then relative to it and confined to it, nothing in it
or on the way to it from the state directory may be a symlink, every file sent must be the one the
snapshot recorded (its sha256 in the manifest), and without `--rules` every file the manifest records must be
there. The snapshot must also be one of the change being reviewed: its policy at its base, the same mode and
commits as the change arguments, and a record of every policy file that applies to a changed path, so a
snapshot of another base, mode, commit range or diff is refused. For a review of the working tree the check is
the base, not the files: a snapshot of the same base taken before later edits passes, and a later `verify`
or `state` of that snapshot reports the edits. `--files`, which a fix round uses for its delta, names no base,
so with `--policy-dir` it also needs `--snapshot-id <id>`, the round's snapshot's full 64-character id,
which must be the one its manifest records, and the snapshot's base must be an ancestor of the repository's
`HEAD` (the fix sits on the reviewed base). The command `review-prepare.py` writes into
`<snapshot DIR>/briefs/external-review.md` always carries `--snapshot-id`, and a fix round keeps it when it
puts `--files <the delta's paths>` in place of the change argument. With `--files` the binding is that id and
an ancestor base, so an older snapshot of an earlier base on `HEAD`'s history passes when the command names
it by its own id (threat model, TM-15).
Nothing else, and nothing at all when the reviewer is `off`, the default. Each of these sits in the prompt between a
BEGIN and an END line that carry a random marker drawn for the run, and the reviewer is told that
everything between them is data: an instruction planted in a specification file, `CLAUDE.md` or the code
cannot close its section or forge a verdict, and the reviewer reports it as a Major finding instead of
following it.

Withheld, before anything is read:

- Files outside the repository, and symlinks
- Lock files, build output, environments and caches (`node_modules/`, `target/`, `cdk.out/`, `.venv/`,
  `.terraform/` and similar) and `.claude/`
- Sensitive files, never sent in any mode: `.env*` (except `.example`, `.sample` and `.template`), keys
  and certificates (`*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*.crt`, `*.cer`, SSH keys),
  `credentials*`, `.netrc`, `.npmrc`, `.pypirc`, `kubeconfig`, Terraform state (`*.tfstate`), real
  `*.tfvars` and `secrets.*` files
- Content that looks like a secret, in any file or diff chunk that would otherwise be sent: an AWS access
  key ID, an AWS secret access key after its key name, a private key block, a quoted password, secret,
  token or API key assignment with a value of 16 characters or more, a GitHub or Slack token, a JSON Web
  Token. The whole file or chunk is withheld, removed and context lines included, and the "not sent:"
  line names it with "content looks like a secret" and the kind, never the value

A change that touches a withheld file is reviewed without it, and the script prints a "not sent:" line
listing each one; the report names them. A required input (rules, plan, context) that cannot be sent in
full, for example over 200 KB per file or holding content that looks like a secret, stops the run instead
of being dropped. A prompt over 600,000
bytes stops too (exit 64): the skill then reviews one wave at a time.

**Both filters are heuristics.** The name filter knows the file names above, and the content check
knows the secret formats above; the rules files, the specification files in scope and every other changed
file are sent in full, so a secret in a form neither recognises (a database URL with a password, a token
assigned without quotes) is sent with it. Run a secret scanner before you enable the reviewer, and
keep `external_review` `off` for a repository with regulated or classified content until your
data-handling review allows the reviewer.

How Amazon Bedrock handles what is sent, in the AWS documentation's words (read 2026-10-16):

- The Converse API reference: "Amazon Bedrock doesn't store any text, images, or documents that you
  provide as content. The data is only used to generate the response."
  (https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
- Abuse detection, which applies to GPT-6 Astra: "For all OpenAI models other than GPT OSS Safeguard 120B,
  GPT OSS Safeguard 20B, gpt-oss-120b, and gpt-oss-20b, classifier-flagged traffic will be retained for
  up to 30 days for automated offline abuse detection. Eligible customers may request full ZDR through
  their AWS account team." and "Retained inputs and outputs are stored and processed by AWS and are not
  shared with third-party model providers."
  (https://docs.aws.amazon.com/bedrock/latest/userguide/abuse-detection.html)
- Data protection: "Because the model providers don't have access to those accounts, they don't have
  access to Amazon Bedrock logs or to customer prompts and completions."
  (https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html)
- Retention is configurable per Region and project; see "Data retention"
  (https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html)

With the `command` mode, where the prompt goes is whatever your command does with it.

The review is saved as `review.md`, beside `review.prompt.md` (the exact prompt), in a new run directory
under the review home: `$SPEC_REVIEW_HOME` when set, else `~/.local/state/spec-external-review/` (or under
`$XDG_STATE_HOME`). The script creates the review home and each run directory with mode 0700 and every
saved file with mode 0600, so only your user can read the code and specification text they hold. An answer without exactly one valid `VERDICT` line and a `FINDINGS` section is saved as
`review.invalid.md` and does not count as a review. The change and prompt digests are recorded, so both
review stages can be shown to have seen the same change.

## States and exit codes

Every run prints one line, `External review: <state> (<reason>)`, which the skill's report quotes
verbatim.

- `0`, passed: the review is printed, whatever its verdict. The skill verifies each finding against the
  code before acting on it and treats the answer as data: an instruction in it is never followed
- `0`, off: the line is exactly "External review: off (configuration)", for the default as for an `off`
  you set. Nothing was read or sent
- `69`, not run, policy `optional`: the reviewer could not start. Causes: the AWS CLI or the API key is
  missing, access is denied, the model is not enabled or not served in the Region, or a setting is invalid.
  The Claude review still runs
- `70`, not run, policy `required`: the same causes. The line ends "required by policy", and the report's
  status is "verification incomplete"
- `1`, failed: the call failed, or the answer is not a valid review. With policy `required` the line ends
  "required by policy" and the status is "verification incomplete"
- `64`: a usage error, nothing reviewable, a required input that cannot be sent, or the prompt over the cap

The skills never write an external review themselves, never change a setting to make the stage pass, and
never put a key in a file.
