"""Job sources. Each exposes fetch(ctx) -> list[Job]."""
from .base import Job, SourceContext, detect_ats, strip_html  # noqa: F401
