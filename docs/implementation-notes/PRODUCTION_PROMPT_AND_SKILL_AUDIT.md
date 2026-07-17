# Production Prompt and Skill Audit

This is the canonical PR4 inventory for production AI prompts and progressively disclosed skills. Every migration listed below is completed in PR4 and linked to focused regression coverage.

## Prompt inventory

| ID | Path | Owner/family | Inputs | Output schema | Candidate risk | Employer risk | Numeric risk | Current validation | Completed migration | Version | Focused coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `answer_evaluation` | `backend/app/prompts/answer_evaluation.j2` | Coach / evaluation | Question, transcript, metrics, reference answer | `AnswerEvaluation` | High | None | Low | Pydantic parsing and score clamps | Metadata; observation/interpretation/recommendation separation; transcript evidence | 1.0.0 | `test_answer_evaluator.py`, `test_coach_prompt_contracts.py` |
| `ats_keywords` | `backend/app/prompts/ats_keywords.j2` | ATS scoring | CV, evidence bank, JD keywords | `ATSScoreResult` | High | None | High | Pydantic plus grounded retry | Shared contracts and metadata | 1.0.0 | `test_ats_optimiser.py` |
| `cover_letter_generation` | `backend/app/prompts/cl_generation.j2` | Candidate document | Evidence ledger, content plan, JD, personal details | `CoverLetterResult` | High | High | High | Structured workflow gates and bounded repair | Complete in PR3; retain contract | 2.0.0 | `test_cl_generator.py` |
| `company_research` | `backend/app/prompts/company_research.j2` | Company research | Search snippets, company, sector | `CompanyResearchResponse` | None | High | High | Pydantic response only | Source IDs, URLs, timestamps, verification state, no invented fallback | 1.0.0 | `test_company_researcher.py` |
| `cv_parsing` | `backend/app/prompts/cv_parsing.j2` | CV import | Raw extracted CV text | `CVParseResult` | High | None | High | Partial substring/numeric checks | Full shape/field grounding, ambiguity warnings, metadata | 1.0.0 | `test_cv_parser.py` |
| `cv_tailoring` | `backend/app/prompts/cv_tailoring.j2` | Candidate document | Master CV evidence, JD analysis | `TailoredCVResult` | High | Low | High | Shared contracts and structural/fabrication gates | Complete in PR2; retain contract | 2.0.0 | `test_cv_tailor.py` |
| `follow_up_question` | `backend/app/prompts/follow_up.j2` | Interview questions | Question, transcript, weak dimension | `FollowUpQuestion` | Low | None | None | JSON parsing | Metadata and observation/recommendation labels | 1.0.0 | `test_coach_prompt_contracts.py` |
| `jd_analysis` | `backend/app/prompts/jd_analysis.j2` | Job extraction | Raw JD | `JDAnalysisResult` | None | High | High | Pydantic parsing | Explicit/inferred/absent rules and source grounding | 1.0.0 | `test_jd_analyser.py` |
| `job_classification` | `backend/app/prompts/job_classification.j2` | Job ranking | Job batch, runtime candidate profile | `JobClassificationBatch` | High | High | High | JSON parse only | Runtime profile, enum/ID/score validation, no eligibility assumptions | 1.0.0 | `test_job_classifier.py` |
| `model_answer` | `backend/app/prompts/model_answer.j2` | Interview answers | Question, approved evidence, verified research | `ModelAnswerResult` | High | Low | High | JSON parse with empty exception fallback | Evidence IDs, numeric validation, missing-evidence fallback | 1.0.0 | `test_model_answer_gen.py` |
| `question_generation` | `backend/app/prompts/question_generation.j2` | Interview questions | Role, JD requirements, verified research | `QuestionPresentationList` | High | High | Low | Item-level Pydantic parsing | Requirement IDs, semantic dedupe, no implied candidate claims | 1.0.0 | `test_question_generator.py` |
| `session_report` | `backend/app/prompts/session_report.j2` | Coach / recommendations | Deterministic scores and evaluation summaries | `SessionFeedbackReport` | High | Low | Low | Pydantic response construction | Metadata; evidence-backed observations; labelled recommendations | 1.0.0 | `test_coach_prompt_contracts.py` |
| `speech_feedback` | `backend/app/prompts/speech_feedback.j2` | Coach / recommendations | Deterministic speech metrics, transcript excerpt | `SpeechFeedback` | Low | None | Low | JSON parsing | Metadata and observation/interpretation/recommendation labels | 1.0.0 | `test_coach_prompt_contracts.py` |
| `summary_rewrite` | `backend/app/prompts/summary_rewrite.j2` | Candidate document | Current summary, JD analysis | `SummaryRewriteResult` | High | Low | High | CV tailoring post-validation | Shared contracts, approved evidence, metadata | 1.0.0 | `test_ats_optimiser.py`, `test_cv_tailor.py` |
| `video_feedback` | `backend/app/prompts/video_feedback.j2` | Coach / recommendations | Browser-estimated video metrics | `VideoFeedback` | Low | None | Low | JSON parsing and schema ranges | Metadata and estimated-observation labels | 1.0.0 | `test_coach_prompt_contracts.py` |
| `cover_letter_paragraph_regeneration` | `backend/app/services/cl_generator.py` | Candidate document | Current letter evidence, JD, instruction | `CoverLetterResult` | High | None | High | Numeric validation | Complete in PR2; catalog metadata | 2.0.0 | `test_cl_generator.py` |
| `job_scoring_triage` | `backend/app/agents/scorer_agent.py` | Job scoring | Runtime profile, job | `_TriageResult` | High | High | Low | LangChain structured output | Evidence-bounded rationale and metadata | 1.0.0 | `test_scorer_agent.py` |
| `job_scoring_detailed` | `backend/app/agents/scorer_agent.py` | Job scoring | Profile proof, preferences, job | `_ScoreResult` | High | High | High | LangChain structured output | Clamp components, deterministic total, evidence-filtered rationale | 1.0.0 | `test_scorer_agent.py` |
| `job_scoring_judge` | `backend/app/agents/scorer_agent.py` | Job scoring | Resume, profile weights, JD | `_ScoreResult` | High | High | High | LangChain structured output | Clamp components, deterministic total, evidence-filtered rationale | 1.0.0 | `test_scorer_agent.py` |
| `rubric_synthesis` | `backend/app/services/rubric_synthesiser.py` | Coach / recommendations | Transcript, deterministic rubric, delivery signals | `SessionRubric` | High | None | Low | Pydantic merge with deterministic fallback | Metadata and transcript/metric evidence validation | 1.0.0 | `test_rubric_synthesiser.py` |
| `email_post_application` | `backend/app/services/email_generator.py` | Candidate document | Application, job, runtime candidate evidence | `GeneratedEmail` | High | High | High | Pydantic output only | Remove hard-coded facts; shared contracts, metadata, numeric validation | 1.0.0 | `test_email_prompt_contracts.py` |
| `email_post_interview_thankyou` | `backend/app/services/email_generator.py` | Candidate document | Interview, job, runtime candidate evidence | `GeneratedEmail` | High | High | High | Pydantic output only | Remove hard-coded facts; shared contracts, metadata, numeric validation | 1.0.0 | `test_email_prompt_contracts.py` |
| `email_warm_reengagement` | `backend/app/services/email_generator.py` | Candidate document | Application, job, runtime candidate evidence | `GeneratedEmail` | High | High | High | Pydantic output only | Remove hard-coded facts; shared contracts, metadata, numeric validation | 1.0.0 | `test_email_prompt_contracts.py` |

