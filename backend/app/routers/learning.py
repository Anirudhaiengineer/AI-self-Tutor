from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas_learning import (
    DiagnosticAnswerRequest,
    DiagnosticStartRequest,
    LearningPlanAcceptRequest,
    LearningPlanCreateRequest,
    LearningSlotActionRequest,
)
from app.services.diagnostic_assessment import DiagnosticAssessmentService
from app.services.learning_plan import LearningPlanService
from app.services.study_monitor import StudyMonitorService

router = APIRouter(prefix='/learning', tags=['learning'])
service = LearningPlanService()
monitor_service = StudyMonitorService(service)
diagnostic_service = DiagnosticAssessmentService()


@router.post('/diagnostic/start')
def start_diagnostic(payload: DiagnosticStartRequest) -> dict[str, object]:
    return diagnostic_service.start(payload.email, payload.goal)


@router.post('/diagnostic/answer')
def answer_diagnostic(payload: DiagnosticAnswerRequest) -> dict[str, object]:
    result = diagnostic_service.answer(payload.session_id, payload.answer)
    if result.get('finished') and result.get('error'):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(result['error']))
    return result


@router.post('/plan')
def create_learning_plan(payload: LearningPlanCreateRequest) -> dict[str, object]:
    try:
        return service.create_plan(
            payload.email,
            payload.goal,
            schedule_type=payload.schedule_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            diagnostic_profile=payload.diagnostic_profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get('/plan/{email}')
def get_learning_plan(email: str) -> dict[str, object]:
    plan = service.get_plan(email)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='No learning plan found for today')
    return plan


@router.get('/plans/{email}')
def list_learning_plans(email: str) -> dict[str, object]:
    plans = service.list_plans(email)
    return {'items': plans}


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


@router.get('/monitor/{email}')
def get_study_monitor(email: str, request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    transcripts = pipeline.recent_transcripts()
    return monitor_service.monitor(email, transcripts)

