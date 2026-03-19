from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class LearningPlanCreateRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    goal: str = Field(min_length=5, max_length=500)
    schedule_type: Literal['short', 'long'] = 'short'
    start_date: date | None = None
    end_date: date | None = None
    diagnostic_profile: dict[str, object] | None = None


class LearningPlanAcceptRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class LearningSlotActionRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    slot_id: str = Field(min_length=1, max_length=100)
    action: str = Field(pattern='^(complete|continue|postpone)$')


class DiagnosticStartRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    goal: str = Field(min_length=5, max_length=500)


class DiagnosticAnswerRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=120)
    answer: str = Field(min_length=1, max_length=1000)
