# Security Policy

## Sensitive data

Do not submit any of the following to this public repository:

- real usernames or passwords
- private keys, tokens, SNMP communities, or enable secrets
- customer or project identifiers
- private production IP addresses
- production configuration backups or command output
- internal-only vendor or site command sequences

Use RFC 5737 documentation addresses in examples.

## Runtime security

AirOps Desktop stores operational data locally. In v0.1.0, device passwords
are still stored in plaintext SQLite. Telnet is also plaintext by protocol
design. Treat the application directory and database as sensitive.

SSH host-key verification is not enforced in the current release; this is
tracked as a hardening item.

For security issues in the application itself, use a private GitHub security
advisory when available instead of publishing credentials or exploit details in
a public issue.
