"""Token budget constants for every LLM call site.

Each constant is a (prompt, max_output) pair. R2a: constants are defined and
used at call sites; the values are still decorative (not forwarded to the
model). R2b enforces them.

prompt + max_output must never exceed the server --ctx-size. Static tripwire:
assert CV_GENERATE.prompt + CV_GENERATE.max_output <= PRIMARY_CTX.
"""
from __future__ import annotations

from typing import NamedTuple


class ContextBudget(NamedTuple):
    prompt: int
    max_output: int


# Primary server --ctx-size (llm-primary: --ctx-size 16384)
PRIMARY_CTX = 16384

# Per-call budgets (prompt, max_output)
TRIAGE          = ContextBudget(1536,  256)    # scorer triage pass
SCORING         = ContextBudget(3328,  768)    # scorer detailed pass
CV_GENERATE     = ContextBudget(10240, 6000)   # cv_tailor full-CV generation; transitional until G-4
TAILORING       = ContextBudget(6656,  1536)   # reserved for G-4 per-section calls
CL_BODY         = ContextBudget(6656,  2048)   # cl_generator body
CL_SNIPPET      = ContextBudget(2048,  512)    # cl_generator snippet
JD_ANALYSIS     = ContextBudget(3328,  1024)   # jd_analyser
ATS             = ContextBudget(4096,  2048)   # ats_optimiser
COMPANY_RESEARCH = ContextBudget(3072, 2048)   # company_researcher
CV_PARSE        = ContextBudget(12288, 4096)   # cv_parser
ANSWER_EVAL     = ContextBudget(2048,  2048)   # answer_evaluator
MODEL_ANSWER    = ContextBudget(2048,  2048)   # model_answer_gen
QUESTION_GEN    = ContextBudget(4096,  4096)   # question_generator
FEEDBACK        = ContextBudget(4096,  4096)   # feedback_generator
COACH_RUBRIC    = ContextBudget(6144,  2048)   # coach rubric synthesiser
GENERIC         = ContextBudget(3072,  4096)   # LLMClient signature default
