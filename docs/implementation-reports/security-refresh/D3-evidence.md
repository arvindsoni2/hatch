# D3 evidence — runtimes, images and the missing Node binary

Task / spec sections / ACs: D3 (runtimes and images), spec §2, §6 D3. Owner decision Q2: Node 24.

Baseline SHA → head SHA: `d41957e932d54a6cb60e868500c2b537a528ecc8` (origin/main) → this branch, `refresh/d3-runtimes-images`.

OpenCode version · model ID · effort · switches: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; no model switch.

Claude Code RED commit: not applicable (D3 is not a high-assurance task). No protected test or protected document was edited.

## Files changed

- `backend/Dockerfile` — every external base pinned by digest; Node 24 bookworm stage copies only `node` into `runtime-base`; a templates stage runs `npm ci --omit=dev` and every API target copies `app/templates/node_modules` as `appuser`.
- `backend/.dockerignore` — excludes a host `app/templates/node_modules` from the build context.
- `backend/scripts/render_docx_check.py` — synthetic CV and cover-letter render through the real builders, validating each output is a DOCX zip.
- `backend/tests/test_tools/test_docker_contract.py` — Node 24, digest pins and per-target template-module contract.
- `backend/tests/test_tools/test_observability_compose_contract.py` — expects the new collector image.
- `frontend/Dockerfile` — all stages `node:24-alpine`, digest-pinned.
- `frontend/package.json`, `frontend/package-lock.json` — `engines.node >=24`, `@types/node ^24`; no other package changed.
- `.github/workflows/ci.yml` — both setup-node steps use Node 24; a step builds the core target and runs the render check as the image user.
- `docker-compose.observability.yml` — collector 0.166.0 pinned by digest; no other compose content changed.
- `docs/implementation-reports/security-refresh/D3-evidence.md` — this report.

Commits:

1. `3bbbf64` `test(build): require Node 24 and digest-pinned images`
2. `3d99482` `build(frontend): move to Node 24`
3. `f5f2a10` `build(backend): restore Node and template modules in API images`
4. `58b2f45` `build(observability): update collector to 0.166.0`
5. `75a24eb` `ci: use Node 24 and verify the DOCX renderer`
6. this report

## Base images

| Image | Tag | Digest |
|---|---|---|
| `python:3.12-slim` | 3.12-slim | `sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b` |
| `node:24-bookworm-slim` | 24-bookworm-slim | `sha256:873f586f3794f52281bd039bf02c048a0be08fde619338f9941bad1eb6b34530` |
| `node:24-alpine` | 24-alpine | `sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5` |
| `otel/opentelemetry-collector-contrib` | 0.166.0 | `sha256:3e18fe04181de50bdd72e23ad4a4d6214b54351e63d496f1c58127cc4541ad7f` |

The collector digest is the multi-arch index (`application/vnd.docker.distribution.manifest.list.v2+json`), verified with `skopeo inspect --raw docker://docker.io/otel/opentelemetry-collector-contrib:0.166.0 | sha256sum`. The index lists `linux/amd64` and `linux/arm64` (plus 386, arm, ppc64le, riscv64 and s390x).

## RED first

`tests/test_tools/test_docker_contract.py` failed before the change:

```text
FAILED test_every_external_image_from_is_digest_pinned
FAILED test_frontend_dockerfile_uses_node_24
FAILED test_ci_uses_node_24_for_both_node_jobs
FAILED test_every_api_target_has_node_and_template_modules
4 failed, 6 passed
```

The in-image check failed on the baseline core image because the binary was gone:

```text
$ podman run --rm --entrypoint python hatch-backend:d3-baseline -c '<render check>'
FileNotFoundError: [Errno 2] No such file or directory: 'node'
exit 1
```

## Image verification

Every API target built from the changed Dockerfile and ran the render check as its default user:

| Target | Build | `id -u` | `node --version` | Render check |
|---|---|---|---|---|
| core | exit 0 | 1000 | v24.22.3 | render-ok |
| browser | exit 0 | 1000 | v24.22.3 | render-ok |
| local-ai | exit 0 | 1000 | v24.22.3 | render-ok |
| observability | exit 0 | 1000 | v24.22.3 | render-ok |
| full | exit 0 | 1000 | v24.22.3 | render-ok |

