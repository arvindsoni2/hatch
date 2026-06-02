"""ORM models package — import all models so Alembic can detect them."""
from .job import JobPosting, ScrapeLog  # noqa: F401
from .application import Application, InterviewRound, FollowUp  # noqa: F401
from .activity import ActivityLog  # noqa: F401
from .document import GeneratedDocument  # noqa: F401
from .coach_session import CompanyResearch, InterviewSession, SessionQuestion, SessionRecording  # noqa: F401
from .auto_apply import ApplicationAttempt  # noqa: F401
from .recruiter import RecruiterContact  # noqa: F401
from .follow_up_email import FollowUpEmail  # noqa: F401
from .agency_reputation import AgencyReputation  # noqa: F401
from .agent_event import AgentEvent  # noqa: F401
from .agent_state import AgentState  # noqa: F401
from .job_score import JobScore  # noqa: F401
from .story import Story, StoryUsage  # noqa: F401
from .cost_tracking import CostTracking  # noqa: F401
from .async_job import AsyncJob  # noqa: F401

__all__ = [
    "JobPosting", "ScrapeLog", "Application", "InterviewRound", "FollowUp",
    "ActivityLog", "GeneratedDocument",
    "CompanyResearch", "InterviewSession", "SessionQuestion", "SessionRecording",
    "ApplicationAttempt", "RecruiterContact", "FollowUpEmail", "AgencyReputation",
    "AgentEvent", "AgentState", "JobScore",
    "Story", "StoryUsage", "CostTracking",
    "AsyncJob",
]
