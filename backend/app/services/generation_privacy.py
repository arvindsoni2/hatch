"""Request-scoped metadata capture for migrated generation workflows."""

from contextlib import contextmanager
from contextvars import ContextVar

metadata_only = ContextVar("generation_metadata_only", default=False)


@contextmanager
def metadata_capture():
    token = metadata_only.set(True)
    try:
        yield
    finally:
        metadata_only.reset(token)
