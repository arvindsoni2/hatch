# PR4 production prompt and skill audit: root cause

## Scope

PR4 applies the shared writing-safety contracts to every production AI task according to risk. Test-only prompt strings and archived specifications are excluded.

## Discovery

Production prompt assembly is split across three mechanisms:

- 15 Jinja templates under `backend/app/prompts/`;
- inline prompt builders in `scorer_agent.py`, `cl_generator.py`, `rubric_synthesiser.py`, and `email_generator.py`;
- seven progressively disclosed skills under `backend/app/skills/`.

Only CV tailoring and cover-letter generation currently expose stable runtime prompt metadata and shared factuality/numeric contracts. Other structured tasks generally parse JSON or Pydantic output, but their prompt versions, evidence boundaries, provenance expectations, and safe missing-evidence behavior are inconsistent.

## High-risk gaps

- Job extraction asks for structured fields but does not post-check salary, IR35, duration, or location values against the supplied JD.
- Job scoring trusts the model-provided weighted total and narrative without a shared evidence contract.
- Company research discards source URLs/timestamps and fabricates a generic company description when retrieval or synthesis fails.
- Interview model answers receive an unstructured summary rather than approved evidence IDs and are not checked for invented metrics.
- Question generation does not map questions to stable job-requirement IDs or deduplicate semantic repeats.
- CV parsing grounds some fields but does not validate every normalized field or malformed top-level output.
- Coach and recommendation prompts do not consistently separate observation, interpretation, and recommendation.
- Job classification contains a hard-coded candidate profile rather than runtime profile data.
- Candidate-facing email prompts contain hard-coded candidate claims and have no output factuality or numeric validation.

## Root cause

The repository has good service-specific schemas and several local grounding checks, but it lacks one inventory and contract boundary spanning all production prompts. As a result, safety behavior depends on the individual prompt author, and no test detects an uncataloged or unversioned production prompt.

## Remediation boundary

PR4 introduces a metadata/risk catalog and a synchronized checked-in audit, then migrates high-risk prompt families using existing evidence, numeric, Pydantic, and skill frameworks. It does not add another prompt loader, change model routing/defaults, persist failed content, or redesign public APIs.
