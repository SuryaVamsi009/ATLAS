# ATLAS Disaster Recovery Plan

## Purpose and scope

This plan describes how to recover the ATLAS repository and its project data after loss, corruption, compromise, or service outage. It covers:

- The GitHub repository and its Git history, branches, workflows, agents, skills, and documentation.
- Local development workstations and repository clones.
- The local JSONL journal at `.journal/ledger.jsonl`.
- Generated market-scan reports in `market-scan/`.
- GitHub Actions schedules, run outputs, and repository configuration.
- External credentials and integrations used by developers or automation.

ATLAS is research-only. Recovery must preserve the paper-trading default and risk gate; do not enable live order execution as part of recovery.

## Current state and recovery objectives

The GitHub repository is the only confirmed canonical remote. The daily market-scan workflow commits reports to GitHub. The daily bug-scan workflow uploads an artifact but does not define an explicit retention period. The journal implementation writes to the local `.journal/ledger.jsonl` path. No repository backup or restore automation, test suite, or dependency lock/manifest was found. Consequently, uncommitted local work and local journal data are not known to be backed up.

The following are proposed targets, not guarantees of the current setup:

| Asset/service | Target recovery point (RPO) | Target recovery time (RTO) |
|---|---:|---:|
| Tracked source, configuration, and Git history | 24 hours | 4 hours |
| Local journal ledger | 24 hours, or last verified backup | 1 business day |
| Committed market-scan reports | 24 hours | 4 hours |
| Scheduled GitHub Actions scans | 1 business day | 1 business day |

Set a more stringent journal RPO before using the journal for operational decisions or relying on it as the sole record of research outcomes. The journal currently exists only on the machine running the code unless separately backed up.

## Responsibilities and authority

- **Incident lead:** repository owner or designated maintainer; declares the incident, chooses recovery scope, and records the timeline.
- **Recovery operator:** performs repository, data, and automation restoration; captures verification evidence.
- **Credential owner:** revokes and reissues affected tokens and keys through their respective provider consoles.

One person may fill all roles for this repository. Record the current named maintainers, emergency contact path, GitHub organization/owner, and provider account recovery methods in an access-controlled location outside this repository. Do not put credentials, recovery codes, or private journal contents in this document or public issues.

## Backup and readiness controls

These are recommended controls; they are not currently automated by the repository:

1. **Git mirror:** maintain an encrypted, access-controlled mirror of the canonical repository in a separate account or provider. Update it at least daily and after significant releases. Verify that it contains all required branches and tags. A mirror hosted only under the same GitHub account is not an independent backup.
2. **Journal backup:** back up `.journal/ledger.jsonl` at least daily to encrypted storage outside the workstation and GitHub account. Retain dated snapshots so an accidental rewrite or corruption can be rolled back. Verify checksums and test reading a restored copy. Restrict access because journal data may reveal trading research or account-related details.
3. **Reports and artifacts:** retain committed `market-scan/` reports in the Git mirror. Set and document an explicit retention period for Actions artifacts; artifacts are supplemental and are not the source of truth.
4. **Rebuild information:** keep Python 3.11 and dependency installation instructions current. Add a dependency manifest and lock versions before treating a clean environment rebuild as deterministic. Preserve `skills-lock.json`; reinstall skills from its recorded sources rather than treating installed skill folders as the only copy.
5. **Account readiness:** keep GitHub and external provider recovery methods available to designated maintainers. Store provider names, token owners, scopes, and rotation instructions in a protected password manager, never in Git.
6. **Recovery testing:** at least quarterly, restore the mirror into a clean directory, validate the journal from a backup, and run a workflow manually in a safe test context. Record date, operator, restore point, elapsed time, validation results, and follow-up actions in an access-controlled record.

## Incident handling

1. **Declare and contain.** Identify affected systems and time range. Stop affected scheduled workflows if they could overwrite or publish corrupted data. If credentials may be exposed, revoke them immediately at the provider; do not wait for repository recovery.
2. **Protect evidence.** Preserve available logs, Git refs, Actions run IDs, and a read-only copy of damaged data before attempting repairs. Record timestamps in UTC and IST.
3. **Select a restore point.** Prefer the newest known-good independent backup. For a Git issue, compare the canonical repository with the mirror and inspect the affected commit range. For journal damage, preserve the damaged file separately and restore a dated backup rather than editing the only copy.
4. **Restore into isolation.** Use a clean workspace or a newly created repository location. Avoid force-pushing, history rewrites, or replacing the canonical repository until the recovered copy is verified and the repository owner approves the cutover.
5. **Validate and cut over.** Follow the relevant scenario below, capture results, then re-enable only the workflows and credentials required for normal research operation.
6. **Close out.** Document impact, restored data range, any unrecoverable gap, credential rotations, and corrective actions. Notify affected collaborators through the normal project channel.

## Recovery procedures

### GitHub repository unavailable, deleted, or corrupted

1. Check GitHub service status and confirm the failure is repository-specific. Do not treat a temporary outage as evidence that the remote should be recreated.
2. Obtain the latest independent mirror and clone it into a new clean directory:

   ```bash
   git clone --mirror <backup-url> atlas.git
   git --git-dir=atlas.git fsck --full
   ```

