from __future__ import annotations

import os
import threading
import time
from collections import deque
from queue import Empty, Queue

import numpy as np

from app.services.models import AudioChunk, TranscriptResult

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import whisper
except ImportError:
    whisper = None


class SpeechToTextService:
    def __init__(self, audio_queue: Queue[AudioChunk]) -> None:
        self.audio_queue = audio_queue
        self.language = os.getenv("STT_LANGUAGE", "en")
        self.mode = os.getenv("STT_MODE", "whisper")
        self.whisper_model_name = os.getenv("WHISPER_MODEL", "tiny")
        self.target_sample_rate = 16000
        self.transcripts: deque[TranscriptResult] = deque(maxlen=20)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.status = "idle"
        self.last_error: str | None = None
        self._recognizer = sr.Recognizer() if sr else None
        self._whisper_model = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="speech-to-text", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def snapshot(self) -> dict[str, str | int | None]:
        return {
            "status": self.status,
            "mode": self.mode,
            "language": self.language,
            "buffered_transcripts": len(self.transcripts),
            "last_error": self.last_error,
        }

    def recent_transcripts(self) -> list[dict[str, str]]:
        return [
            {
                "text": item.text,
                "source": item.source,
                "created_at": item.created_at.isoformat(),
            }
            for item in reversed(self.transcripts)
        ]

    def _run(self) -> None:
        self.status = "running"
        while not self._stop_event.is_set():
            try:
                chunk = self.audio_queue.get(timeout=1)
            except Empty:
                continue

            try:
                transcript = self._transcribe(chunk)
                if transcript:
                    self.transcripts.append(transcript)
                    self.last_error = None
                    self.status = "running"
            except Exception as exc:
                self.status = "error"
                self.last_error = f"Speech-to-text failed: {exc}"
                time.sleep(1)
            finally:
                self.audio_queue.task_done()

    def _transcribe(self, chunk: AudioChunk) -> TranscriptResult | None:
        if self.mode == "mock":
            return TranscriptResult(
                text=f"Received {len(chunk.raw_data)} bytes of system audio at {chunk.sample_rate} Hz",
                source="mock",
            )

        if self.mode == "whisper":
            if whisper is None:
                self.status = "degraded"
                self.last_error = "Install openai-whisper to enable whisper mode"
                return None

            model = self._get_whisper_model()
            audio = np.frombuffer(chunk.raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            if audio.size == 0:
                return None

            audio = self._resample_audio(audio, chunk.sample_rate, self.target_sample_rate)
            result = model.transcribe(audio, language=self.language, fp16=False, verbose=False, condition_on_previous_text=False)
            text = result.get("text", "").strip()
            if not text:
                return None

            return TranscriptResult(text=text, source=f"whisper:{self.whisper_model_name}")

        if self.mode == "google":
            if not sr or not self._recognizer:
                self.status = "degraded"
                self.last_error = "Install SpeechRecognition to enable google STT mode"
                return None

            audio_data = sr.AudioData(chunk.raw_data, chunk.sample_rate, chunk.sample_width)
            try:
                text = self._recognizer.recognize_google(audio_data, language=self.language)
            except sr.UnknownValueError:
                return None
            except sr.RequestError as exc:
                self.status = "degraded"
                self.last_error = f"Google STT request failed: {exc}"
                return None

            return TranscriptResult(text=text, source="google")

        self.status = "degraded"
        self.last_error = f"Unsupported STT_MODE: {self.mode}"
        return None

    def _get_whisper_model(self):
        if self._whisper_model is None:
            self._whisper_model = whisper.load_model(self.whisper_model_name)
        return self._whisper_model

    def _resample_audio(self, audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        if source_rate == target_rate:
            return audio

        duration = len(audio) / float(source_rate)
        target_length = max(1, int(duration * target_rate))
        source_positions = np.linspace(0, len(audio) - 1, num=len(audio), dtype=np.float32)
        target_positions = np.linspace(0, len(audio) - 1, num=target_length, dtype=np.float32)
        return np.interp(target_positions, source_positions, audio).astype(np.float32)
