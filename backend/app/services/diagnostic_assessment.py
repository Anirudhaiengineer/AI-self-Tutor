from __future__ import annotations

import json
import os
import re
from datetime import datetime
from statistics import mean
from uuid import uuid4

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from app.database import diagnostic_sessions_collection

STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'have', 'how', 'i', 'in', 'is',
    'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'was', 'what', 'when', 'where', 'which', 'who', 'why',
    'will', 'with', 'you', 'your', 'can', 'could', 'should', 'would', 'do', 'does', 'did', 'about', 'into',
    'we', 'they', 'their', 'our', 'there', 'here', 'been', 'being', 'more', 'most', 'less', 'very', 'please',
}


class DiagnosticAssessmentService:
    def __init__(self) -> None:
        self.model = os.getenv('HF_CHAT_MODEL', 'openai/gpt-oss-20b')
        self.base_url = os.getenv('HF_BASE_URL', 'https://router.huggingface.co/v1')
        self.api_key = os.getenv('HF_TOKEN', '')
        self.client = self._build_client()

    def start(self, email: str, goal: str) -> dict[str, object]:
        questions = self._build_questions(goal)
        now = datetime.now().isoformat()
        session = {
            'session_id': uuid4().hex,
            'email': email.lower(),
            'goal': goal,
            'questions': questions,
            'current_index': 0,
            'answers': [],
            'scores': [],
            'finished': False,
            'created_at': now,
            'updated_at': now,
        }
        diagnostic_sessions_collection.insert_one(session)
        return self._view(session)

    def answer(self, session_id: str, answer: str) -> dict[str, object]:
        session = diagnostic_sessions_collection.find_one({'session_id': session_id}, {'_id': 0})
        if not session:
            return {
                'finished': True,
                'error': 'Diagnostic session not found',
            }

        if session.get('finished'):
            return self._build_finished_payload(session)

        index = int(session.get('current_index', 0))
        questions = session.get('questions') or []
        if index >= len(questions):
            session['finished'] = True
            session['updated_at'] = datetime.now().isoformat()
            diagnostic_sessions_collection.replace_one({'session_id': session_id}, session, upsert=True)
            return self._build_finished_payload(session)

        question = questions[index]
        score_data = self._score_answer(question, answer, session.get('goal', ''))
        entry = {
            'question_id': question.get('question_id'),
            'question': question.get('question'),
            'difficulty': question.get('difficulty'),
            'answer': answer.strip(),
            'score': score_data['score'],
            'feedback': score_data['feedback'],
            'matched_points': score_data['matched_points'],
            'missed_points': score_data['missed_points'],
            'created_at': datetime.now().isoformat(),
        }
        session.setdefault('answers', []).append(entry)
        session.setdefault('scores', []).append(score_data['score'])
        session['current_index'] = index + 1
        session['updated_at'] = datetime.now().isoformat()

        if session['current_index'] >= len(questions):
            session['finished'] = True
            diagnostic_sessions_collection.replace_one({'session_id': session_id}, session, upsert=True)
            return self._build_finished_payload(session)

        diagnostic_sessions_collection.replace_one({'session_id': session_id}, session, upsert=True)
        return {
            'finished': False,
            'session_id': session['session_id'],
            'question': questions[session['current_index']],
            'question_index': session['current_index'] + 1,
            'total_questions': len(questions),
            'last_score': score_data['score'],
            'feedback': score_data['feedback'],
        }

    def get_session(self, session_id: str) -> dict[str, object] | None:
        session = diagnostic_sessions_collection.find_one({'session_id': session_id}, {'_id': 0})
        if not session:
            return None
        return self._view(session)

    def _build_client(self):
        if not OpenAI or not self.api_key:
            return None
        return OpenAI(base_url=self.base_url, api_key=self.api_key)

    def _build_questions(self, goal: str) -> list[dict[str, object]]:
        fallback = self._fallback_questions(goal)
        if not self.client:
            return fallback

        prompt = '\n'.join([
            'You are a tutor building a diagnostic test before creating a study schedule.',
            'Generate exactly 3 questions that progress from easy to medium to hard for the topic.',
            'Return ONLY valid JSON with this structure:',
            '{',
            '  "questions": [',
            '    {',
            '      "difficulty": "easy",',
            '      "question": "...",',
            '      "expected_points": ["...", "..."],',
            '      "hint": "optional short hint"',
            '    }',
            '  ]',
            '}',
            'Requirements:',
            '1. Use the exact user topic.',
            '2. Easy should test definitions or simple recall.',
            '3. Medium should test explanation or comparison.',
            '4. Hard should test application or edge cases.',
            '5. Keep each question short and clear.',
            '',
            f'User topic: {goal}',
        ])

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
            )
            content = response.choices[0].message.content or ''
            parsed = self._parse_questions(content, goal)
            if parsed:
                return parsed
        except Exception:
            pass

        return fallback

    def _parse_questions(self, content: str, goal: str) -> list[dict[str, object]] | None:
        text = content.strip()
        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if match:
            text = match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        questions = data.get('questions')
        if not isinstance(questions, list) or len(questions) < 3:
            return None

        cleaned = []
        for index, item in enumerate(questions[:3], start=1):
            if not isinstance(item, dict):
                continue
            question = str(item.get('question', '')).strip()
            difficulty = str(item.get('difficulty', '')).strip().lower() or ['easy', 'medium', 'hard'][index - 1]
            expected_points = [str(point).strip() for point in item.get('expected_points', []) if str(point).strip()]
            hint = str(item.get('hint', '')).strip()
            if not question:
                continue
            cleaned.append({
                'question_id': f'q-{index}-{uuid4().hex[:6]}',
                'difficulty': difficulty,
                'question': question,
                'expected_points': expected_points[:6] or self._fallback_expected_points(goal, difficulty),
                'hint': hint,
            })

        if len(cleaned) < 3:
            return None
        return cleaned

    def _fallback_questions(self, goal: str) -> list[dict[str, object]]:
        normalized = goal.strip().rstrip('.')
        title = normalized[:1].upper() + normalized[1:] if normalized else 'the topic'
        return [
            {
                'question_id': f'q-1-{uuid4().hex[:6]}',
                'difficulty': 'easy',
                'question': f'What is {title} in simple words?',
                'expected_points': self._fallback_expected_points(goal, 'easy'),
                'hint': f'Define {title.lower()} at a basic level.',
            },
            {
                'question_id': f'q-2-{uuid4().hex[:6]}',
                'difficulty': 'medium',
                'question': f'Can you explain the main components or steps involved in {title}?',
                'expected_points': self._fallback_expected_points(goal, 'medium'),
                'hint': f'Focus on core ideas and how they connect.',
            },
            {
                'question_id': f'q-3-{uuid4().hex[:6]}',
                'difficulty': 'hard',
                'question': f'How would you apply {title} to solve a practical problem or edge case?',
                'expected_points': self._fallback_expected_points(goal, 'hard'),
                'hint': f'Use an example or scenario.',
            },
        ]

    def _fallback_expected_points(self, goal: str, difficulty: str) -> list[str]:
        tokens = self._tokenize(goal)
        core = tokens[:3] or [goal.strip() or 'the topic']
        if difficulty == 'easy':
            return [f'Basic definition of {core[0]}', 'Purpose of the concept']
        if difficulty == 'medium':
            return [f'Key parts of {core[0]}', 'How the ideas relate']
        return [f'Practical application of {core[0]}', 'Trade-offs or edge cases']

    def _score_answer(self, question: dict[str, object], answer: str, goal: str) -> dict[str, object]:
        expected_points = [str(point) for point in question.get('expected_points', []) if str(point).strip()]
        answer_text = answer.strip()
        if not answer_text:
            return {
                'score': 0.0,
                'feedback': 'No answer was provided. Try giving a short explanation in your own words.',
                'matched_points': [],
                'missed_points': expected_points,
            }

        if self.client:
            prompt = '\n'.join([
                'You are grading a student answer to a study diagnostic question.',
                'Return ONLY valid JSON with this structure:',
                '{',
                '  "score": 0 to 100,',
                '  "feedback": "short helpful feedback",',
                '  "matched_points": ["..."],',
                '  "missed_points": ["..."]',
                '}',
                'Use the expected points and the student answer to decide the score.',
                'Keep feedback encouraging and specific.',
                '',
                f'Topic: {goal}',
                f'Difficulty: {question.get("difficulty", "")}',
                f'Question: {question.get("question", "")}',
                f'Expected points: {", ".join(expected_points)}',
                f'Student answer: {answer_text}',
            ])
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{'role': 'user', 'content': prompt}],
                )
                content = response.choices[0].message.content or ''
                parsed = self._parse_score(content, expected_points)
                if parsed:
                    return parsed
            except Exception:
                pass

        tokens = set(self._tokenize(answer_text))
        expected_tokens = set(self._tokenize(' '.join(expected_points)))
        overlap = sorted(tokens & expected_tokens)
        score = min(100.0, round((len(overlap) / max(len(expected_tokens), 1)) * 100 + min(len(answer_text) / 8, 25), 2))
        feedback = 'Good start. Expand your answer with more detail.' if score >= 50 else 'You should add the basic definition and main idea.'
        matched = overlap[:5]
        missed = [point for point in expected_points if not set(self._tokenize(point)) & tokens]
        return {
            'score': score,
            'feedback': feedback,
            'matched_points': matched,
            'missed_points': missed,
        }

    def _parse_score(self, content: str, expected_points: list[str]) -> dict[str, object] | None:
        text = content.strip()
        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if match:
            text = match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        score = data.get('score')
        feedback = str(data.get('feedback', '')).strip()
        matched_points = [str(point).strip() for point in data.get('matched_points', []) if str(point).strip()]
        missed_points = [str(point).strip() for point in data.get('missed_points', []) if str(point).strip()]

        if score is None:
            return None

        try:
            score_value = float(score)
        except (TypeError, ValueError):
            return None

        return {
            'score': max(0.0, min(100.0, score_value)),
            'feedback': feedback or 'Good effort. Keep building the explanation.',
            'matched_points': matched_points[:5],
            'missed_points': missed_points[:5] or expected_points[:5],
        }

    def _build_finished_payload(self, session: dict[str, object]) -> dict[str, object]:
        answers = session.get('answers') or []
        scores = session.get('scores') or []
        average_score = round(mean(scores), 2) if scores else 0.0
        if average_score >= 75:
            proficiency_level = 'advanced'
            focus_mode = 'concept-light, application-heavy'
        elif average_score >= 50:
            proficiency_level = 'intermediate'
            focus_mode = 'balanced concept and practice'
        else:
            proficiency_level = 'beginner'
            focus_mode = 'foundations-first with more revision'

        return {
            'finished': True,
            'session_id': session['session_id'],
            'goal': session.get('goal', ''),
            'average_score': average_score,
            'proficiency_level': proficiency_level,
            'focus_mode': focus_mode,
            'summary': self._build_summary(session, average_score, proficiency_level),
            'answers': answers,
        }

    def _build_summary(self, session: dict[str, object], average_score: float, proficiency_level: str) -> str:
        goal = session.get('goal', '')
        return (
            f'The diagnostic for {goal} finished with an average score of {average_score:.0f}/100. '
            f'Based on the answers, the learner is best treated as {proficiency_level}. '
            'The upcoming schedule should match this pace and depth.'
        )

    def _view(self, session: dict[str, object]) -> dict[str, object]:
        questions = session.get('questions') or []
        index = int(session.get('current_index', 0))
        current_question = questions[index] if index < len(questions) else None
        return {
            'session_id': session.get('session_id'),
            'goal': session.get('goal', ''),
            'current_index': index,
            'total_questions': len(questions),
            'finished': bool(session.get('finished')),
            'question': current_question,
            'answers': session.get('answers', []),
            'scores': session.get('scores', []),
        }

    def _tokenize(self, text: str) -> list[str]:
        words = re.findall(r'[a-zA-Z0-9]+', text.lower())
        return [word for word in words if word not in STOP_WORDS and len(word) > 2]
