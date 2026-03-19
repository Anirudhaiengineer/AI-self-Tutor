from __future__ import annotations

from datetime import datetime
import re

from app.services.learning_plan import LearningPlanService

STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'have', 'how', 'i', 'in', 'is',
    'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'was', 'what', 'when', 'where', 'which', 'who', 'why',
    'will', 'with', 'you', 'your', 'can', 'could', 'should', 'would', 'do', 'does', 'did', 'about', 'into',
    'we', 'they', 'their', 'our', 'there', 'here', 'been', 'being', 'more', 'most', 'less', 'very',
}


class StudyMonitorService:
    def __init__(self, learning_plan_service: LearningPlanService | None = None) -> None:
        self.learning_plan_service = learning_plan_service or LearningPlanService()

    def monitor(self, email: str, transcripts: list[dict[str, str]]) -> dict[str, object]:
        plan = self.learning_plan_service.get_plan(email)
        if not plan:
            return {
                'status': 'idle',
                'score': 0.0,
                'message': 'Create a learning plan first so I can monitor the current study topic.',
                'matched_terms': [],
                'missing_terms': [],
                'active_slot': None,
                'evidence': [],
            }

        active_slot = self._current_slot(plan)
        if not active_slot:
            next_slot = self._next_slot(plan)
            return {
                'status': 'idle',
                'score': 0.0,
                'message': 'No active study slot is running right now.',
                'matched_terms': [],
                'missing_terms': [],
                'active_slot': next_slot,
                'evidence': [],
            }

        active_transcripts = self._select_transcripts_for_slot(transcripts, active_slot)
        topic_terms = self._topic_terms(plan, active_slot)
        transcript_terms = self._transcript_terms(active_transcripts)
        matched_terms = sorted(topic_terms & transcript_terms)
        missing_terms = sorted(topic_terms - transcript_terms)

        coverage = len(matched_terms) / max(len(topic_terms), 1)
        activity = min(len(active_transcripts) / 4, 1.0)
        score = round((coverage * 0.75) + (activity * 0.25), 2)

        if not active_transcripts:
            status = 'listening'
            message = (
                f'Listening for study evidence on {active_slot["topic"]}. '
                'Start discussing the topic to build the monitor score.'
            )
        elif score >= 0.55:
            status = 'focused'
            message = (
                f'The transcript is strongly aligned with {active_slot["topic"]}. '
                'The learner appears to be studying the scheduled concept.'
            )
        elif score >= 0.28:
            status = 'drifting'
            message = (
                f'The transcript partially matches {active_slot["topic"]}. '
                'Some topic terms are present, but there is room to stay more focused.'
            )
        else:
            status = 'off_topic'
            message = (
                f'The transcript is not matching {active_slot["topic"]} closely enough yet. '
                'It looks like the user may be discussing another idea.'
            )

        evidence = [item['text'] for item in active_transcripts[:4]]
        return {
            'status': status,
            'score': score,
            'message': message,
            'matched_terms': matched_terms[:10],
            'missing_terms': missing_terms[:10],
            'active_slot': active_slot,
            'evidence': evidence,
        }

    def _current_slot(self, plan: dict[str, object]) -> dict[str, object] | None:
        now = datetime.now()
        slots = plan.get('slots') or []
        for slot in slots:
            if slot.get('status') in {'completed', 'postponed'}:
                continue
            try:
                start_at = datetime.fromisoformat(str(slot.get('start_at')))
                end_at = datetime.fromisoformat(str(slot.get('end_at')))
            except (TypeError, ValueError):
                continue
            if start_at <= now < end_at:
                return slot
        return None

    def _next_slot(self, plan: dict[str, object]) -> dict[str, object] | None:
        now = datetime.now()
        upcoming = []
        for slot in plan.get('slots') or []:
            if slot.get('status') in {'completed', 'postponed'}:
                continue
            try:
                start_at = datetime.fromisoformat(str(slot.get('start_at')))
            except (TypeError, ValueError):
                continue
            if start_at >= now:
                upcoming.append((start_at, slot))
        if not upcoming:
            return None
        upcoming.sort(key=lambda pair: pair[0])
        return upcoming[0][1]

    def _select_transcripts_for_slot(
        self,
        transcripts: list[dict[str, str]],
        slot: dict[str, object],
    ) -> list[dict[str, str]]:
        try:
            start_at = datetime.fromisoformat(str(slot.get('start_at')))
            end_at = datetime.fromisoformat(str(slot.get('end_at')))
        except (TypeError, ValueError):
            return self._normalize(transcripts[-8:])

        selected = []
        for item in self._normalize(transcripts):
            created_at = item.get('created_at')
            if not created_at:
                continue
            try:
                created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except ValueError:
                continue
            if start_at <= created.replace(tzinfo=None) <= end_at:
                selected.append(item)

        if selected:
            return selected[-8:]
        return self._normalize(transcripts[-8:])

    def _topic_terms(self, plan: dict[str, object], slot: dict[str, object]) -> set[str]:
        parts = [
            str(plan.get('goal', '')),
            str(slot.get('topic', '')),
            str(slot.get('description', '')),
            ' '.join(str(item) for item in slot.get('subtopics') or []),
        ]
        return set(self._tokenize(' '.join(parts)))

    def _transcript_terms(self, transcripts: list[dict[str, str]]) -> set[str]:
        text = ' '.join(item['text'] for item in transcripts)
        return set(self._tokenize(text))

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

    def _tokenize(self, text: str) -> list[str]:
        words = re.findall(r'[a-zA-Z0-9]+', text.lower())
        return [word for word in words if word not in STOP_WORDS and len(word) > 2]
