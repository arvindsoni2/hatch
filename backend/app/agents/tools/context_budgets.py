"""Token budget constants for every LLM call site.

Each constant is a (prompt, max_output) pair. Call sites pass max_output to
LLMClient, which forwards it to the configured model provider.

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
CV_GENERATE     = ContextBudget(10240, 3000)   # full CV JSON; source structure is restored deterministically
TAILORING       = ContextBudget(6656,  1536)   # reserved for G-4 per-section calls
CL_BODY         = ContextBudget(6656,  1024)   # 250-350 word cover letter JSON
CL_SNIPPET      = ContextBudget(2048,  512)    # cl_generator snippet
JD_ANALYSIS     = ContextBudget(3328,  768)    # compact JD analysis JSON
ATS             = ContextBudget(4096,  1024)   # ATS score and concise suggestions
COMPANY_RESEARCH = ContextBudget(3072, 2048)   # company_researcher
CV_PARSE        = ContextBudget(12288, 4096)   # cv_parser
ANSWER_EVAL     = ContextBudget(2048,  2048)   # answer_evaluator
MODEL_ANSWER    = ContextBudget(2048,  2048)   # model_answer_gen
QUESTION_GEN    = ContextBudget(4096,  4096)   # question_generator
FEEDBACK        = ContextBudget(4096,  4096)   # feedback_generator
COACH_RUBRIC    = ContextBudget(6144,  2048)   # coach rubric synthesiser
COACH_CONVERSATIONAL_EVALUATION = ContextBudget(8192, 4096)
COACH_EVIDENCE_GROUNDING = ContextBudget(8192, 4096)
COACH_COACHING = ContextBudget(6144, 2048)
GENERIC         = ContextBudget(3072,  4096)   # LLMClient signature default
