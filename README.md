# daylee — Claude Code bridge for Daylee standups

`daylee` is a small CLI that captures Claude Code session activity on a
developer's machine and forwards it to the Daylee backend. The activity
feeds the AI-generated standup draft alongside GitHub, Linear, and JIRA.

## Install

```bash
pipx install daylee
```

## First-time setup

```bash
daylee login            # prints a 6-character code
                        # paste it into Slack: /daylee link <code>

daylee install-hooks    # registers Claude Code hooks (~/.claude/settings.json)

daylee status           # confirm everything is wired up
```

## What gets sent

By default: timestamps, durations, working directory, git remote, branch,
file paths touched, tool-use counts, and a locally-redacted prompt digest
(2 KB max). Tool *output* is never sent. Raw prompts are opt-in via
`~/.config/daylee/config.toml`.

## Privacy

The CLI runs a regex pass on prompts before transmission to redact AWS
keys, GitHub PATs, Slack tokens, JWTs, and PEM private keys; `.env` file
content is dropped entirely. The server runs the same pass again as
defence-in-depth.
