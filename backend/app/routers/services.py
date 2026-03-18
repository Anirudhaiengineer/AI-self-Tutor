from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas_chat import ChatRequest

router = APIRouter(prefix="/services", tags=["services"])


@router.get("/status")
def get_service_status(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return pipeline.snapshot()


@router.post("/start")
def start_recording(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return {
        "message": "Recording started",
        "services": pipeline.start_recording(),
    }


@router.post("/stop")
def stop_recording(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return {
        "message": "Recording stopped",
        "services": pipeline.stop_recording(),
    }


@router.get("/transcripts")
def get_recent_transcripts(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return {"items": pipeline.recent_transcripts()}


@router.get("/summary")
def get_transcript_summary(request: Request) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return pipeline.summarize_transcripts()


@router.post("/chat")
def chat_with_transcript(request: Request, payload: ChatRequest) -> dict[str, object]:
    pipeline = request.app.state.audio_pipeline
    return pipeline.answer_question(payload.message)
