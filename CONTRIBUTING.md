# Contributing Guidelines

Thank you for your interest in contributing to our project. Whether it's a bug report, new feature, correction, or additional
documentation, we greatly value feedback and contributions from our community.

Please read through this document before submitting any issues or pull requests to ensure we have all the necessary
information to effectively respond to your bug report or contribution.


## Security issue notifications
If you discover a potential security issue in this project we ask that you notify AWS/Amazon Security via our [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public GitHub issue.

See [SECURITY.md](SECURITY.md) for the reporting channels, and the
[threat model](docs/security/threat-model.md) for the plugin's trust boundaries and controls.


## Reporting Bugs/Feature Requests

We welcome you to use the GitHub issue tracker to report bugs or suggest features.

When filing an issue, please check existing open, or recently closed, issues to make sure somebody else hasn't already
reported the issue. Please try to include as much information as you can. Details like these are incredibly useful:

- A reproducible test case or series of steps
- The version of our code being used (the `version` in `.claude-plugin/plugin.json`) and the Claude Code version
- Any modifications you've made relevant to the bug
- Anything unusual about your environment or deployment


## Contributing via Pull Requests
Contributions via pull requests are much appreciated. Before sending us a pull request, please ensure that:

1. You are working against the latest source on the *main* branch
2. You check existing open, and recently merged, pull requests to make sure someone else hasn't addressed the problem already
3. You open an issue to discuss any significant work - we would hate for your time to be wasted

To send us a pull request, please:

1. Fork the repository
2. Modify the source; please focus on the specific change you are contributing. If you also reformat all the code, it will be hard for us to focus on your change
3. Ensure the local checks pass (see "Local checks" below)
4. Commit to your fork using clear commit messages
5. Send us a pull request, answering any default questions in the pull request interface, and say which checks you ran and with what result
6. Stay involved in the conversation. This repository has no CI: a maintainer runs the full test suite before merging

GitHub provides additional document on [forking a repository](https://help.github.com/articles/fork-a-repo/) and
[creating a pull request](https://help.github.com/articles/creating-a-pull-request/).


## Local checks

There is no CI of any kind. The unit tests, the skill evals, the security scans and the container tests are kept in
the maintainers' development repository, as available there, and are not part of the released plugin. A pull request
is merged only after a maintainer has reviewed every changed line and run all of them on the change.

- **Every change:** `claude plugin validate . --strict` from the repository root passes, and the change works in a
  Claude Code session that loads your copy with `claude --plugin-dir <your copy>`
- **A change to a skill, an agent, the gate or the core:** describe how you exercised it: the skill run, the prompt
  or the command, and what you observed
- **The plugin's own Python:** Python 3.9 or later, standard library only. Run your change on `python3` and, on
  macOS, on the built-in Python (the plugin's minimum, 3.9)
- **Never commit credentials.** The maintainers' checks include a secrets scan; findings at or above MEDIUM fail
  the run


## Provenance and security records

- The maintainers record where every file came from. A pull request that adds a file says whether it is new or
  ported, and from what, with the source's licence
- The maintainers record how scan findings are triaged and every disposition. A pull request that suppresses or
  accepts a finding states its rationale; nothing is suppressed silently
- AI-generated code is welcome, but it is reviewed by a human like any other change, and AI agents must not
  open issues or pull requests unattended


## Finding contributions to work on
Looking at the existing issues is a great way to find something to contribute on. As our projects, by default, use the default GitHub issue labels (enhancement/bug/duplicate/help wanted/invalid/question/wontfix), looking at any 'help wanted' issues is a great place to start.


## Code of Conduct
This project has adopted the [Amazon Open Source Code of Conduct](https://aws.github.io/code-of-conduct).
For more information see the [Code of Conduct FAQ](https://aws.github.io/code-of-conduct-faq) or contact
opensource-codeofconduct@amazon.com with any additional questions or comments.


## Licensing

See the [LICENSE](LICENSE) file for our project's licensing. We will ask you to confirm the licensing of your contribution.

The `LICENSE` file holds the Apache License 2.0, the licence of the whole repository: scripts, hooks, skills and
documentation.
