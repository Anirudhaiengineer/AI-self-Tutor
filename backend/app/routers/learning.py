from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas_learning import LearningPlanAcceptRequest, LearningPlanCreateRequest, LearningSlotActionRequest
from app.services.learning_plan import LearningPlanService

router = APIRouter(prefix='/learning', tags=['learning'])
service = LearningPlanService()


@router.post('/plan')
def create_learning_plan(payload: LearningPlanCreateRequest) -> dict[str, object]:
    try:
        return service.create_plan(
            payload.email,
            payload.goal,
            schedule_type=payload.schedule_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get('/plan/{email}')
def get_learning_plan(email: str) -> dict[str, object]:
    plan = service.get_plan(email)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No learning plan found for today')
    return plan


@router.post('/accept')
def accept_learning_plan(payload: LearningPlanAcceptRequest) -> dict[str, object]:
    plan = service.accept_plan(payload.email)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No learning plan found for today')
    return plan


@router.post('/slot-action')
def apply_learning_slot_action(payload: LearningSlotActionRequest) -> dict[str, object]:
    plan = service.apply_slot_action(payload.email, payload.slot_id, payload.action)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Learning slot not found')
    return plan
