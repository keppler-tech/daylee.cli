# daylee — connect your coding agent to Daylee

`daylee` is a small CLI that links your machine to the Daylee backend
so any MCP-capable coding agent (Claude Code, Cursor, Codex, …) can
push standup updates on your behalf.

## Install

```bash
pipx install daylee
```

## First-time setup

```bash
daylee login            # prints a 6-character code
                        # paste it into Slack: /daylee link <code>

daylee connect          # prints MCP config snippets for the major agents
                        # (use --agent claude-code|cursor|codex for one
                        # specific snippet)

daylee status           # confirm everything is wired up
```

After pasting the snippet into your agent's MCP config, the agent has
access to three Daylee tools:

| Tool | Purpose |
|---|---|
| `mcp__daylee__get_last_update` | Returns the timestamp of your most recent submission |
| `mcp__daylee__get_standup_window` | Returns the active standup window(s) for your team(s) |
| `mcp__daylee__submit_update` | Submits a standup update on your behalf |

## Pushing an update

In **Claude Code**, install the bundled slash command and run:
```bash
mkdir -p ~/.claude/commands
cp <repo>/plugins/daylee/commands/daylee-update.md ~/.claude/commands/
```
```
/daylee-update
```

In **Cursor / Codex / any MCP-capable agent**:
> "Push my Daylee update."

The agent summarises your session, reads `git log`/`git status` since
your last push, asks you to confirm the summary, then submits.

## Privacy

The agent writes the summary on your machine and only the final summary
plus structured metadata (repo, branches, files touched) is sent to the
Daylee backend — never your raw prompts or tool outputs.
