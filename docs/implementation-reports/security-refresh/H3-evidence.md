# H3 evidence — files and paths

Task / spec sections / ACs: H3, spec §8 H3, §12, §14.

Baseline SHA → head SHA: `4d3d46b371a4c3d9bfff36e2ca10b449b9333980` (origin/main) → this branch, `refresh/h3-files-paths`.

OpenCode version · model ID · effort · switches: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; no model switch.

No protected spec, plan, `AGENTS.md`, `CLAUDE.md`, `opencode.json`, `.claude/`, visual-evidence or protected RED test was edited.

## Files changed

- `backend/app/services/safe_paths.py` (new) — `resolve_within`, `require_uuid`, `UnsafePathError`.
- `backend/app/services/docx_cv_builder.py` — UUID, variant and version validation; resolved paths before `mkdir`; staged paths use the helper.
- `backend/app/services/docx_cl_builder.py` — UUID, variant and version validation; resolved paths before `mkdir`.
- `backend/app/routers/coach.py` — submit-audio requires UUID session/question IDs and resolves the recordings path before `mkdir`/write. The existing safe-ID helper remains for conversational routes that import it.
- `backend/app/services/tailor_service.py` — shadow append resolves and confines the builder path before opening the archive.
- `backend/app/routers/digest.py` — time/timezone/frequency/enabled validation; shared atomic env writer.
- `backend/app/routers/settings.py` — one allow-listed atomic writer; narrowed loader; `_write_env_key` removed.
- `backend/tests/security/test_file_paths.py` (new) — H3 contract, with builder rejection cases parametrized over both builders.
- Existing tests updated only where they encoded the old slug-ID or removed-writer behavior (see “Tests updated”).
- `docs/implementation-reports/security-refresh/H3-evidence.md` — this report.

## RED

Initial run, before `safe_paths.py` existed:

```text
$ python -m pytest -q --no-cov tests/security/test_file_paths.py
ERROR collecting tests/security/test_file_paths.py
ModuleNotFoundError: No module named 'app.services.safe_paths'
1 error in 0.33s
```

After adding only the shared helper, the contract exposed the remaining defects:

```text
21 failed, 29 passed
```

The RED failures were:

| Test group | Observed failure before the fix |
|---|---|
| CV/CL builder sibling, relative, absolute, non-UUID and symlink cases | no `ValueError`; the old builder created the directory first and used a string prefix check |
| CV builder variant/version | unknown variant and string version were accepted |
| submit-audio non-UUID session | the old safe-ID regex accepted it and the route continued into media/job work |
| submit-audio `question-1` | the old safe-ID regex accepted a non-UUID question |
| shadow append outside the base | the old code opened the outside archive and appended `hatch/cv.json`; no error |
| digest invalid values | CR/LF time, `7:00`, `24:00`, unknown timezone, `weekly` and non-boolean `enabled` were written instead of returning 422 |
| digest valid update | file was not written atomically with mode 0600 |
| env loader | an unknown key was loaded into the process environment |
| env writer tests | `write_env_values` did not exist; the old `_write_env_key` was still present |

The real DOCX builder tests ran with Node available and `backend/app/templates/node_modules` installed by `npm ci`; they skip if Node or the template modules are absent.

## Guard checks (spec §12)

Each guard was disabled in turn, the matching tests were run, and the source was restored.

| Guard disabled | Matching test(s) | Result |
|---|---|---|
| `resolve_within` boundary (`is_relative_to`) | sibling-prefix and symlink tests | 2 failed |
| `resolve_within` component validation | unsafe-part parameter set | 6 failed |
| `require_uuid` | non-UUID unit, builder and submit-audio tests | 10 failed |
| CV builder variant/version checks | unknown variant and non-int version | 1 failed |
| coach session UUID check | non-UUID session submit-audio | 1 failed |
| coach question UUID check | unsafe/non-UUID question set | 4 failed |
| shadow append path check | outside-base archive test | 1 failed |
| digest field validation | invalid digest payloads | 7 failed |
| env writer allow-list and value checks | control-character/unknown-key test | 1 failed |
| env writer atomic replace | replace-failure test | 1 failed |
| env loader allow-list | unknown-key loader test | 1 failed |
| cover-letter builder guard (repair cycle 1) | seven CL builder rejection tests | 7 failed |

Restored:

```text
$ python -m pytest -q --no-cov tests/security/test_file_paths.py
62 passed
```

The mode-600 guarantee is supplied by `mkstemp` (0600) and made explicit with `os.chmod` before `os.replace`; the separate atomic-replace guard above covers the replacement behavior.

## GREEN

