# Hatch

**A self-hosted, human-in-the-loop workspace for job search, applications, and interview preparation.**

Hatch helps you find roles, score them against your profile, prepare grounded curriculum vitae (CV) and cover-letter packs, track applications, and prepare for interviews. It runs on your machine, keeps your data local by default, and never submits an application without you.

<p align="center">
  <img src="docs/visual-evidence/readme/today-ready.png" alt="Hatch Today screen showing roles ready for review" width="100%">
</p>

## Why Hatch

Job hunting turns into repeated admin: search boards, compare roles, adapt your CV, track each application, and prepare for interviews. Hatch automates the repeatable work while keeping every external action under your control.

- **Scout** discovers roles from enabled sources
- **Scorer** ranks roles against your profile and preferences
- **Tailor** prepares evidence-grounded CV and cover-letter packs
- **You review and apply** on the employer site
- **Coach** creates structured interview preparation

```mermaid
flowchart LR
    A[Scout finds roles] --> B[Scorer ranks matches]
    B --> C{Worth pursuing?}
    C -->|Yes| D[Tailor prepares CV pack]
    C -->|Not yet| E[Park for later]
    D --> F[Human review]
    F --> G[Apply externally]
    G --> H[Track application]
    H --> I[Coach prepares interview]
```

## Product walkthrough

This walkthrough follows the main Hatch workflow from first setup to interview preparation.

### Start with your profile

Onboarding captures your target market, role titles, compensation preferences, eligibility, skills, CV, artificial intelligence (AI) provider choice, and job-board preferences.

<p align="center">
  <img src="docs/visual-evidence/readme/onboarding.png" alt="Hatch onboarding market and profile setup screen" width="82%">
</p>

### See what needs attention

**Today** prioritizes the next useful action. It highlights roles ready for review, recent agent activity, follow-ups, and preparation work.

<p align="center">
  <img src="docs/visual-evidence/readme/today-ready.png" alt="Hatch Today screen with roles ready for review" width="100%">
</p>

### Review roles before generation

**Pipeline** shows roles while Hatch discovers, scores, and prepares them. You review the match evidence before generating a CV pack.

<p align="center">
  <img src="docs/visual-evidence/readme/pipeline.png" alt="Hatch Pipeline screen with scored roles" width="100%">
</p>

### Track the application journey

**Applications** tracks roles through the real application lifecycle:

`Saved -> Discovered -> Preparing -> Ready to apply -> Applied -> Interview -> Offered -> Accepted`

Cards can be moved by drag-and-drop or with the keyboard-accessible **Move to...** menu. Hatch blocks invalid backward transitions and uses explicit close actions for rejected, withdrawn, and declined outcomes.

<p align="center">
  <img src="docs/visual-evidence/readme/applications.png" alt="Hatch Applications Kanban board" width="100%">
</p>

### Prepare an evidence-led CV pack

**CV Studio** compares the job description with your confirmed master CV, surfaces evidence, and generates a reviewable CV and cover letter. Hatch is designed not to invent experience.

<p align="center">
  <img src="docs/visual-evidence/readme/cv-studio.png" alt="Hatch CV Studio tailoring screen" width="100%">
</p>

### Prepare for interviews

**Interview Prep** supports application-linked and manual sessions, reusable answers in the Question Bank, role-specific questions, model answers, calendar export, and practice workflows.

<p align="center">
  <img src="docs/visual-evidence/readme/interview-prep.png" alt="Hatch Interview Prep screen" width="100%">
</p>

## Key capabilities

Hatch combines job discovery, document tailoring, and application tracking in one local workspace:

| Area | What Hatch includes |
|---|---|
| Discovery | Scheduled job discovery, deduplication, company watchlists, and public job URL import |
| Matching | Profile-based scoring, shortlist thresholds, evidence, and rationale |
| CV Studio | Master-CV management, ATS-safe DOCX templates, tailoring review, quality gates, and document history |
| Applications | Kanban lifecycle, manual entries, follow-ups, outcomes, and interview hand-off |
| Interview Prep | Company research, likely questions, Question Bank, model answers, voice practice, and optional advanced coaching |
| AI choice | Start without AI, use bundled local `llama.cpp` services, or configure a supported cloud provider |
| Privacy | Self-hosted data, local app lock, protected product APIs, and host-managed provider secrets |

