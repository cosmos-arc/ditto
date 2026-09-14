# Security Policy

Ditto is a local-first workstation and does not connect to a broker or place orders.

## Reporting a vulnerability

Please use [GitHub private vulnerability reporting](https://github.com/cosmos-arc/ditto/security/advisories/new).
Do not open a public issue for a suspected vulnerability or secret exposure.

Include reproduction steps, affected versions/commits, and logs with secrets redacted.
Findings against pinned third-party dependencies should name the lockfile entry and the
advisory identifier; findings against the production image should name the base digests
from `deploy/docker/Dockerfile`.

## Agent session boundaries

Development on this repository routinely happens through agent sessions
(Codex, ZCode). Their boundaries are machine-enforced, not advisory:

- Sessions run inside the host sandbox by default; bypass-permission and
  full-access modes are not used on this repository. Dangerous commands and
  protected writes are denied by the shared PreToolUse hook, and the
  `main` branch merge gate is enforced server-side by the `ditto-main` ruleset
  (see the [agent harness](docs/engineering/agent-harness.md)).
- Authorization boundaries for dependency upgrades, schema migrations, CI and
  release configuration, production or real-data writes, and irreversible
  deletions live in [AGENTS.md](AGENTS.md) as the single source of truth.
- Secrets never enter the repository: gitleaks runs as pre-commit and over the
  full history in CI; tests run against an isolated null keyring.

## Supply chain

- Python and JavaScript dependency sets are locked (`uv.lock`, `bun.lock`) and
  scanned by OSV on every PR; installations run against the pinned npmjs registry.
- Release images build only from digest-pinned base images; the artifact gate
  rejects images where files flagged HIGH/CRITICAL in a scanned source image
  remain byte-identical, and release evidence carries SBOMs and attestations.
