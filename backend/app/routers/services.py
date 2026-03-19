from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas_chat import ChatRequest
from app.services.study_notes import StudyNotesService

router = APIRouter(prefix='/services', tags=['services'])
notes_service = StudyNotesService()


@router.get('/status')
def get_service_status(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return pipeline.snapshot()


@router.post('/start')
def start_recording(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return {
        'message': 'Recording started',
        'services': pipeline.start_recording(),
    }


@router.post('/stop')
def stop_recording(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return {
        'message': 'Recording stopped',
        'services': pipeline.stop_recording(),
    }


@router.get('/transcripts')
def get_recent_transcripts(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return {'items': pipeline.recent_transcripts()}


@router.get('/summary')
def get_transcript_summary(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return pipeline.summarize_transcripts()


@router.get('/notes/{email}')
def get_saved_notes(email: str, request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    notes = notes_service.refresh_notes(email, pipeline.recent_transcripts())
    return {'items': notes}


@router.post('/chat')
def chat_with_transcript(request: Request, payload: ChatRequest) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return pipeline.answer_question(payload.message)
