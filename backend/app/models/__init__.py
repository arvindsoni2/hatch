"""ORM models package — import all models so Alembic can detect them."""
from .job import JobPosting, ScrapeLog  # noqa: F401
from .application import Application, InterviewRound, FollowUp  # noqa: F401
from .activity import ActivityLog  # noqa: F401
from .document import GeneratedDocument  # noqa: F401
from .document_asset import GeneratedDocumentAsset  # noqa: F401
from .coach_session import CompanyResearch, InterviewSession, SessionQuestion, SessionRecording  # noqa: F401
from .recruiter import RecruiterContact  # noqa: F401
from .follow_up_email import FollowUpEmail  # noqa: F401
from .agency_reputation import AgencyReputation  # noqa: F401
from .agent_event import AgentEvent  # noqa: F401
from .agent_state import AgentState  # noqa: F401
from .job_score import JobScore  # noqa: F401
from .story import Story, StoryUsage  # noqa: F401
from .cost_tracking import CostTracking  # noqa: F401
from .async_job import AsyncJob  # noqa: F401
from .application_score_snapshot import ApplicationScoreSnapshot  # noqa: F401
from .application_outcome import ApplicationOutcome  # noqa: F401
from .opportunity_score import OpportunityScore  # noqa: F401
from .app_lock import AppLockConfig, AppLockSession  # noqa: F401
from .tailoring_review import TailoringReview  # noqa: F401
from .company_watchlist import CompanyWatchlistItem, WatchlistScanRun, DiscoveredRoleFingerprint  # noqa: F401
from .question_bank import QuestionBankItem  # noqa: F401

__all__ = [
    "JobPosting", "ScrapeLog", "Application", "InterviewRound", "FollowUp",
    "ActivityLog", "GeneratedDocument", "GeneratedDocumentAsset",
    "CompanyResearch", "InterviewSession", "SessionQuestion", "SessionRecording",
    "RecruiterContact", "FollowUpEmail", "AgencyReputation",
    "AgentEvent", "AgentState", "JobScore",
    "Story", "StoryUsage", "CostTracking",
    "AsyncJob", "ApplicationScoreSnapshot", "ApplicationOutcome", "OpportunityScore",
    "AppLockConfig", "AppLockSession",
    "TailoringReview",
    "CompanyWatchlistItem", "WatchlistScanRun", "DiscoveredRoleFingerprint",
    "QuestionBankItem",
]
