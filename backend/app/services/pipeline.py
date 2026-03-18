from __future__ import annotations

from queue import Queue

from app.services.audio_listener import SystemAudioListenerService
from app.services.models import AudioChunk
from app.services.speech_to_text import SpeechToTextService
from app.services.transcript_assistant import TranscriptAssistantService


class RealtimeAudioPipeline:
    def __init__(self) -> None:
        self.audio_queue: Queue[AudioChunk] = Queue(maxsize=10)
        self.audio_listener = SystemAudioListenerService(self.audio_queue)
        self.speech_to_text = SpeechToTextService(self.audio_queue)
        self.transcript_assistant = TranscriptAssistantService()

    def start(self) -> None:
        self.audio_listener.start()
        self.speech_to_text.start()

    def stop(self) -> None:
        self.audio_listener.stop()
        self.speech_to_text.stop()

    def start_recording(self) -> dict[str, object]:
        self.audio_listener.enable_capture()
        return self.snapshot()

    def stop_recording(self) -> dict[str, object]:
        self.audio_listener.disable_capture()
        return self.snapshot()

    def snapshot(self) -> dict[str, object]:
        return {
            'audio_listener': self.audio_listener.snapshot(),
            'speech_to_text': self.speech_to_text.snapshot(),
        }

    def recent_transcripts(self) -> list[dict[str, str]]:
        return self.speech_to_text.recent_transcripts()

    def summarize_transcripts(self) -> dict[str, object]:
        return self.transcript_assistant.summarize(self.recent_transcripts())

    def answer_question(self, question: str) -> dict[str, object]:
        return self.transcript_assistant.answer(question, self.recent_transcripts())
