# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --json number,title,body,labels,comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Make an issue a sub-issue of a parent**: `gh issue create --parent <parent> ...`, or `gh issue edit <parent> --add-sub-issue <child>` (`gh` 2.94+). Without sub-issues, put `Part of #<parent>` at the top of the child body.
- **Blocking**: Prefer GitHub issue dependencies. Use `gh issue create --blocked-by <n>,<n> ...` or `gh issue edit <child> --add-blocked-by <blocker>` (`gh` 2.94+). When unavailable, use `Blocked by: #<n>` at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Count open blockers**: `gh api repos/<owner>/<repo>/issues/<n> --jq .issue_dependencies_summary.blocked_by`; alternatively filter `gh issue view <n> --json blockedBy` for `state == "OPEN"`.
- **Comment on an issue**: `gh issue comment <number> --body "..."`.
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`.
- **Close**: comment with the explanation, then run `gh issue close <number>`.

Infer the repo from `git remote -v`; `gh` uses the current clone. File issues only in `SuryaVamsi009/ATLAS`. Before the first issue creation in a session, confirm the target with `gh repo view --json nameWithOwner`.

## Pull requests as a triage surface

**PRs as a request surface: no.** Set to `yes` only if this repo starts treating external PRs as feature requests.

## When a skill says “publish to the issue tracker”

Create a GitHub issue.

## When a skill says “fetch the relevant ticket”

Read it with `gh issue view <number>`.

## Wayfinding operations

- **Map**: one issue labelled `wayfinder:map`, containing Notes / Decisions-so-far / Fog.
- **Child ticket**: link as a GitHub sub-issue when available; otherwise add it to the map task list and put `Part of #<map>` at the top of the child. Use `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`). Assign the ticket to the driving developer when claimed.
- **Blocking**: use the dependency convention above.
- **Frontier**: choose the first open map child without an open blocker or assignee.
- **Claim**: `gh issue edit <n> --add-assignee @me`.
- **Resolve**: comment with the answer, close the child, then append a context pointer to the map's Decisions-so-far.
