# Daylee plugin for Claude Code

A `/daylee-update` slash command that summarises your current Claude Code
session and pushes the result to Daylee as a standup update.

## Prerequisites

1. Your workspace admin has enabled the Daylee integration.
2. You've linked this machine:
   ```bash
   pipx install daylee
   daylee login
   ```
3. You've wired the Daylee MCP server into Claude Code:
   ```bash
   daylee connect --agent claude-code
   ```
   …and pasted the printed JSON snippet into `~/.claude.json` (or a
   project-local `.mcp.json`).

## Install the slash command

In Claude Code, add this repo as a plugin marketplace and install the plugin:

```
/plugin marketplace add keppler-tech/daylee.cli
/plugin install daylee
```

Manual install (if you don't want to use the marketplace):

```bash
mkdir -p ~/.claude/commands
curl -sL https://raw.githubusercontent.com/keppler-tech/daylee.cli/master/plugin/commands/daylee-update.md \
     -o ~/.claude/commands/daylee-update.md
```

## Use

In Claude Code:
```
/daylee-update
```

Claude will:
1. Ask Daylee for the last push timestamp and your team's standup window.
2. Read `git log` / `git status` since that timestamp.
3. Combine that with what it knows from this conversation into a 3-6 bullet summary.
4. Show you the proposed summary and wait for approval.
5. Push it to Daylee via `mcp__daylee__submit_update`.

## Other agents

The MCP server itself works with any agent that supports streamable-HTTP MCP:
- **Cursor**: `daylee connect --agent cursor`, paste into `~/.cursor/mcp.json`
- **Codex CLI**: `daylee connect --agent codex`, append to `~/.codex/config.toml`

Those agents don't have Claude-Code-style slash commands, but you can
trigger the same flow by asking the agent in plain language:
> "Push my Daylee update."
