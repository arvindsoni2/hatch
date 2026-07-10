# Troubleshooting

Use the symptom that best matches what you see, then start with the diagnostic command before changing config.

## Frontend Unavailable

- Symptom: `http://localhost:3000` does not load
- Likely cause: frontend container is stopped or failed during boot
- Diagnostic:

```bash
docker compose ps
docker compose logs --tail 50 frontend
```

- Recovery: rebuild and restart the frontend with `docker compose up -d --build frontend`

## Backend Unavailable

- Symptom: the UI loads but API calls fail or onboarding cannot save
- Likely cause: backend container is unhealthy or the database cannot open
- Diagnostic:

```bash
curl -f http://127.0.0.1:8000/api/health
docker compose logs --tail 50 backend
```

- Recovery: restart backend, then re-check health

## App Lock Problems

- Symptom: unlock fails or password is forgotten
- Likely cause: wrong local password or app-lock tables need reset
- Diagnostic:

```bash
docker compose ps
```

- Recovery:

```bash
bash scripts/reset-app-lock.sh
```

## Onboarding Does Not Complete

- Symptom: save loops, returns to onboarding, or setup status stays incomplete
- Likely cause: backend profile save or profile validation failed
- Diagnostic:

```bash
docker compose logs --tail 50 backend frontend
hatch status
```

- Recovery: revisit onboarding, then re-run `hatch apply-ai-config` if AI mode was changed

## Master CV Missing

- Symptom: CV Studio or Settings shows no confirmed resume
- Likely cause: upload not confirmed or local file was reset
- Diagnostic:

```bash
ls -l data/master_cv.json data/master_cv.meta.json
```

- Recovery: re-upload the resume from Settings

## Local Model Unreachable

- Symptom: local AI selected but AI actions fail
- Likely cause: models are missing or `llm-primary` / `llm-triage` is not running
- Diagnostic:

```bash
hatch probe
hatch models list
docker compose ps
docker compose logs --tail 50 llm-primary llm-triage
```

- Recovery: install the selected models, then restart local model services

## Cloud Provider Authentication Failure

- Symptom: provider test fails or AI setup shows missing secret
- Likely cause: host secret not configured or provider/model mismatch
- Diagnostic:

```bash
hatch secrets status
```

- Recovery: set or replace the secret with `hatch secrets set <provider>`

## Scraper Failure Or No Jobs Discovered

- Symptom: discovery runs but produces no roles
- Likely cause: source drift, rate limiting, or weak query/profile data
- Diagnostic:

```bash
docker compose logs --tail 100 backend
```

- Recovery: review job boards, target roles, and source health in the logs

## No High-Match Roles

- Symptom: roles arrive but none are shortlisted
- Likely cause: thresholds, sparse skills, or broad search inputs
- Diagnostic:

```bash
curl -f http://127.0.0.1:8000/api/agents/dashboard/pipeline
```

- Recovery: tighten the profile, add more skills, or review shortlist thresholds in the saved profile

## CV Or Cover Letter Generation Failure

- Symptom: Tailor fails or stalls
- Likely cause: AI provider unavailable, local model unhealthy, or document guardrails rejected the generation
- Diagnostic:

```bash
docker compose logs --tail 100 backend
```

- Recovery: re-check AI setup, then retry generation

## PDF Or DOCX Export Problems

- Symptom: generated package exists but a format is unavailable
- Likely cause: PDF export is capability gated, while DOCX remains the primary source of truth
- Diagnostic:

```bash
curl -f http://127.0.0.1:8000/api/setup/capabilities
```

- Recovery: use DOCX when PDF export is unavailable, or configure the converter path if supported

## Capability Profile Mismatch

- Symptom: browser, embeddings, or advanced coach functionality is unavailable
- Likely cause: backend profile is still `core`
- Diagnostic:

```bash
hatch capabilities status
```

- Recovery:

```bash
hatch capabilities enable browser
hatch capabilities enable local-embeddings
hatch capabilities enable full
```

## Windows Installer Issues

- Symptom: preflight fails, resume is required, or WSL/Docker checks block install
- Diagnostic:

```powershell
.\install-hatch.cmd -CheckOnly
.\install-hatch.cmd -CheckOnly -Json
```

- Recovery: follow the exact prerequisite action, then rerun with `-Resume`

## Update Failure

- Symptom: `hatch update` refuses to run
- Likely cause: unmanaged checkout or uncommitted changes
- Diagnostic:

```bash
git status --short
hatch update --dry-run
```

- Recovery: clean the managed checkout or update manually