The first core build hit a transient npm `ECONNRESET`; the browser build then produced the templates stage, the remaining targets reused it, and rebuilding core succeeded. No image build failed for a code or dependency reason.

## Image sizes

`scripts/report_docker_sizes.sh` was run with `BACKEND_IMAGE=hatch-backend:d3-core` and `FRONTEND_IMAGE=hatch-frontend:d3-review`. Its image table filters repositories starting with `hatch-`, while Podman reports locally built images as `localhost/hatch-*`, so the review rows did not appear in the script output; the sizes below are the same images from `podman images`.

| Image | Baseline | Review | Change |
|---|---|---|---|
| backend core | 408 MB | 544 MB | +136 MB (Node binary) |
| frontend | 228 MB | 265 MB | +37 MB |
| backend browser | — | 1.72 GB | — |
| backend local-ai | — | 1.89 GB | — |
| backend observability | — | 572 MB | — |
| backend full | — | 3.4 GB | — |

## Collector

Trivy 0.76.2, severity `CRITICAL,HIGH`:

| Image | Result |
|---|---|
| `otel/opentelemetry-collector-contrib:0.153.0` | `Total: 40 (HIGH: 37, CRITICAL: 3)` |
| `otel/opentelemetry-collector-contrib:0.166.0` | 0 vulnerabilities |

The existing collector config validates with the new image:

```text
$ podman run --rm -v "$PWD/infrastructure/observability/otel-collector.yaml:/etc/otelcol-contrib/config.yaml:ro,z" \
    otel/opentelemetry-collector-contrib:0.166.0@sha256:3e18fe04181de50bdd72e23ad4a4d6214b54351e63d496f1c58127cc4541ad7f validate --config=/etc/otelcol-contrib/config.yaml
exit 0
```

No llama.cpp image or pin was changed, and no other compose content was edited.

## Backend

```text
$ ruff check app/ tests/
All checks passed!

$ python -m pytest -q --no-cov \
    tests/test_tools/test_docker_contract.py tests/test_services/test_docx_cv_builder.py
18 passed
```

The first full run (before installing the templates `node_modules` on the host) had 14 failures: 13 runtime CV-tailor tests failed with `Cannot find module 'docx'`, and the compose contract expected the old collector tag. After `npm ci` in `backend/app/templates` and the contract update:

```text
$ python -m pytest -q --no-cov \
    tests/runtime/test_cv_tailor_lifecycle.py tests/test_tools/test_observability_compose_contract.py
21 passed
```

Full suite:

```text
$ python -m pytest -q --no-cov tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4159 passed, 2 skipped in 857.68s
```

## Frontend

Host commands ran with Node 22.23.2; the frontend image built with Node 24.

```text
$ npm ci
exit 0

$ npm audit --audit-level=high
found 0 vulnerabilities

$ npm run type-check
exit 0

$ npm run lint
exit 0 (one pre-existing react-hooks/exhaustive-deps warning)

$ npm run build
exit 0

$ TZ=UTC npx vitest run
120 files passed, 736 tests passed
```

The first local-time full run had one failure in `ConversationSession.test.tsx` while five image render checks were running; the same file passed alone (48/48) immediately afterwards. The final local-time full run passed:

```text
$ npx vitest run
120 files passed, 736 tests passed
```

Node 24 was also exercised directly with `node:24-bookworm-slim` over a mount of the repository:

```text
$ node --version
v24.22.3

$ npx tsc --noEmit && npx next lint
exit 0 (one pre-existing react-hooks/exhaustive-deps warning)

$ npx vitest run
120 files passed, 736 tests passed
```

## Documentation

`grep` found no stated Node version in the installation docs, `README.md` or the installers, so no documentation version needed changing.

```text
$ python scripts/check_docs.py
Documentation validation passed.

$ python scripts/check_readme_contract.py
README contract passed.

$ git diff --check
exit 0
```

Model calls in tests: fake/local only; no live model calls. No `data/` or `.env*` was read.

Not run / known limits:

- `e2e/api-flows.spec.ts` was not run.
- `report_docker_sizes.sh` only sees images whose repository starts with `hatch-`; Podman's `localhost/hatch-*` names are listed separately above.
- The host frontend commands used Node 22.23.2; Node 24 is exercised by the image builds (and the container checks noted above).
- The core image grows by the Node binary (+136 MB); this is the cost of restoring the renderer.

Ready for review: yes.