H3 contract:

```text
$ python -m pytest -q --no-cov tests/security/test_file_paths.py
62 passed
```

Security suite:

```text
$ python -m pytest -q --no-cov tests/security
174 passed
```

Focused H3 and neighbouring suites:

```text
$ python -m pytest -q --no-cov \
    tests/security/test_file_paths.py \
    tests/test_routers/test_settings_router.py \
    tests/test_routers/test_digest_router.py \
    tests/test_routers/test_coach_async.py \
    tests/test_routers/test_coach_router.py \
    tests/test_services/test_docx_cv_builder.py \
    tests/test_services/test_blocking_gate.py \
    tests/runtime/test_cv_tailor_lifecycle.py \
    tests/runtime/test_cv_tailor_artifacts.py \
    tests/test_services/test_coach_media_storage.py
203 passed
```

Routers and middleware:

```text
$ python -m pytest -q --no-cov tests/test_routers tests/test_middleware
572 passed
```

Full backend suite:

```text
$ python -m pytest -q --no-cov \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4306 passed, 2 skipped in 686.90s
```

The two ignored files are the known local CUDA-only suites. This full-suite result is from the original H3 cycle; repair cycle 1 did not rerun it (the requested repair checks are the H3 contract, `tests/security`, ruff and `git diff --check`).

Repository checks:

```text
$ ruff check app/ tests/
All checks passed!

$ python scripts/check_docs.py
Documentation validation passed.

$ python scripts/check_readme_contract.py
README contract passed.

$ git diff --check
exit 0
```


## Repair cycle 1

Two follow-up changes were made on the same branch:

1. The CV builder rejection tests now run against both `DocxCVBuilder` and `DocxCLBuilder` for the sibling-prefix, relative/non-UUID, absolute, symlink-escape, unknown-variant and non-int-version cases. The CL cases are selected as `[cl]` test IDs.
2. `require_uuid` now accepts only the canonical hyphenated form. Uppercase canonical input is accepted and returned lowercase; `urn:uuid:...`, braces, no-hyphen and underscore forms are rejected.

Canonical UUID RED, before the fix:

```text
$ python -m pytest -q --no-cov tests/security/test_file_paths.py -k "require_uuid_rejects"
3 failed, 9 passed
FAILED ... [urn:uuid:...]
FAILED ... [{...}]
FAILED ... [<32 hex characters>]
```

The underscore form was already rejected by `uuid.UUID`; it remains in the rejection parameter set. After the fix:

```text
$ python -m pytest -q --no-cov tests/security/test_file_paths.py -k "require_uuid"
13 passed
```

Cover-letter guard disabled (the old prefix/mkdir path was restored temporarily), then the seven new CL rejection tests were run:

```text
$ python -m pytest -q --no-cov tests/security/test_file_paths.py -k "builder_rejects and cl"
7 failed
FAILED ... test_builder_rejects_a_sibling_with_the_same_prefix_before_mkdir[cl]
FAILED ... test_builder_rejects_relative_and_non_uuid_ids_before_mkdir[cl-../x]
FAILED ... test_builder_rejects_relative_and_non_uuid_ids_before_mkdir[cl-not-a-uuid]
FAILED ... test_builder_rejects_an_absolute_id_before_mkdir[cl]
FAILED ... test_builder_rejects_a_symlink_escape_before_mkdir[cl]
FAILED ... test_builder_rejects_unknown_variant[cl]
FAILED ... test_builder_rejects_non_int_version[cl]
```

Restored:

```text
$ python -m pytest -q --no-cov tests/security/test_file_paths.py -k "builder_rejects and cl"
7 passed
```

Repair-cycle checks:

```text
$ python -m pytest -q --no-cov tests/security/test_file_paths.py
62 passed

$ python -m pytest -q --no-cov tests/security
174 passed

$ python -m pytest -q --no-cov     tests/security/test_file_paths.py     tests/test_routers/test_settings_router.py     tests/test_routers/test_digest_router.py     tests/test_routers/test_coach_async.py     tests/test_routers/test_coach_router.py     tests/test_services/test_docx_cv_builder.py     tests/test_services/test_blocking_gate.py     tests/runtime/test_cv_tailor_lifecycle.py     tests/runtime/test_cv_tailor_artifacts.py     tests/test_services/test_coach_media_storage.py
203 passed

$ ruff check app/ tests/
All checks passed!

$ git diff --check
exit 0
```

The optional shared render-argument validation function was not taken; both builders continue to use the shared `require_uuid` and `resolve_within` primitives with equivalent local checks.

