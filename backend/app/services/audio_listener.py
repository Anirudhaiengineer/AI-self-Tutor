from __future__ import annotations

import os
import threading
import time
from queue import Full, Queue

from app.services.models import AudioChunk

try:
    import numpy as np
except ImportError:
    np = None

try:
    import soundcard as sc
except ImportError:
    sc = None


class SystemAudioListenerService:
    def __init__(self, audio_queue: Queue[AudioChunk]) -> None:
        self.audio_queue = audio_queue
        self.sample_rate = int(os.getenv("AUDIO_SAMPLE_RATE", "44100"))
        self.chunk_seconds = float(os.getenv("AUDIO_CHUNK_SECONDS", "5"))
        self.channels = 1
        self.stt_mode = os.getenv("STT_MODE", "mock")
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._capture_enabled = threading.Event()
        self.status = "idle"
        self.last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._capture_enabled.clear()
        self._thread = threading.Thread(target=self._run, name="system-audio-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._capture_enabled.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def enable_capture(self) -> None:
        self._capture_enabled.set()
        if self.status in {"idle", "paused", "mock-paused"}:
            self.status = "running" if self._can_capture_system_audio() else "mock-running"

    def disable_capture(self) -> None:
        self._capture_enabled.clear()
        if self.status == "running":
            self.status = "paused"
        elif self.status == "mock-running":
            self.status = "mock-paused"

    def snapshot(self) -> dict[str, str | int | float | bool | None]:
        return {
            "status": self.status,
            "sample_rate": self.sample_rate,
            "chunk_seconds": self.chunk_seconds,
            "queued_chunks": self.audio_queue.qsize(),
            "capture_enabled": self._capture_enabled.is_set(),
            "last_error": self.last_error,
        }

    def _can_capture_system_audio(self) -> bool:
        return sc is not None and np is not None

    def _run(self) -> None:
        if not self._can_capture_system_audio():
            self._run_mock_capture("Install soundcard and numpy to enable real system audio capture")
            return

        try:
            speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        except Exception as exc:
            self._run_mock_capture(f"Unable to access loopback audio device: {exc}")
            return

        self.status = "paused"
        self.last_error = None
        frames_per_chunk = max(1, int(self.chunk_seconds * self.sample_rate))

        while not self._stop_event.is_set():
            if not self._capture_enabled.wait(timeout=0.5):
                continue

            try:
                with mic.recorder(samplerate=self.sample_rate) as recorder:
                    audio = recorder.record(numframes=frames_per_chunk)

                mono_channel = audio[:, 0] if getattr(audio, "ndim", 1) > 1 else audio
                pcm = (mono_channel * 32767).astype(np.int16).tobytes()
                self.audio_queue.put_nowait(
                    AudioChunk(
                        raw_data=pcm,
                        sample_rate=self.sample_rate,
                        sample_width=2,
                        channels=self.channels,
                    )
                )
                self.status = "running"
                self.last_error = None
            except Full:
                self.last_error = "Audio queue is full; dropping chunk"
            except Exception as exc:
                self.status = "error"
                self.last_error = f"Audio capture failed: {exc}"
                time.sleep(1)

    def _run_mock_capture(self, reason: str) -> None:
        self.last_error = reason
        self.status = "mock-paused" if self.stt_mode == "mock" else "degraded"

        if self.stt_mode != "mock":
            while not self._stop_event.is_set():
                time.sleep(1)
            return

        frames_per_chunk = max(1, int(self.sample_rate * self.chunk_seconds))
        silent_chunk = b"\x00\x00" * frames_per_chunk

        while not self._stop_event.is_set():
            if not self._capture_enabled.wait(timeout=0.5):
                continue

            try:
                self.audio_queue.put_nowait(
                    AudioChunk(
                        raw_data=silent_chunk,
                        sample_rate=self.sample_rate,
                        sample_width=2,
                        channels=self.channels,
                    )
                )
                self.status = "mock-running"
            except Full:
                self.last_error = "Audio queue is full; dropping mock chunk"

            time.sleep(self.chunk_seconds)
