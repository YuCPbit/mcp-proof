"""Behavior-regression lane: golden fixtures, provenance, replayable drift detection."""

from .ci_template import github_action_yaml
from .recorder import is_destructive, record
from .replayer import DriftResult, replay, summarize
from .sampler import sample_args

__all__ = [
    "is_destructive",
    "record",
    "replay",
    "summarize",
    "DriftResult",
    "sample_args",
    "github_action_yaml",
]
