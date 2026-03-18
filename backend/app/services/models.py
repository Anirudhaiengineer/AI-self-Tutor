from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class AudioChunk:
    raw_data: bytes
    sample_rate: int
    sample_width: int
    channels: int
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class TranscriptResult:
    text: str
    source: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
