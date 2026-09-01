"""Typed adapter for local artifact-generation handlers."""

from .native import CapabilityHandler, NativeCapabilityAdapter


class ArtifactCapabilityAdapter(NativeCapabilityAdapter):
    """Names the artifact boundary while retaining the native typed contract."""

    def __init__(self, handler: CapabilityHandler) -> None:
        super().__init__(handler)