## Install Hatch

Hatch uses Docker Compose for the application stack. On supported Linux systems, the managed installer can install Docker Engine with explicit consent, then starts the lightweight profile and lets you configure AI later.

### Windows — recommended

1. Confirm Docker Desktop can run Linux containers on your machine.
2. Download `install-hatch.cmd` from this repository.
3. Double-click it.
4. Follow the readiness report.
5. Open <http://localhost:3000>.

The Windows installer supports Windows PowerShell 5.1 and PowerShell 7, so most users do not need to install PowerShell separately. It checks Docker Desktop, WSL 2 readiness, Docker Compose, Git, Python, ports, disk space, network access, and existing Hatch state before changing the machine.

Run a non-mutating check from a terminal with:

```powershell
.\install-hatch.cmd -CheckOnly
```

For Docker/WSL recovery steps and diagnostic output, read the [Windows install guide](docs/getting-started/WINDOWS_INSTALL.md).

### Linux and macOS

```bash
curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
```

Automatic Docker installation supports Ubuntu 22.04/24.04, Debian 12/13, and Fedora 43/44. Fedora 42 and other distributions use the manual Docker path. Docker Desktop installation remains manual on macOS.

For unattended Linux installation:

```bash
curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh \
  | bash -s -- \
      --non-interactive --yes --install-docker --allow-docker-group \
      --mode ai-later --backend-profile core
```

The installer rejects whole-script root execution. Run it as your normal user; it requests narrowly scoped `sudo` access when approved. Membership in the docker group grants root-level privileges and requires the separate `--allow-docker-group` consent. Docker also creates networking and firewall rules for published ports; Hatch does not weaken host firewall policy.

Use `--check-only` for a strictly read-only readiness report, `--json` for schema-versioned machine output, or `--resume` after a safe incomplete phase. `--check-only` and `--resume` cannot be combined.

### Windows — advanced terminal install

```powershell
iwr https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.ps1 | iex
```

Local script examples:

```powershell
.\install-hatch.cmd -InstallDir "D:\Apps\Hatch"
.\install-hatch.cmd -Mode cloud -BackendProfile core
.\install-hatch.cmd -CheckOnly -Json
.\install-hatch.cmd -Resume
.\install.ps1 -Mode advanced -BackendProfile full
```

Open <http://localhost:3000>, create the local app-lock password, and complete onboarding.

Common host commands:

```bash
hatch status
hatch doctor
hatch probe
hatch models list
hatch models install --primary <catalog-id> --triage <catalog-id>
hatch apply-ai-config
hatch provider test <provider>
hatch capabilities status
hatch capabilities enable browser
hatch capabilities enable local-embeddings
hatch capabilities enable full
hatch capabilities disable
```

The canonical sanitized hardware snapshot is `${HATCH_HOME}/probe/hardware_probe_latest.json`. The backend receives that directory through a dedicated read-only mount.

Non-interactive Local mode runs the probe and records Local intent, but downloads no model and remains pending until explicit catalog model IDs are selected.

Linux/macOS advanced capability example:

```bash
./install.sh --mode advanced --backend-profile full
```

For manual Docker setup, capability profiles, troubleshooting, reset commands, and development checks, read the [Hatch operations guide](docs/operations/OPERATIONS.md).

## AI and capability choices

AI routing and Hatch capabilities are separate choices. Choose **None**, **Local**, or **Cloud** for AI. Choose **Standard Hatch** (the default), Core + browser, Core + local embeddings, or Full capabilities independently. Hatch can start with AI configuration deferred; profile editing, manual application tracking, settings, and job entry remain available.

### Local AI

