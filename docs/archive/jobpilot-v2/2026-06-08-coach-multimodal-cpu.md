---
title: Coach Module — Multimodal Transformation (CPU-first, multilingual)
document_type: historical
status: historical
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

> [!WARNING]
> This document is retained for historical context. It does not describe the current Hatch implementation on `main`.

# Coach Module — Multimodal Transformation (CPU-first, multilingual)

**Author:** Arvind Soni
**Date:** 8 June 2026
**Repo:** https://github.com/arvindsoni2/hatch
**Status:** Spec — ready for refinement, then Claude Code execution
**Supersedes nothing; extends the existing Coach agent and services.**

---

## 1. Goal

Transform the Coach from a text-first Q&A tool into something closer to a human interview coach: it studies the CV, researches the company, runs STAR-based behavioural prep and "show-don't-tell" technical drills, **observes delivery (voice tone) and presence (facial expression/engagement)**, produces a **rubric-style improvement report**, and **schedules a follow-up session** that tracks progress over time.

## 2. Hard constraints (these drive every model choice)

1. **Hardware floor: a laptop CPU, no GPU.** Most users are job seekers across many countries who will not buy expensive hardware.
2. **Free / open source first**, with a clean switch to paid cloud providers (Anthropic, etc.) for users who want it.
3. **Multilingual.** Users span countries; defaults must not be English-only.
4. **Privacy-first, single-user, self-hosted.** Video and audio analysis must be able to run entirely on-device.
5. **Human-in-the-loop.** All signals are advisory. The coach prepares; the human decides. Nothing is auto-submitted.

## 3. The architectural split (the key decision)

| Layer | Where it runs | Cost | Why |
|-------|---------------|------|-----|
| **Perception** (ASR, voice tone, face) | 100% local, on CPU/browser | Free | Small models; async background jobs absorb CPU latency |
| **Reasoning** (rubric synthesis, model answers, follow-up plan) | Small local Ollama model (default) — pluggable to cloud | Free, local | Slow on CPU but free; UX sets the expectation. Lean on deterministic metrics so the weak LLM mostly phrases/prioritises rather than judges |
| **Voice out** (optional TTS) | Local, on CPU | Free | Piper is real-time on CPU |

**Latency is acceptable because analysis is asynchronous.** A recorded answer is submitted, processed in a background job (existing `AsyncJobService` 202 + poll pattern in `routers/coach.py`), and the result is polled. There is no live-streaming budget to meet. The slow step — local-LLM rubric synthesis — is covered by explicit "processing may take a little while on local hardware" messaging in the UI (see Phase A). To keep that step robust despite a weak local model, the deterministic delivery metrics carry the factual feedback; the LLM mainly phrases, prioritises, and writes the narrative.

**Locales.** Keep the current supported geographies and the existing `locales/*.yaml` pattern. Add a `coach.fillers` list (per-locale filler words/phrases) to each pack, with the loader falling back to a default list when absent. New geographies extend by adding a pack — no code change, exactly as today.

## 4. Locked CPU-default model stack

| Capability | CPU default (free, local) | Notes | Paid/GPU upgrade |
|-----------|---------------------------|-------|------------------|
| **Transcription + word timestamps** | `faster-whisper` (CTranslate2), `small` or `medium`, int8 quantised | 99 languages; word timestamps unlock pace/pause/filler analysis for free | Whisper large-v3 / Parakeet (GPU); Deepgram / AssemblyAI (cloud) |
| **Ultralight ASR alt** | Qwen3-ASR 0.6B | Newer (Jan 2026), 52 langs, timestamps; less mature tooling | Qwen3-ASR 1.7B |
| **Browser fallback ASR** | Web Speech API (existing) | Zero infra; Chrome/Edge; keep as low-power escape hatch | — |
| **Delivery metrics** | None — derived from transcript + timestamps | WPM, filler rate, long pauses, answer length, STAR coverage. Deterministic, explainable | — |
| **Vocal tone (dimensional)** | `audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim` (ONNX) | Continuous arousal/valence/dominance → energy/warmth/assertiveness trends | Hume AI (cloud) |
| **Vocal tone (categorical, optional)** | `emotion2vec+ base` (~90M) | 9-class, language-robust | `emotion2vec+ large` (~300M) |
| **Facial expression / engagement** | **MediaPipe Face Landmarker (in-browser, WASM)** | 52 blendshapes + head pose + eye-contact proxy; video never leaves device | EmotiEffLib (server, ONNX/CPU) → richer engagement; Hume (cloud) |
| **Reasoning (coach brain)** | Small local Ollama model (default), e.g. Phi-4 / Gemma 4 small / Qwen3 4B | Free, fully local; slow on CPU — surface processing-time messaging in the UI | Anthropic Claude / any cloud model via the same factory |
| **Coach voice (optional)** | Piper (real-time on CPU) | Quality option: Kokoro (82M, slower on CPU) | Qwen3-TTS / ElevenLabs (cloud) |

