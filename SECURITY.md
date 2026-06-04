# Security Policy

## Threat model and deployment assumptions

Hatch is designed as a **single-user, self-hosted application** that runs on your local machine. This is not a multi-tenant service. The following assumptions are baked into the design:

- **No authentication.** There is intentionally no login system. The assumption is that only the person who started the application can access it.
- **Localhost-only.** The backend (port 8000) and frontend (port 3000) are bound to `127.0.0.1` by default. **Do not expose either port to the internet or to an untrusted network.** If you put this behind a reverse proxy that is internet-facing, you are responsible for adding authentication (e.g. HTTP basic auth, OAuth proxy).
- **Single user.** The data model stores one profile, one set of applications, and one job search. There is no user-isolation or tenant separation.

## Where secrets are stored

| Secret | Location | Notes |
|--------|----------|-------|
| LLM API keys (Anthropic, OpenAI, Google, etc.) | `data/api_keys.env` | gitignored; never committed |
| Profile configuration | `data/profile.yaml` | gitignored; contains personal info |
| Master CV | `data/master_cv.json` | gitignored |
| Database | `data/jobpilot.db` | gitignored |

None of these files are committed to the repository. Verify your `.gitignore` is correct before making your fork public.

## What the application does NOT do

- It does **not** auto-submit job applications. The "assisted apply" flow requires the user to manually submit after reviewing tailored documents.
- It does **not** send data to third parties except your configured LLM provider (Anthropic, OpenAI, Google, or your local Ollama instance).
- It does **not** store LLM API keys in the database — they are read from environment files at runtime.

## Known limitations (acceptable for localhost use)

- **No CSRF protection.** Acceptable for a localhost-only app; would be required for any internet-facing deployment.
- **SQLite with no encryption.** The job database is a plaintext SQLite file. Acceptable for local use; encrypt the disk if the machine is shared.
- **No rate limiting per user.** Acceptable for single-user; required for multi-tenant.

## Reporting a vulnerability

This is a personal self-hosted tool. If you find a security issue that could affect users who follow the self-hosting instructions (i.e., not multi-tenant concerns), please open a GitHub issue marked **[SECURITY]**. For issues involving credential exposure or data leakage, email the maintainer directly rather than opening a public issue.

## Dependency security

The CI pipeline runs `npm audit --audit-level=high` (frontend) and `pip-audit` (backend) on every push. Check the Actions tab for the current status.
