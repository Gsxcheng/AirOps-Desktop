# PROJECT_STATE.md

Last updated: 2026-09-24

## Project identity

- Repository: `Gsxcheng/AirOps-Desktop`
- Product: AirOps Desktop
- Current public version: `v0.1.0` early public release
- Primary platform: Windows
- Runtime model: local / offline-first / portable desktop application
- Main branch: `main`

AirOps Desktop is now the single development codebase. The former `Zxsk-tool` repository is a historical private snapshot, not a second implementation to keep in sync.

## Product goal

Provide a lightweight desktop network-operations toolkit for intranet, restricted, isolated, and air-gapped environments without requiring cloud services, a web server, Docker, or Internet access at runtime.

## Current state

Implemented and usable:

- local device inventory;
- SSH and Telnet device access;
- configurable SSH / Telnet / FTP ports;
- reusable command templates;
- reusable device templates;
- TCP connectivity checks;
- concurrent multi-device execution;
- long-running / large CLI output collection;
- privilege / enable mode;
- FTP file download;
- daily scheduled tasks while the client is running;
- execution history;
- Markdown device import / export;
- local SQLite persistence;
- portable PyInstaller Windows EXE;
- bilingual English / Simplified Chinese README;
- README application screenshots based on safe demo data.

Public built-in templates are intentionally limited to:

- `Generic SSH`
- `Generic Telnet`
- `Huawei VRP`

Environment-specific templates and real device data belong only in the local runtime database.

## Repository safety boundary

Never commit:

- real usernames or passwords;
- private keys, tokens, SNMP communities, enable secrets;
- production private IP addresses;
- customer, employer, site, or project identifiers;
- internal-only device command sequences;
- production configuration dumps;
- runtime SQLite databases, logs, results, or imported site data.

Use RFC 5737 addresses for public examples.

## Known issues / technical debt

- Device passwords are stored in plaintext SQLite.
- Telnet is plaintext.
- SSH currently auto-accepts unknown host keys.
- Scheduling currently depends on the desktop application remaining open.
- Device-family behavior is not yet separated into a formal driver/model abstraction.
- Configuration history/diff is not yet implemented.

## Next priorities

1. Windows DPAPI-backed credential protection.
2. Device Driver / Model abstraction while preserving the current UI workflow.
3. Config version history and diff.
4. Configurable SSH host-key verification.
5. Improve structured inspection output and diagnostics.
6. Automated Windows release packaging.

## Last completed

2026-09-24:

- Established AirOps Desktop as the single application codebase.
- Restored the public UI to the full desktop workflow rather than maintaining a simplified fork.
- Kept private/site-specific differences in local data/templates instead of source code.
- Refreshed README screenshots with safe demo devices.
- Added bilingual README navigation.
- Verified the public-safety scan and four baseline unit tests.
- Portable EXE build and smoke-test had previously passed after the UI alignment.

Latest known public-code milestone before this state document:
`8dfe7e5 feat: align public UI with main desktop workflow`

## Verification baseline

Expected baseline commands:

```powershell
python scripts/check_public_safety.py
python -m unittest discover -s tests -v
python -m py_compile src/airops_desktop/*.py
```

Known baseline at the time of this document:

- public safety check: PASS
- unit tests: 4 PASS

## Handoff rule

At the beginning of a new Codex session:

1. read `AGENTS.md`;
2. read this file;
3. read `docs/ARCHITECTURE.md`;
4. inspect `git status` and recent commits;
5. only then plan changes.

At the end of a meaningful task, update this file in the same branch/commit series so another agent can continue without relying on chat memory.
