# AirOps Desktop

**Lightweight. Offline-first. Portable.**

AirOps Desktop is a lightweight Windows desktop toolkit for operating network
devices in isolated, restricted, intranet, and air-gapped environments. It is
designed to work locally without a cloud service, web server, Docker, or
Internet access at runtime.

> Status: early public release (v0.1.0).

## Why AirOps Desktop?

Many production, regulated, industrial, and security-sensitive networks cannot
depend on SaaS services or Internet connectivity. AirOps Desktop focuses on a
simple local workflow:

- portable Windows desktop application
- local SQLite inventory
- SSH and legacy Telnet device access
- reusable device and command templates
- concurrent connectivity checks
- batch command execution
- long-running CLI output collection
- scheduled local tasks
- execution history and local result files
- Markdown device import/export

No device inventory, credentials, execution output, or logs are sent to a
remote service by the application.

## Built-in public templates

The public repository intentionally contains only generic templates:

- Generic SSH
- Generic Telnet
- Huawei VRP

Site-specific device types, credentials, addresses, command sets, and private
operational data are not part of this repository.

## Portable layout

A packaged build keeps mutable data beside the executable:

~~~text
AirOps-Desktop/
├─ AirOps-Desktop.exe
├─ data/
│  └─ airops_desktop.db
├─ logs/
└─ results/
~~~

Copy the whole folder to move the application and its local data together.

## Development

Requirements:

- Windows
- Python 3.11
- Tkinter / ttk
- SQLite
- Paramiko
- PyInstaller

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m airops_desktop
~~~

Or run:

~~~powershell
run.bat
~~~

Build a portable one-file executable:

~~~powershell
build_onefile.bat
~~~

The executable is written to release/AirOps-Desktop.exe.

## Security notes

AirOps Desktop is offline-first, but offline does not automatically mean secure.

Current v0.1.0 limitations:

- device passwords are stored in the local SQLite database in plaintext
- Telnet transmits credentials and CLI traffic without encryption
- SSH currently accepts unknown host keys automatically
- local database/result-file access is protected only by host OS controls

Use Telnet only where legacy equipment requires it and only on trusted isolated
networks. Do not commit data/, logs/, results/, or local import files.

Planned hardening includes Windows DPAPI-backed credential protection and
configurable SSH host-key verification.

See SECURITY.md.

## Public roadmap

- [ ] Driver/model abstraction for device families
- [ ] Windows DPAPI credential encryption
- [ ] Config version history and diff
- [ ] Structured inspection results
- [ ] Better SSH host-key policy
- [ ] Additional public device drivers
- [ ] Windows release artifacts

## Contributing

Issues and pull requests are welcome. When contributing examples or test
fixtures, use documentation-only addresses such as 192.0.2.0/24,
198.51.100.0/24, or 203.0.113.0/24. Never submit real device credentials,
customer names, private network addresses, or production configuration dumps.

## License

MIT