Owner-approved follow-up: `backend/scripts/render_docx_check.py` called both builders with the non-UUID `synthetic-app`. It now uses one canonical UUID for the in-image render check, matching the builder contract. This file was outside H3's original list and was changed only after owner approval.

## What changed

- `resolve_within` rejects empty or NUL components, absolute paths, drive letters and backslashes; it resolves both base and candidate and requires `candidate.is_relative_to(resolved_base)`. It has no filesystem side effect.
- `require_uuid` accepts only the canonical hyphenated UUID form (case-insensitive) and returns the canonical lowercase form, or raises `ValueError` naming the field.
- CV and CL builders validate the application UUID, known variant label and non-negative integer version before any `mkdir`, then build the directory and filename with `resolve_within`. Staged CV paths use the same helper.
- Coach submit-audio requires UUID session and question IDs at the route; the recordings directory and audio filename are resolved inside the recordings base before `mkdir`. Invalid IDs keep the route’s existing 400 error shape (`{"detail": "Invalid <field>..."}`).
- Shadow append reconstructs the relative path against the builder output base, resolves it with `resolve_within`, and only then opens the ZIP archive.
- Digest updates validate first: `HH:MM` 24-hour time, `zoneinfo.ZoneInfo` timezone, `daily` frequency (the scheduler registers only the daily digest), and a real JSON boolean. Invalid values return 422 before the writer is called.
- One writer replaces the file atomically (`mkstemp`, `fsync`, `chmod 0600`, `os.replace`) and rejects keys outside the allow-list and values containing CR, LF or NUL. `_write_env_key` is deleted.
- `_load_env_file` loads only provider keys in `_KEY_PROVIDER_MAP` plus `DIGEST_TIMEZONE`, `DIGEST_TIME`, `DIGEST_FREQUENCY` and `DIGEST_ENABLED`. Other keys are ignored and logged by name only.

## Env-file key history and allow-list

Current and past writers in the repository put these keys in `data/api_keys.env`:

| Key | Source | Kept? |
|---|---|---|
| `ANTHROPIC_API_KEY` | provider map / old `_write_env_key` caller | Yes |
| `OPENAI_API_KEY` | provider map / old `_write_env_key` caller | Yes |
| `GOOGLE_API_KEY` | provider map / old `_write_env_key` caller | Yes |
| `AZURE_OPENAI_API_KEY` | provider map / old `_write_env_key` caller | Yes |
| `GOOGLE_GENAI_API_KEY` | provider map / old `_write_env_key` caller | Yes |
| `OPENROUTER_API_KEY` | provider map / old `_write_env_key` caller | Yes |
| `DIGEST_TIMEZONE` | current and past digest writer | Yes |
| `DIGEST_TIME` | current and past digest writer | Yes |
| `DIGEST_FREQUENCY` | current and past digest writer | Yes |
| `DIGEST_ENABLED` | current and past digest writer | Yes |

The old `_write_env_key` accepted an arbitrary name argument, but its only product caller validated against `_KEY_PROVIDER_MAP` before calling it. The host CLI writes `${HATCH_HOME}/config/secrets.env`, not this file. The reset-script test fixture uses a synthetic `SECRET=value` to prove preservation/clearing; it is not a product writer.

Existing lines outside the allow-list are preserved but are neither loaded nor written by the new writer. Unknown update keys are rejected.

## Path-source decisions

| Site | Path source | Decision |
|---|---|---|
| `profile_service.get_profile_path`, `save_profile`, `atomic_save_profile_raw` | `PROFILE_PATH` environment variable or the discovered fixed `data/profile.yaml`; request bodies carry profile data, not a path | No change |
| `setup_intent` / `setup.patch_intent` | `HATCH_CONFIG_DIR` setting plus fixed `ai_setup_intent.json` | No change |
| `setup.finalize_onboarding` | fixed profile path via `atomic_save_profile_raw`; request carries profile data only | No change |
| `setup_reset` | `DATA_DIR` environment variable plus fixed file and directory names | No change |
| `coach_media_storage` | configured media root plus server-generated or route-validated IDs; no raw request path segment | No change (see CodeQL section) |
| `digest.update_digest_settings` | fixed `DATA_DIR/api_keys.env` | No path helper; values validated and writer is atomic |
| DOCX builders | request `application_id` plus fixed output base | UUID check and `resolve_within` before `mkdir` |
| Coach submit-audio | request `session_id`/`question_id` plus fixed `DATA_DIR/recordings` base | UUID checks and `resolve_within` before `mkdir` |
| Tailor shadow append | builder-returned `file_path` plus builder output base | `resolve_within` before archive open |

