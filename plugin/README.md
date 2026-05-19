# Daylee plugin for Claude Code

A `/daylee:update` slash command that summarises your current Claude Code
session and pushes the result to Daylee as a standup update.

## Prerequisites

1. Your workspace admin has enabled the Daylee integration.
2. You've linked this machine and wired the slash command + MCP server:
   ```bash
   pipx install daylee
   daylee login
   daylee connect --agent claude-code
   ```
   `daylee connect --agent claude-code` registers this plugin in
   `~/.claude/settings.json` (so `/daylee:update` shows up) and prints
   the MCP-server JSON to paste under `mcpServers` in `~/.claude.json`.

## Manual install (without the CLI)

If you'd rather not run the CLI, install the plugin through Claude
Code's marketplace UI:

```
/plugin marketplace add keppler-tech/daylee.cli
/plugin install daylee
```

You'll still need the MCP server wired in for the command to do
anything useful — the CLI is the simplest way to obtain a device
token.

## Use

In Claude Code:
```
/daylee:update
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