After `hatch probe`, the setup screen requests a curated live catalogue from Hugging Face, filters it by publisher, family, licence, immutable revision, checksum metadata, RAM, and free disk, and falls back to a pinned catalogue if the service is unavailable. Nothing downloads until you explicitly assign both routes and confirm:

```bash
hatch models list
hatch models install --primary <catalog-id> --triage <catalog-id>
hatch apply-ai-config --restart
```

Downloads use `.part` files, SHA-256 verification, and a local verification manifest. Network or rate-limit failures leave setup pending and do not replace an existing verified model.

The root `docker-compose.yml` is the developer-stack exception and intentionally keeps a pinned test pair:

| Service | Default model | Port | Main purpose |
|---|---|---:|---|
| `llm-primary` | Qwen3.5-4B Q4_K_M | 8080 | Detailed scoring, CV packs, and Coach |
| `llm-triage` | Qwen3.5-0.8B Q8_0 | 8081 | Fast relevance filtering |

Easy-install Compose has no model filename defaults. Model services start only after Local is selected, both routes are verified, and the host configuration is applied. Services bind to localhost.

### Cloud AI

Cloud providers are optional. Easy-install secrets stay outside the browser and repository:

```bash
hatch secrets set openai
hatch provider test openai
hatch secrets status
hatch secrets unset openai
```

Cloud mode routes both primary and triage work to the selected provider-hosted models and does not start or download local model services. Provider testing is explicit and may make a small billable request; background status polling never calls a provider.

## Privacy and safety

Hatch is designed around a strict trust boundary:

- Hatch never submits applications automatically
- Generated documents require human review
- App lock protects the workspace and product APIs
- Sessions use an HttpOnly cookie and expire server-side
- Personal files, databases, generated documents, recordings, and models under `data/` are gitignored
- Cloud AI is used only after you configure a provider
- DOCX remains the source of truth for generated CVs

To reset a forgotten database-backed app-lock password without deleting job data:

```bash
bash scripts/reset-app-lock.sh
```

## Documentation

See the [Hatch documentation index](docs/README.md) for current user, operations, architecture, development, and historical documentation.

- Installation: [docs/getting-started/INSTALLATION.md](docs/getting-started/INSTALLATION.md)
- Architecture: [docs/architecture/OVERVIEW.md](docs/architecture/OVERVIEW.md)
- Operations: [docs/operations/OPERATIONS.md](docs/operations/OPERATIONS.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)

## Repository structure

The repository is split by application surface and operational responsibility:

```text
backend/        FastAPI services, agents, persistence, and document workflows
frontend/       Next.js application, Vitest tests, and Playwright tests
data/           Local profile, database, documents, and model state
locales/        Market-specific configuration
scripts/        Installation, maintenance, model, and recovery scripts
docs/           User, architecture, operations, development, reference, and historical documentation
```

## Current boundaries

These constraints are intentional for the current release:

- Hatch does not auto-apply or automate recruiter messaging
- Job-board reliability depends on public access, site changes, rate limits, and enabled capabilities
- Browser CV preview is approximate because DOCX is the document source of truth
- Local model quality and speed depend on the machine and model selected
- PDF export stays capability-gated and unavailable unless a safe converter is configured

## Development

Start with the operations guide, then use the project checks that match your change:

```bash
make help
make test
make lint
docker compose config --quiet
```

Frontend checks:

```bash
cd frontend
npm ci
npm run type-check
npm test
npm run test:e2e
```

Backend checks:

```bash
cd backend
python -m pytest
```

## Contributing

Issues and focused pull requests are welcome. Changes should preserve the core Hatch boundary: the system may assist, prepare, and recommend, but you approve every external action.

## Release Notes And Governance

- License: [MIT](LICENSE)
- Changes: [CHANGELOG.md](CHANGELOG.md)
- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reporting: [SECURITY.md](SECURITY.md)
- Release checklist: [docs/operations/RELEASE_CHECKLIST.md](docs/operations/RELEASE_CHECKLIST.md)
- Operational details: [docs/operations/OPERATIONS.md](docs/operations/OPERATIONS.md)