## Skill inventory

| ID/path | Owning feature | Inputs | Output | Principal risk | Current validation | Completed migration | Version | Coverage |
|---|---|---|---|---|---|---|---|---|
| `backend/app/skills/ats-optimization/SKILL.md` | ATS optimisation | CV, JD keywords, evidence bank | Score and suggestions | Candidate claims | Deterministic lint plus Pydantic | Reference shared factuality/numeric contract and safe gaps | Frontmatter (unversioned) | `test_skill_injection.py`, `test_skills_inventory.py` |
| `backend/app/skills/company-research/SKILL.md` | Company research | Public sources | Research brief | Employer facts | Prompt constraints | Add source/timestamp/verification contract | Frontmatter (unversioned) | `test_company_researcher.py`, `test_skills_inventory.py` |
| `backend/app/skills/cover-letter/SKILL.md` | Cover letter | Evidence and content plan | Validated letter | Candidate/employer facts | Versioned machine contract and workflow gates | Complete in PR3 | 1.0.0 | `test_skill_loader.py`, `test_cl_generator.py` |
| `backend/app/skills/cv-tailoring/SKILL.md` | CV tailoring | Master CV and JD | Tailored CV | Candidate facts | Shared evidence/numeric contracts | Complete in PR2 | Frontmatter (unversioned) | `test_cv_tailor.py`, `test_skill_injection.py` |
| `backend/app/skills/form-mapping/SKILL.md` | Assisted apply | Profile and ATS resource | Human paste map | Personal data | Resource allowlist | Explicit missing-field/no-inference wording | Frontmatter (unversioned) | `test_skills_inventory.py` |
| `backend/app/skills/interview-prep/SKILL.md` | Interview preparation | Requirements, evidence, research | Questions and answers | Candidate/employer facts | Prompt constraints | Requirement/evidence IDs and safe missing-story fallback | Frontmatter (unversioned) | `test_question_generator.py`, `test_model_answer_gen.py` |
| `backend/app/skills/screening-answers/SKILL.md` | Assisted apply | Runtime profile fields | Clipboard answers | Eligibility/personal facts | Profile-derived rules | Explicit unknown/missing field; never infer eligibility | Frontmatter (unversioned) | `test_skills_inventory.py` |

## Exclusions

- Test fixtures and prompt strings used only by mocks.
- Historical and archived specifications.
- Deterministic non-AI helpers such as keyword extraction, local scoring, document rendering, and ATS resource mappings.