## CodeQL alerts

Alert locations are the open alerts at the H3 baseline. Expected result after the PR scans: alerts 19–21, 31–34 and 44 close; alerts 35–43 are proposed false-positive dismissals for the owner.

| Alert | Baseline location | Disposition |
|---|---|---|
| 19, 20, 21 | `docx_cv_builder.py` lines 54, 55, 80 | Fixed by UUID validation and resolved paths before `mkdir` |
| 31, 32, 33, 34 | `coach.py` lines 662, 664, 665, 678 (old line numbers) | Fixed by UUID validation and resolved recordings paths before `mkdir`/write |
| 44 | `tailor_service.py` line 569 | Fixed by resolving the builder path inside the output base before `ZipFile`/`stat` |
| 35, 36 | `coach_media_storage.py` lines 575, 577 | Proposed false positive; dismissal reason below |
| 37, 38 | `coach_media_storage.py` lines 622, 625 | Proposed false positive; dismissal reason below |
| 39, 40, 41, 42 | `coach_media_storage.py` lines 807, 814, 820, 825 | Proposed false positive; dismissal reason below |
| 43 | `coach_media_storage.py` line 885 | Proposed false positive; dismissal reason below |

### Alerts 35–43: identifier source and no-follow control

- `_open_exact_directory` (35, 36) receives the configured `HATCH_COACH_MEDIA_ROOT`, a server-created staging directory, or a stored path created by the same module. It opens with `O_NOFOLLOW | O_DIRECTORY`, then compares `fstat` and no-follow `stat` device/inode values and the `/proc/self/fd` descriptor path.
- `_owned_child_directory` (37, 38) receives that configured root and either the literal `.uploads` or a `session_id`. The conversational route validates `session_id` with `_require_safe_id` before `resolve_owned_audio_path`; `attempt_id` and `upload_id` are also validated there. The child is created with `os.mkdir(..., dir_fd=root_fd)` and opened with `O_NOFOLLOW`.
- `publish_staged_audio` (39–42) receives a staged entry created by `_new_staged_entry` and a destination created by `resolve_owned_audio_path` or stored by the same upload flow. It links with `src_dir_fd`/`dst_dir_fd`, stats the leaf with `follow_symlinks=False`, opens it with `O_NOFOLLOW`, and verifies the published inode.
- `owned_audio_path_is_file` (43) receives a stored attempt audio path. It opens the exact parent directory with `O_NOFOLLOW` and stats the leaf with `follow_symlinks=False`; no request path segment reaches it.

Proposed dismissal reason for 35–43:

> False positive. The path components are configuration values, server-generated names, or identifiers validated to `[A-Za-z0-9_-]+` before use; no request-controlled separator or traversal segment reaches the filesystem. Directories are opened with `O_NOFOLLOW | O_DIRECTORY` and verified by descriptor and no-follow device/inode checks, and leaves are opened or statted with `dir_fd` and `O_NOFOLLOW`. The code does not follow symlinks out of the configured media root.

Dismissal is the owner’s action. No code change was made to `coach_media_storage.py`.

## Tests updated

- `backend/tests/test_routers/test_coach_async.py` — three submit-audio tests used slug session/question IDs. Changed to UUIDs because the route now requires UUIDs.
- `backend/tests/test_routers/test_coach_router.py` — legacy submit-audio and conversational tests used slug session IDs (and some non-UUID question IDs). Changed to UUIDs where the old value would be rejected before the behavior under test; the traversal test keeps its unsafe question value but uses a UUID session.
- `backend/tests/runtime/test_cv_tailor_lifecycle.py` — replaced the `app-r6` fixture ID with a UUID constant because the real builders now require a UUID application ID.
- `backend/tests/test_routers/test_settings_router.py` — the removed `_write_env_key` test now exercises the shared `write_env_values` writer. The old function no longer exists.

No unrelated assertion was weakened, skipped or deleted.

## Privacy and model calls

- No `data/`, `.env*`, real CV, real document or real key was read or printed. All fixtures are synthetic.
- No model calls were made.
- Error messages name the field but do not echo the rejected value.

## Migration

Not applicable: no schema or stored-data change.

## Not run / known limits

- The full suite excludes the two known CUDA-only test files.
- The real DOCX builder tests require Node and `backend/app/templates/node_modules`; both were available in this worktree. The tests skip with a recorded reason when either is absent.
- CodeQL alert closure cannot be confirmed until the branch is pushed and scanned. The alert mapping above is the expected result; alerts 35–43 are dismissal proposals for the owner.
- `coach_media_storage.py` was read but not changed.

Ready for review: yes.
