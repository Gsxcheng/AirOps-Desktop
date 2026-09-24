# Architecture

## Overview

AirOps Desktop is intentionally a small local desktop application.

```text
AirOps Desktop
├─ Tkinter / ttk UI
├─ SQLite local state
├─ SSH / Telnet / FTP transports
├─ local scheduler
└─ local logs / execution results
```

There is no required cloud control plane, web backend, container runtime, or remote database.

## Repository map

```text
AirOps-Desktop/
├─ src/
│  └─ airops_desktop/
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ ui.py
│     ├─ db.py
│     └─ network.py
├─ tests/
│  ├─ test_network.py
│  └─ test_public_defaults.py
├─ scripts/
│  └─ check_public_safety.py
├─ docs/
│  └─ images/
├─ examples/
├─ main.py
├─ pyproject.toml
├─ build_onefile.bat
├─ run.bat
├─ README.md
├─ README.zh-CN.md
├─ SECURITY.md
└─ PROJECT_STATE.md
```

## Module responsibilities

### `ui.py`

Owns the desktop user experience:

- device list and detail editor;
- multi-device selection;
- sorting and connectivity-status rendering;
- command-template management;
- device-template management;
- scheduled-task view;
- execution-history view;
- Markdown import/export;
- orchestration of background execution threads.

The current full desktop workflow is intentional. Do not replace it with a simplified public-only UI.

### `db.py`

Owns local persistence:

- SQLite schema initialization;
- application settings;
- command templates;
- device templates;
- devices;
- execution runs;
- schedule metadata;
- public default seed templates.

Important design rule: site/company-specific templates belong in the runtime database, not in source-code seed data.

### `network.py`

Owns device communication and execution:

- TCP connectivity checks;
- SSH via Paramiko;
- Telnet compatibility;
- FTP downloads;
- CLI prompt detection;
- long-running command read policies;
- command execution;
- local output-file generation;
- execution-result persistence through the database layer.

Large configuration commands intentionally use a much longer hard timeout than ordinary commands.

## Data model boundary

Portable runtime state lives beside the packaged executable:

```text
AirOps-Desktop/
├─ AirOps-Desktop.exe
├─ data/
│  └─ airops_desktop.db
├─ logs/
└─ results/
```

The same application code can therefore be used in multiple environments while each machine keeps its own inventory, credentials, and private templates.

## Public vs private content

The repository itself is public-safe.

Public code may contain generic protocol logic and publicly documented vendor examples.

Private operational content must stay local:

- employer/customer-specific device types;
- site-specific command templates;
- production device inventory;
- credentials;
- private addressing;
- command output and configuration backups.

This separation is a data/configuration boundary, not a code-fork boundary.

## Concurrency

Connectivity checks and multi-device execution use worker threads so the Tk UI remains responsive. UI updates must be marshalled back to the Tk main thread.

Avoid adding blocking network calls directly to UI callbacks.

## Build

The project targets a portable Windows executable using PyInstaller.

Development entry points:

```powershell
python -m airops_desktop
python main.py
```

Build:

```powershell
build_onefile.bat
```

## Current architectural evolution

The next structural step is a Driver / Model layer that encapsulates device-family differences such as:

- login/session preparation;
- prompt behavior;
- pagination control;
- privilege transition;
- default inspection commands;
- configuration-backup commands;
- output cleanup.

This should be introduced incrementally without breaking the current working SSH/Telnet execution path or creating separate application variants.
