# Claude Code Configuration

This directory contains Claude Code configurations for browser-agent-test-fixture.

## Configuration Files

| File | Purpose | Committed to Git |
|------|---------|------------------|
| `settings.json` | Project permissions, hooks, environment | Yes |
| `settings.local.json` | Local overrides (API keys, personal prefs) | No |
| `hooks/issue-detector.sh` | Auto-creates GitHub issues for Claude problems | Yes |
| `issue-log.txt` | Log of auto-created issues | No |
| `commands/*.md` | Custom slash commands | Yes |
| `agents/*.md` | Custom subagents | Yes |

## What's Configured

### Permissions (from Anthropic best practices)
- **Allowed**: Read/Edit src/, tests/, features.json
- **Denied**: .env files, secrets, destructive commands
- **Rationale**: Principle of least privilege + safety

### Hooks (bridging Claude Code features)
- **SessionStart**: Shows feature progress on every session start
- **PreToolUse (Edit)**: Reminds to run tests after edits
- **UserMessagePost**: Auto-creates GitHub issues when Claude encounters problems

### MCP Servers (from `.mcp.json`)
- **reliable-ai**: Feature tracking and coordination (get_progress, start_feature, complete_feature, etc.)
- **filesystem**: Sandboxed file access
- **code-search**: Fast code search via ripgrep

## Bridging Anthropic Articles ↔ Claude Code Features

| Anthropic Pattern | Claude Code Feature | Config Location |
|-------------------|---------------------|-----------------|
| Gap-driven development | SessionStart hook | settings.json |
| Session protocol | CLAUDE.md + hooks | CLAUDE.md, settings.json |
| Progress tracking | features.json + hooks | features.json |
| Tool safety | Permission rules | settings.json |
| Issue tracking | UserMessagePost hook | settings.json, hooks/issue-detector.sh |
| MCP servers | .mcp.json | .mcp.json |

## Update Lifecycle

### Scenario 1: Update configs in a running product dev environment

```bash
# 1. Edit the config file directly
vim .claude/settings.json

# 2. Restart Claude Code session to pick up changes
# (type /clear or restart the IDE)

# 3. Verify changes took effect
# Check hooks fire, permissions apply, etc.
```

### Scenario 2: Update the scaffold template (for new projects)

```bash
# 1. Edit files in reliable-ai/scaffold/
cd reliable-ai
vim scaffold/browser-agent-test-fixture/.claude/settings.json

# 2. Test by generating a new project
cookiecutter scaffold/ --no-input project_name="Test"

# 3. Verify the new project has updated configs
cat Test/.claude/settings.json
```

### Scenario 3: Propagate scaffold updates to existing projects

**Option A: Manual sync**
```bash
# Copy updated configs from scaffold to existing project
cp reliable-ai/scaffold/browser-agent-test-fixture/.claude/settings.json \
   my-existing-project/.claude/settings.json
```

**Option B: Git-based sync (recommended)**
```bash
# In existing project, add reliable-ai as upstream
git remote add scaffold https://github.com/dreamteam-ai-labs/reliable-ai.git
git fetch scaffold

# Cherry-pick or merge config updates
git checkout scaffold/main -- scaffold/browser-agent-test-fixture/.claude/
cp scaffold/browser-agent-test-fixture/.claude/* .claude/
rm -rf scaffold/
```

**Option C: Automation via n8n/GitHub Actions**
```yaml
# .github/workflows/sync-claude-config.yml
name: Sync Claude Config
on:
  repository_dispatch:
    types: [claude-config-updated]
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Fetch latest configs
        run: |
          curl -L https://raw.githubusercontent.com/dreamteam-ai-labs/reliable-ai/main/scaffold/.claude/settings.json \
            -o .claude/settings.json
      - name: Create PR
        uses: peter-evans/create-pull-request@v5
        with:
          title: "chore: sync Claude Code configs"
```

## Local Overrides

Create `.claude/settings.local.json` for personal settings (not committed):

```json
{
  "permissions": {
    "allow": [
      "Bash(docker:*)"
    ]
  }
}
```

## Adding Custom Commands

Create `.claude/commands/your-command.md`:

```markdown
# Your Command Name

Description of what this command does.

## Instructions

1. Step one
2. Step two
```

Then use with `/your-command` in Claude Code.