**Explicitly out of the CPU default path:** Qwen3-Omni / Qwen3.5-Omni (GPU-only, document as an advanced self-hoster option), NVIDIA Parakeet/Canary (GPU/NeMo-oriented).

## 5. Provider abstraction (mirror the LLM factory)

Today `agents/tools/llm_factory.py` reads `profile.yaml → llm` and returns provider-agnostic models. Do the same for perception. Add to `profile.yaml`:

```yaml
perception:
  asr:
    provider: faster_whisper        # faster_whisper | qwen3_asr | web_speech | deepgram
    model: small                    # small | medium | large-v3
    compute_type: int8              # int8 | int8_float16 | float32
    language: auto                  # auto-detect; or locale-driven
  voice_emotion:
    provider: audeering             # audeering | emotion2vec | hume | none
    model: wav2vec2-large-robust-12-ft-emotion-msp-dim
  face:
    provider: mediapipe_browser     # mediapipe_browser | emotiefflib | hume | none
    enabled: false                  # opt-in; see §8
  tts:
    provider: none                  # none | piper | kokoro | qwen3_tts | elevenlabs
    voice: en_GB-default
```

New module `agents/tools/perception_factory.py`:
- `get_transcriber()`, `get_voice_emotion_analyser()`, `get_face_analyser()`, `get_tts()` — each returns an object behind a small unified interface, so agent/service code never references a specific provider. Cloud providers read API keys from `.env`, identical to the LLM pattern.

## 6. Coach agent expansion (LangGraph)

**Scope this iteration: recorded answers only.** The user records an answer, the system analyses it in a background job, feedback is returned on poll. No live/real-time mock interview yet — this keeps the experiment clean and the CPU latency story simple.

Extend `agents/coach_agent.py` from `research → questions → model answers → STAR` into a full loop:

```
prep            -> research_company + generate_questions + generate_model_answers
                   + create_star_prep + (NEW) build_technical_drills
capture         -> user records an answer (audio, optionally webcam)  [async job]
analyse (fan-out)-> transcribe -> delivery_metrics + voice_emotion
                   (if face enabled) -> face/engagement summary (from browser)
fuse            -> (NEW) rubric_synthesiser  [LLM-as-judge]
report          -> emit prep_report / answer_report event
follow_up       -> (NEW) plan_followup_session (focus areas + scheduled next session)
```

- **`build_technical_drills`** (new): for technical questions, generate worked-example walkthroughs and "explain your approach out loud" prompts rather than just Q&A — the "show, don't tell" requirement.
- **`rubric_synthesiser`** (new): takes transcript + delivery metrics + tone trend + (optional) face summary and produces per-dimension scores with concrete evidence and a single "focus for next session". This is LLM-as-judge — consistent with the scoring overhaul direction.
- **`plan_followup_session`** (new): creates a linked child `coach_session` targeting the weakest 1–2 dimensions.

## 7. Rubric dimensions

Existing (`answer_evaluator.py`): content/relevance, STAR structure, depth/specificity, conciseness, impact/quantification.

Add: **delivery** (pace, fillers, pauses), **vocal confidence** (tone trend), **presence** (eye contact/engagement — only if face enabled). Every dimension shows: score band, 1–2 concrete examples pulled from the answer, and a recommended drill. Never a bare number with no evidence.

## 8. Privacy & ethics (must-do, not optional)

