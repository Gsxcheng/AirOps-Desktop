# AGENTS.md

AirOps Desktop is a lightweight, offline-first Windows desktop toolkit for network operations in intranet, restricted, isolated, and air-gapped environments.

## Start here

Before changing code, read these files in order:

1. `AGENTS.md`
2. `PROJECT_STATE.md`
3. `docs/ARCHITECTURE.md`
4. `README.md` or `README.zh-CN.md`

Then inspect:

- `git status --short --branch`
- `git log -5 --oneline`

Do not infer the current state from old chat history when the repository can answer it.

## Core product rules

- There is ONE application codebase: `AirOps-Desktop`.
- Do not create a separate internal/private implementation.
- Environment-specific differences belong in local runtime data, not a code fork.
- Company/site-specific device templates, real device inventories, credentials, private IPs, logs, and configuration dumps must never be committed.
- Public examples must use RFC 5737 documentation addresses:
  - `192.0.2.0/24`
  - `198.51.100.0/24`
  - `203.0.113.0/24`
- Keep the application usable without Internet, cloud services, Docker, or a server at runtime.
- Preserve the current full desktop workflow unless the task explicitly requests a UI redesign.

## Main modules

- `src/airops_desktop/ui.py` — Tkinter/ttk desktop UI and local workflows.
- `src/airops_desktop/db.py` — SQLite schema, settings, inventory, templates, runs, public seed data.
- `src/airops_desktop/network.py` — SSH/Telnet/FTP transport, CLI prompt detection, long-output collection, execution.
- `src/airops_desktop/__main__.py` — application entry point.
- `scripts/check_public_safety.py` — public repository safety scan.

See `docs/ARCHITECTURE.md` for details.

## Runtime data boundary

These paths are local runtime state and must remain ignored by Git:

- `data/`
- `logs/`
- `results/`
- `imports/`
- generated EXE/runtime files under `release/`

The runtime SQLite database may contain device credentials. Treat it as sensitive.

## Security constraints

Current known limitations are intentional tracked debt, not claims of security:

- device passwords are stored in plaintext SQLite;
- Telnet is plaintext by protocol design;
- SSH currently accepts unknown host keys automatically.

Do not describe the project as cryptographically hardened until these are fixed.

## Verification before completion

For code changes, run:

```powershell
python scripts/check_public_safety.py
python -m unittest discover -s tests -v
python -m py_compile src/airops_desktop/*.py
```

For build-affecting changes on Windows, also build the portable EXE and smoke-test that it starts.

## Handoff / progress synchronization

Every meaningful completed task must update `PROJECT_STATE.md` in the same change:

- update "Last completed";
- update "Current state" if behavior changed;
- update "Known issues / technical debt" if needed;
- update "Next priorities" if priorities changed;
- record the verification commands actually run.

Keep `PROJECT_STATE.md` concise and factual. It is the cross-agent handoff source of truth.

## Definition of done

A task is not complete until:

- requested behavior is implemented;
- public-safety boundaries are respected;
- relevant tests/checks pass;
- `PROJECT_STATE.md` is synchronized;
- the working tree contains no accidental runtime/private data.