3. Compare branches and tags with the most recent backup inventory. If recovering from a mirror, create a working clone from it:

   ```bash
   git clone atlas.git ATLAS
   cd ATLAS
   git status --short --branch
   git log -1 --oneline
   ```

4. Create or repair the GitHub repository using the repository owner’s normal access-controlled process. Configure branch protection and required settings before directing collaborators to the restored remote.
5. Push recovered refs only after the owner confirms the destination and the `fsck`/branch review succeeds. Avoid force-push unless the owner explicitly approves the exact destination and overwrite.
6. Restore repository secrets and environment configuration from the approved credential store. Recreate Actions permissions and schedules; repository contents alone do not restore GitHub settings or secrets.
7. Verify a clean clone, check workflows, run agent validation, and trigger a manual market scan only after confirming that the run will publish to the intended repository.

If no independent mirror exists, recover whatever Git data remains from a developer clone, another collaborator’s clone, or GitHub’s repository recovery process. A workstation clone may not contain remote branches or unpushed work; record those gaps explicitly.

### Workstation lost or damaged

1. Revoke developer sessions and tokens associated with the lost device where supported. Rotate credentials if the device may have been unlocked or its storage was not encrypted.
2. On a trusted replacement device, install Git and Python 3.11, authenticate to the approved Git remote, and clone the repository.
3. Restore only project data needed for work. If the workstation held `.journal/ledger.jsonl`, recover it from the latest verified encrypted backup. Keep the original backup unchanged and record its timestamp/checksum.
4. Recreate environment variables and provider credentials from the approved secret store. Do not copy secrets from shell history, logs, or old unencrypted backups.
5. Install dependencies according to `README.md` and the scan workflow. Validate the clone and confirm market-scan automation can run without enabling live execution.

### Journal missing, malformed, or partially corrupted

1. Stop writers and copy the current journal to an incident-specific evidence location with restricted access. Do not run repair scripts against the only copy.
2. Determine the affected line range using a JSONL parser and compare against the latest known-good backup. Preserve valid records before and after the damaged range.
3. Restore a backup to a separate file and validate that each non-empty line parses as a JSON object with a unique `entry_id`. Compare line counts and file checksums with the backup record.
4. If recovering records from the damaged file, reconcile by `entry_id` and preserve original timestamps and source files. Keep the unrepaired original and document any gaps or conflicting entries.
5. Restore the verified file to `.journal/ledger.jsonl`, restrict filesystem access to the project’s authorized user, and make a fresh backup before resuming writes.
6. Run a read-only ledger stats/evaluation check. Confirm no live orders were placed as part of the validation.

The current journal supports append writes and also has code paths that rewrite the ledger. Treat backups as required; do not assume append-only behavior alone prevents data loss.

### GitHub Actions outage or failed scheduled scans

1. Inspect the workflow run, commit history, and GitHub service status. A missed scan does not require repository restoration.
2. Use `workflow_dispatch` for the relevant workflow or run the documented script locally in a clean Python 3.11 environment.
3. Confirm dependencies install, the script exits successfully, and output is under the expected path (`market-scan/` for the market scan). Review report timestamps and content before publishing.
4. If manual execution is used, commit generated reports through normal review. Resume the schedule after confirming its permissions and destination.
5. For the bug-scan workflow, retrieve its artifact while retained if needed. Do not rely on artifact availability as a durable backup.

### Credential or repository-account compromise

1. Revoke compromised personal access tokens, OAuth grants, API keys, and sessions through their provider consoles. Rotate credentials for integrations that shared the same secret or account.
2. Review GitHub audit events, workflow runs, changed Actions secrets, branch protections, collaborator access, and recent commits for unauthorized changes.
3. Disable affected workflows and remove unauthorized access before restoring files. Restore trusted code from the last clean independent mirror or reviewed commit.
4. Reissue narrowly scoped credentials and store them only in the approved secret store or GitHub Actions secrets. Verify no credential appears in Git history, logs, artifacts, generated reports, or issue text. If exposed in Git history, revoke first; history rewriting alone does not invalidate a secret.
5. Re-enable workflows one at a time and inspect the first run.

## Post-restore validation

Complete and record each applicable check:

- The restored working tree is clean, expected branches/tags are present, and Git reports no object corruption.
- Core Python modules import in Python 3.11.
- `python validate_agents.py` passes for the checked-out `.github/agents/`.
- A market-scan dry run or reviewed manual run produces a report under `market-scan/` with the expected date.
- A restored journal parses as JSONL and its record count, time range, and checksum match the selected backup record.
- GitHub Actions workflows have the expected schedule, permissions, secrets, and artifact retention.
- `OrchestratorConfig` remains in paper-trading mode and risk checks remain in the execution path. No recovery test places live orders.
- Collaborators can access the recovered repository, and the next backup completes successfully.

## Plan maintenance

Review this plan after changes to repository ownership, storage location, journal handling, Actions workflows, credential providers, or dependency installation. Update the backup inventory, named responsibilities, RPO/RTO targets, and recovery-test record whenever those operational details change.
