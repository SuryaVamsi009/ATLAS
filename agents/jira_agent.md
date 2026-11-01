# Agent Jira - Jira Management Assistant

## Overview
Agent Jira is a Jira management assistant built using the Atlassian MCP tools. It can perform various Jira operations including issue creation, search, editing, transitions, and comment management.

## Session Information
- **Session ID:** `3febf14b-2d52-46af-bdea-fd6defb5df2f`
- **Project:** ATLAS (SuryaVamsi009/ATLAS)
- **Branch:** suryavamsi009-fantastic-doodle
- **Status:** Interactive and ready

## Capabilities

### 1. Issue Creation
- Create tasks, bugs, stories, and epics
- Set summary, description, priority, and assignee
- Example: `createJiraIssue({summary: "Fix login bug", projectKey: "KAN", issueType: "Task"})`

### 2. Issue Search
- Search using JQL queries
- Filter by project, status, priority, assignee, etc.
- Example: `searchJiraIssuesUsingJql({jql: "project = KAN AND status = Open", view: "evidence"})`

### 3. Issue Editing
- Update issue fields (summary, description, status, priority)
- Add labels and components
- Example: `editJiraIssue({issueIdOrKey: "KAN-6", additional_fields: {description: "Updated description"}})`

### 4. Workflow Transitions
- Move issues through statuses
- Assign to sprints or backlog
- Example: `transitionJiraIssue({issueIdOrKey: "KAN-4", transitionName: "To In Progress"})`

### 5. Comment Management
- Add comments to issues
- Edit existing comments
- Example: `addOrEditJiraIssueComment({issueIdOrKey: "KAN-6", commentBody: "Starting work on this issue"})`

### 6. Issue Retrieval
- Get issue details by key/ID
- View full issue metadata
- Example: `getJiraIssue({issueIdOrKey: "KAN-6"})`

## Usage Examples

### Create a Task
```javascript
// Create a new task in project KAN
const result = await createJiraIssue({
  summary: "Repair and connect notion",
  projectKey: "KAN",
  issueType: "Task",
  additional_fields: {
    description: "nvidia/nemotron-3.5-lightining-30b-a3b . Nvidia NIM"
  }
});
// Result: KAN-4 created
```

### Search Issues
```javascript
// Search for all open issues in KAN project
const results = await searchJiraIssuesUsingJql({
  jql: "project = KAN AND status = Open",
  view: "evidence",
  maxResults: 50
});
// Returns list of issues
```

### Transition an Issue
```javascript
// Move issue KAN-6 to In Progress
const result = await transitionJiraIssue({
  issueIdOrKey: "KAN-6",
  transitionName: "To In Progress"
});
// Issue status updated
```

### Add a Comment
```javascript
// Add comment to issue KAN-6
await addOrEditJiraIssueComment({
  issueIdOrKey: "KAN-6",
  commentBody: "Starting work on this task - will investigate the notion integration"
});
```

## Backup & Documentation

### Session Backup
- **Session ID:** `3febf14b-2d52-46af-bdea-fd6defb5df2f`
- **Plan file:** `~/.copilot/session-state/3febf14b-2d52-46af-bdea-fd6defb5df2f/plan.md`
- **SQL tracking:** Use `session_store_sql` to record configurations

### Repository Backup
- This markdown file is stored in: `/Users/suryavamsipichika/Documents/GitHub/ATLAS/agents/jira_agent.md`
- Keep updated with any capability changes
- Version control recommended

### Session Archiving
- Use `archive_session` when done with a project
- Restore later if needed
- Preserves history without keeping active worktrees

## Getting Started

1. **Interact with Agent Jira** by sending prompts like:
   - "Create a task to fix login bug in project KAN"
   - "Search for all open issues in project KAN with priority High"
   - "Transition issue KAN-4 to In Progress status"
   - "Add a comment to issue KAN-6: Starting work"

2. **Agent Jira will execute** using the Atlassian MCP tools automatically

3. **Review results** and continue with additional prompts as needed

## Configuration

Agent Jira operates within the ATLAS project workspace and uses:
- **MCP Server:** `cc-_1kgu7WrDe1UQjIe` (Atlassian)
- **Project:** KAN (and other projects as specified)
- **Session Mode:** Interactive (plan approved)

---
*Generated: 2026-11-01*
*Agent: Agent Jira*
*Project: ATLAS (SuryaVamsi009/ATLAS)*