- **EU AI Act (effective Feb 2026):** emotion recognition in workplace/education contexts is high-risk and largely prohibited there. This tool is a single user analysing **their own** face for self-practice — materially different — but treat it carefully:
  - Face analysis is **opt-in and off by default** (`perception.face.enabled: false`).
  - Run face analysis **in the browser (MediaPipe)** so raw video never reaches the server.
  - Store only **aggregate summaries**, never raw frames; offer one-click delete.
  - Frame everything as **self-coaching**, and gate behind an explicit consent screen.
- **All emotion/expression output is a directional aggregate signal, never ground truth.** Report trends and patterns ("energy dropped in the second half"), not absolute verdicts. No single-frame labels.
- Reuse the existing local-first posture: this is exactly why on-device perception fits Hatch.

## 9. Data model

Extend `coach_session` (and add child tables as needed):
- `rubric` — JSON: per-dimension score band + evidence + recommended drill.
- `signals` — JSON summary: delivery metrics, tone trend points, face/engagement summary (if enabled). Store summaries, not raw media.
- `parent_session_id` — nullable FK for follow-up chaining.
- `focus_areas` — the 1–2 dimensions this session targets.
- Add a progress view: per-skill trend across a session chain.

Alembic migration; do not rewrite history.

## 10. Phased tasks (TDD; infra before feature)

### Phase A — Server-side ASR + deterministic delivery metrics
*Highest leverage, zero ethics concerns, fully local.*

- [ ] **Add `faster-whisper` transcriber** behind `perception_factory.get_transcriber()`.
  - WRITE TESTS FIRST — `backend/tests/test_tools/test_transcriber.py`:
    - `test_transcribe_returns_text_and_word_timestamps` (short fixture wav → non-empty text, word list with start/end)
    - `test_language_autodetect` (non-English fixture → detected language code)
    - `test_int8_model_loads_on_cpu` (model loads with `compute_type=int8`, `device=cpu`)
  - THEN IMPLEMENT `backend/app/services/transcriber.py` (wrap faster-whisper; return `{text, language, words:[{w,start,end}]}`).
  - Suggested commit: `feat(coach): local faster-whisper transcriber with word timestamps`
