from __future__ import annotations

from datetime import datetime
from hashlib import sha1
from uuid import uuid4

from app.database import study_notes_collection
from app.services.transcript_assistant import TranscriptAssistantService


class StudyNotesService:
    def __init__(self) -> None:
        self.transcript_assistant = TranscriptAssistantService()

    def refresh_notes(self, email: str, transcripts: list[dict[str, str]]) -> list[dict[str, object]]:
        items = self._normalize(transcripts)
        if not items:
            return self.list_notes(email)

        summary = self.transcript_assistant.summarize(items)
        transcript_hash = self._hash_transcripts(items)
        note = {
            'note_id': uuid4().hex,
            'email': email.lower(),
            'title': self._build_title(summary),
            'summary': summary['summary'],
            'keypoints': summary.get('highlights', [])[:6],
            'keywords': summary.get('keywords', [])[:8],
            'transcript_hash': transcript_hash,
            'transcript_count': len(items),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
        }

        study_notes_collection.update_one(
            {'email': note['email'], 'transcript_hash': transcript_hash},
            {'$setOnInsert': note},
            upsert=True,
        )
        return self.list_notes(email)

    def list_notes(self, email: str) -> list[dict[str, object]]:
        cursor = study_notes_collection.find({'email': email.lower()}, {'_id': 0}).sort('created_at', -1)
        return list(cursor)

    def _build_title(self, summary: dict[str, object]) -> str:
        keywords = summary.get('keywords') or []
        if keywords:
            return f"Notes on {keywords[0]}"
        return 'Listening Notes'

    def _hash_transcripts(self, transcripts: list[dict[str, str]]) -> str:
        joined = '||'.join(item['text'].strip().lower() for item in transcripts if item.get('text'))
        return sha1(joined.encode('utf-8')).hexdigest()

    def _normalize(self, transcripts: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized = []
        for item in transcripts:
            text = (item.get('text') or '').strip()
            if text:
                normalized.append({
                    'text': text,
                    'created_at': item.get('created_at', ''),
                })
        return normalized
