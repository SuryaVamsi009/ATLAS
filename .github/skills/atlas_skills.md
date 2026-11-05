# ATLAS Skills Configuration

## Installed Skill Packages (skills CLI)

Agent skills are installed via the [skills](https://github.com/vercel-labs/skills) CLI into `.agents/skills/` (universal layout, recognized by GitHub Copilot and 20+ agents), with Claude Code symlinks in `.claude/skills/`. Packages are pinned in `skills-lock.json`.

| Package | Source | Skills | Installed |
|---------|--------|--------|-----------|
| `mattpocock/skills` | https://github.com/mattpocock/skills | 38 | 2026-11-05 |

```bash
npx skills@latest add mattpocock/skills --skill '*' -y   # install
npx skills@latest list                                    # list installed
npx skills@latest update --project -y                     # update
```

Notable skills: `ask-matt` (router), `tdd`, `code-review`, `diagnosing-bugs`, `implement`, `to-spec`, `to-tickets`, `pr`, `research`, `retro`, `grill-with-docs`, `domain-modeling`.

## Enabled Skills (from settings.json)

The following MCP skills are enabled in `/Users/suryavamsipichika/.copilot/settings.json`:

| Skill | MCP Server | Purpose |
|-------|-----------|---------|
| `computer-use` | `computer-use-*` | UI automation, screen interaction |
| `atlassian` | `cc-_1kgu7WrDe1UQjIe-*` | Jira issue management, Confluence content |
| `notion` | `cc-Nzr5erXk-_8CZnJY-*` | Notion page/database management, skills |

## Jira Skill (Agent Jira)

**Location:** `.github/agents/jira_agent.md`

**Capabilities:**
- Issue creation (`createJiraIssue`)
- Issue search (`searchJiraIssuesUsingJql`)
- Issue editing (`editJiraIssue`)
- Workflow transitions (`transitionJiraIssue`)
- Comment management (`addOrEditJiraIssueComment`)
- Issue retrieval (`getJiraIssue`)

**Configuration:**
- Project: ATLAS (SuryaVamsi009/ATLAS)
- Session ID: `3febf14b-2d52-46af-bdea-fd6defb5df2f`
- Branch: suryavamsi009-fantastic-doodle

**Usage:**
```javascript
// Create a task
const result = await createJiraIssue({
  summary: "Fix login bug",
  projectKey: "KAN",
  issueType: "Task",
  additional_fields: {
    description: "nvidia/nemotron-3.5-lightining-30b-a3b . Nvidia NIM"
  }
});
```

## Notion Skill (Agent Notion)

**Location:** `.github/agents/notion_agent.md`

**Capabilities:**
- Page creation (`createNotionPage`)
- Database management (`queryDataSource`)
- Content updates (`updatePageContent`)
- Skill integration (`updateEnabledSkills`)
- Page retrieval (`fetchPage`)

**Configuration:**
- Project: ATLAS (SuryaVamsi009/ATLAS)
- Enabled plugins: computer-use, atlassian, notion
- Session ID: placeholder-session-id

**Usage:**
```javascript
// Create a project documentation page
const result = await createNotionPage({
  title: "ATLAS Project Overview",
  icon: "📊",
  cover: "https://example.com/atlase-cover.jpg",
  properties: {
    "Project": "ATLAS",
    "Status": "Active",
    "Created": "2026-11-03"
  }
});
```

## Skill Management

### Enable/Disable Skills

Skills are enabled/disabled via `/Users/suryavamsipichika/.copilot/settings.json`:

```json
{
  "enabledPlugins": {
    "computer-use": true,
    "atlassian": true,
    "notion": true
  }
}
```

### Add a New Skill

To add a new skill URL:

```javascript
// Using the Notion MCP tool
await notionUpdateEnabledSkills({
  add_skill_urls: ["https://www.notion.so/new-skill-url"]
});
```

### Remove a Skill

To remove a skill URL:

```javascript
// Using the Notion MCP tool
await notionUpdateEnabledSkills({
  remove_skill_urls: ["https://www.notion.so/old-skill-url"]
});
```

## Integration Points

### ATLAS Workflow Integration

Both skills integrate with the ATLAS project workflow:

1. **Jira**: Create issues for ATLAS next steps, track research findings, document risk verdicts
2. **Notion**: Document project architecture, store journal entries, maintain evaluation results

### Recommended Workflow

1. **Research phase**: Create Jira tasks for each ATLAS next step
2. **Implementation**: Use Jira for issue tracking, Notion for documentation
3. **Review**: Update both Jira status and Notion page status
4. **Retrospective**: Archive Jira issues, update Notion database

## Version Control

Both skill files are tracked in git:

- `.github/agents/jira_agent.md` - Commit `39df7ec` (moved to .github/)
- `.github/agents/notion_agent.md` - Created this session

These files should be kept in sync with the `.copilot/settings.json` plugin configuration.