- [ ] **Upgrade `speech_analyser.py` to compute delivery metrics from transcript + timestamps.**
  - WRITE TESTS FIRST — `test_services/test_speech_analyser.py`:
    - `test_words_per_minute`, `test_filler_word_rate` (filler lexicon read from the active locale pack's `coach.fillers`, default fallback), `test_long_pause_detection`, `test_star_section_coverage`
  - THEN IMPLEMENT pure functions over the transcriber output (no model needed).
  - Suggested commit: `feat(coach): deterministic delivery metrics from transcript`
- [ ] **Add `coach.fillers` to each current locale pack** (`locales/*.yaml`) + loader support with a default fallback list.
  - TESTS: loader returns pack-specific fillers; falls back to default when key absent.
  - Suggested commit: `feat(coach): per-locale filler lexicons in locale packs`
- [ ] Wire transcriber into the existing async `submit_answer` job in `routers/coach.py`.
- [ ] **Processing-time UX messaging.** In the coach practice UI (existing `useAsyncJob` poll flow), add an explicit "analysing your answer — this can take a little while on local hardware" state with a progress affordance, so the slow local-LLM step never reads as a hang.
  - TESTS (Vitest/RTL): poll `running` state renders the processing message; `done` clears it.
  - Suggested commit: `feat(coach): processing-time messaging for local analysis`

### Phase B — Vocal tone + session rubric
- [ ] **Add voice-emotion analyser** (`audeering` ONNX) behind `get_voice_emotion_analyser()`.
  - TESTS: returns arousal/valence/dominance in [0,1]; handles 16kHz mono; runs on CPU.
  - Suggested commit: `feat(coach): local dimensional speech-emotion analyser`
- [ ] **Expand `answer_evaluator.py` into a session-level rubric** with the new dimensions.
  - TESTS: rubric has all dimensions; each carries evidence; missing-face dimension is omitted, not zeroed.
  - Suggested commit: `feat(coach): multi-dimensional rubric with evidence`
- [ ] **`rubric_synthesiser`** in `coach_agent.py` (LLM-as-judge via existing factory).

### Phase C — Follow-up sessions + technical drills
- [ ] Data-model migration (§9) + `plan_followup_session`.
- [ ] `build_technical_drills` (worked-example "show, don't tell" prompts).
- [ ] Progress trend endpoint + view across a session chain.
- [ ] TESTS: follow-up targets weakest dimensions; progress trend computes deltas.

### Phase D — Opt-in on-device facial / engagement
- [ ] Browser MediaPipe Face Landmarker capture in `components/coach/` (blendshapes + head pose + eye-contact proxy). Summarise client-side; POST only the summary.
- [ ] Consent screen + `perception.face.enabled` gate + delete control.
- [ ] Add `presence` dimension to rubric only when face data present.
- [ ] TESTS (frontend, Vitest/RTL): consent gate blocks capture; only summary leaves the client.

### Phase E (optional) — Coach voice (recorded flow only)
- [ ] Piper TTS behind `get_tts()`; spoken question prompts and spoken playback of feedback on a recorded answer. **No live mock interview in this iteration.**
- [ ] TESTS: TTS disabled by default; returns playable audio when enabled.

## 11. Deployment tiers (reference)

| Tier | Hardware | ASR | Tone | Face | LLM | Voice |
|------|----------|-----|------|------|-----|-------|
| **0 (default)** | CPU laptop | faster-whisper small int8 | audeering / emotion2vec-base | MediaPipe (browser) | small local Ollama (free, slow) | Piper |
| 1 | Mid GPU / Apple Silicon | faster-whisper large-v3 | audeering | EmotiEffLib | Qwen3 8–14B local | Kokoro |
| 2 (advanced) | 24GB+ GPU | Qwen3-Omni (unified) | (Omni) | EmotiEffLib / Omni | Omni / cloud | Qwen3-TTS |

Any layer in any tier swaps to a paid cloud provider through the §5 abstraction.

## 12. Model reference (CPU defaults)

| Model | Task | Size | License | Link |
|-------|------|------|---------|------|
| faster-whisper (Whisper small/medium) | ASR + timestamps | ~0.24–0.77B | MIT | https://github.com/SYSTRAN/faster-whisper |
| Qwen3-ASR 0.6B | ASR (alt) | 0.6B | Apache-2.0 | https://github.com/QwenLM/Qwen3-ASR |
| audeering wav2vec2-large-robust-12-ft-emotion-msp-dim | Voice tone (dim.) | ~0.16B | CC | https://huggingface.co/audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim |
| emotion2vec+ base | Voice tone (cat.) | ~90M | model-card | https://huggingface.co/emotion2vec/emotion2vec_plus_base |
| MediaPipe Face Landmarker | Face / engagement | tiny | Apache-2.0 | https://ai.google.dev/edge/mediapipe |
| EmotiEffLib (HSEmotion) | Face / engagement (server) | small | Apache-2.0 | https://github.com/sb-ai-lab/EmotiEffLib |
| Piper | TTS | small | MIT | https://github.com/rhasspy/piper |
| Kokoro | TTS (quality) | 82M | Apache-2.0 | https://huggingface.co/hexgrad/Kokoro-82M |

---

### Resolved decisions
1. **Reasoning:** small local Ollama model is the default — free and fully local — paired with clear "processing may take a little while" UX. Cloud (Anthropic, etc.) stays a one-field upgrade via the LLM factory. Deterministic delivery metrics (Phase A) carry the factual feedback so a weak local LLM mainly phrases and prioritises rather than judges.
2. **Scope:** recorded answers only this iteration — no live mock interview.
3. **Locales:** keep the current geographies and the existing `locales/*.yaml` pattern; add a `coach.fillers` list per pack, extensible by adding packs (no code change).

### Remaining unknown (validate during Phase A)
- Which exact small Ollama model gives an acceptable rubric on a typical CPU laptop (Phi-4 vs Gemma 4 small vs Qwen3 4B) — pick during Phase B by trialling on a real recorded answer, since this is the one quality risk the local-default choice introduces.
