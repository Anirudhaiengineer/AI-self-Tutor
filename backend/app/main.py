from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.learning import router as learning_router
from app.routers.services import router as services_router
from app.services.pipeline import RealtimeAudioPipeline

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    audio_pipeline = RealtimeAudioPipeline()
    app.state.audio_pipeline = audio_pipeline
    audio_pipeline.start()
    try:
        yield
    finally:
        audio_pipeline.stop()


app = FastAPI(title='Backend API', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(auth_router)
app.include_router(learning_router)
app.include_router(services_router)


@app.get('/')
def read_root() -> dict[str, str]:
    return {'message': 'FastAPI server is running'}
