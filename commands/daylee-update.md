---
description: Push a Daylee standup update summarising this session
allowed-tools: Bash(git log:*), Bash(git status:*), Bash(git diff:*), Bash(git rev-parse:*), Bash(git remote:*), mcp__daylee__get_last_update, mcp__daylee__get_standup_window, mcp__daylee__submit_update
---

You are pushing a Daylee standup update on behalf of the user. The
Daylee MCP server is wired in as `daylee`. Follow these steps:

1. Call `mcp__daylee__get_last_update` to find the timestamp of the
   user's previous submission. Call `mcp__daylee__get_standup_window`
   to discover the active standup window for each team they're on.

2. Decide the time window your summary covers:
   - **since** = `last_update.until` if present, else the earliest
     `window_start` returned by `get_standup_window`, else
     "two hours ago".
   - **until** = now (in UTC, ISO 8601).

3. Gather raw signal from git for context. Run, from the project root:
   - `git rev-parse --show-toplevel`
   - `git remote get-url origin` (best-effort)
   - `git log --since "<since>" --author "$(git config user.email)" --pretty=format:'%h %s'`
   - `git status --short`
   Plus what you already know from this conversation: what the user
   asked for, what got built, blockers, decisions.

4. Write a tight summary in 3–6 bullets. Focus on **outcomes**, not
   tool calls. Name specific repos / branches / PRs / tickets when you
   know them. Skip filler like "we discussed" or "I helped with".

5. Build the structured payload:
   - `repos`: list of repo labels touched (e.g. `["acme/api"]`)
   - `branches`: list of branches you committed to
   - `files_touched`: list of file paths modified (cap at ~20)
   - Anything else worth capturing as `source_metadata` (cwd, agent
     version if known).

6. Show the user the proposed summary plus `since` / `until` and ask
   for confirmation before submitting. If they ask for edits, revise
   and re-show. If they accept, call `mcp__daylee__submit_update` with
   `agent_kind="claude_code"`.

7. After submitting, print the returned `id` and `submitted_at`.

Notes:
- If `get_standup_window` returns an empty teams list, the user isn't
  on a Daylee team in this workspace — submit anyway; the backend
  stores the update for when they're added to one.
- If `mcp__daylee__submit_update` errors with 401/403, tell the user
  to re-run `daylee login` on their machine; the device may have been
  revoked.
- Never submit without showing the user the summary first.
