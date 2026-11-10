# Model providers

The skills work the same on each way of running Claude Code:

- A Claude subscription login (Pro, Max, Team or Enterprise)
- An Anthropic API key
- Amazon Bedrock: `CLAUDE_CODE_USE_BEDROCK=1`, with an AWS profile, an SSO profile, access keys or an
  Amazon Bedrock API key

Set up the provider as the Claude Code documentation describes. The plugin needs nothing extra from it.

## Models by alias

The skills name models only by alias: `opus`, `sonnet` or `inherit`. A full model ID would tie
them to one provider, because a first-party ID fails on Bedrock and a Bedrock ID fails first-party.

- The Claude review subagents run on `opus` or `sonnet`, as each skill states
- The `running-external-review` subagent, which only runs the external review command, runs on `sonnet`
- No skill sets an effort level. Your session's setting applies

## Amazon Bedrock: pin the aliases

Without pins, Claude Code resolves the aliases to its built-in Bedrock defaults. Its Bedrock page (read
2026-10-16) says: "without `ANTHROPIC_DEFAULT_SONNET_MODEL`, the `sonnet` alias resolves to Sonnet 4.5".
That is an older model than the current Sonnet, so a `sonnet` reviewer would silently run on it.

Pin both aliases to models enabled in your account:

```
export ANTHROPIC_DEFAULT_OPUS_MODEL='<an Opus model or inference profile ID>'
export ANTHROPIC_DEFAULT_SONNET_MODEL='<a Sonnet model or inference profile ID>'
```

Or run `/setup-bedrock` in Claude Code: the wizard verifies which models your account can invoke and
saves the pins in your user settings. `/status` shows the region in use.

Other Bedrock differences, and how the plugin handles them:

- **WebSearch** is not available on Amazon Bedrock. The skills do not need it: they read documentation
  through the AWS Documentation MCP server, the Terraform MCP server, or WebFetch on known URLs
- **Monitors** do not run on Amazon Bedrock. The plugin uses none; its gate is a hook, which runs
  everywhere
- **Context size.** The skills read specifications section by section and assume no particular context
  window

## Claude Code's credentials and the external reviewer

The external reviewer authenticates on its own, and never with Claude Code's credentials.

- Claude Code on Bedrock may use a Bedrock API key in `AWS_BEARER_TOKEN_BEDROCK`. The external review
  script removes that variable, and every other Bedrock bearer variable, from the reviewer's environment,
  so turning the reviewer on never changes how Claude Code authenticates
- The reviewer's AWS profile may differ from the account Claude Code runs in
- In API-key mode the reviewer reads its own key from `IMPLEMENT_FROM_SPEC_BEDROCK_API_KEY`

Details: [external-review.md](external-review.md).

## Billing

- On a subscription, the skills spend your plan's usage
- With an API key or on Amazon Bedrock, they are billed per token
- The external review (off by default) is billed separately when you enable it, to the AWS account it
  runs in, at the reviewer model's Amazon Bedrock price
