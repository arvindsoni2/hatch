"""Product-specific registrations for the generic runtime context plane."""

from app.runtime.context import ContextRegistry

from .application import ApplicationContextProvider
from .coach import CoachContextProvider
from .job import JobPostingContextProvider
from .profile import ProfileYamlContextProvider
from .resume import ResumeContextProvider

from .application import ApplicationSourceReader
from .coach import CoachSourceReader
from .job import JobSourceReader


def register_initial_context_providers(
    registry: ContextRegistry,
    *,
    job_reader: JobSourceReader,
    application_reader: ApplicationSourceReader,
    coach_reader: CoachSourceReader,
) -> None:
    """Register exactly the initial §9.2 capability vocabulary once."""
    for provider in (
        ProfileYamlContextProvider(),
        ResumeContextProvider(),
        JobPostingContextProvider(job_reader),
        ApplicationContextProvider(application_reader),
        CoachContextProvider(coach_reader),
    ):
        registry.register(provider)


__all__ = [
    "ApplicationContextProvider",
    "CoachContextProvider",
    "JobPostingContextProvider",
    "ProfileYamlContextProvider",
    "ResumeContextProvider",
    "register_initial_context_providers",
]
