from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from uuid import uuid4

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from app.database import learning_plans_collection


class LearningPlanService:
    def __init__(self) -> None:
        self.model = os.getenv('HF_CHAT_MODEL', 'openai/gpt-oss-20b')
        self.base_url = os.getenv('HF_BASE_URL', 'https://router.huggingface.co/v1')
        self.api_key = os.getenv('HF_TOKEN', '')
        self.client = self._build_client()

    def create_plan(
        self,
        email: str,
        goal: str,
        schedule_type: str = 'short',
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, object]:
        outline = self._build_outline(goal)
        now = datetime.now().replace(second=0, microsecond=0)

        if schedule_type == 'long':
            if start_date is None or end_date is None:
                raise ValueError('Start date and end date are required for long-term schedules')
            if end_date < start_date:
                raise ValueError('End date must be on or after start date')
            calendar_entries = self._build_long_term_calendar(outline['modules'], start_date, end_date)
            plan_date = start_date.isoformat()
        else:
            calendar_entries = self._build_short_term_calendar(outline['modules'], now + timedelta(minutes=5))
            plan_date = now.date().isoformat()

        plan = {
            'email': email.lower(),
            'goal': goal,
            'schedule_type': schedule_type,
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'plan_date': plan_date,
            'accepted': False,
            'summary': outline['summary'],
            'modules': outline['modules'],
            'calendar': calendar_entries,
            'slots': calendar_entries,
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
        }

        learning_plans_collection.replace_one(
            {'email': plan['email'], 'plan_date': plan['plan_date']},
            plan,
            upsert=True,
        )
        return plan

    def get_plan(self, email: str) -> dict[str, object] | None:
        return learning_plans_collection.find_one({'email': email.lower()}, {'_id': 0}, sort=[('created_at', -1)])

    def accept_plan(self, email: str) -> dict[str, object] | None:
        plan = self.get_plan(email)
        if not plan:
            return None
        plan['accepted'] = True
        plan['updated_at'] = datetime.now().isoformat()
        learning_plans_collection.replace_one(
            {'email': plan['email'], 'plan_date': plan['plan_date']},
            plan,
            upsert=True,
        )
        return plan

    def apply_slot_action(self, email: str, slot_id: str, action: str) -> dict[str, object] | None:
        plan = self.get_plan(email)
        if not plan:
            return None

        now = datetime.now().replace(second=0, microsecond=0)
        slots = plan['slots']
        slot = next((item for item in slots if item['slot_id'] == slot_id), None)
        if not slot:
            return None

        if action == 'complete':
            slot['status'] = 'completed'
        elif action == 'continue':
            slot['status'] = 'in_progress'
            current_end = datetime.fromisoformat(slot['end_at'])
            slot['end_at'] = (current_end + timedelta(minutes=30)).isoformat()
            self._shift_following_slots(slots, slot_id, timedelta(minutes=30))
        elif action == 'postpone':
            slot['status'] = 'postponed'
            duration = datetime.fromisoformat(slot['end_at']) - datetime.fromisoformat(slot['start_at'])
            last_end = max(datetime.fromisoformat(item['end_at']) for item in slots)
            postponed_start = last_end + timedelta(minutes=15)
            postponed_end = postponed_start + duration
            slots.append({
                'slot_id': f'{slot_id}-retry-{uuid4().hex[:4]}',
                'date': slot.get('date'),
                'topic': f"{slot['topic']} (rescheduled)",
                'description': slot.get('description', ''),
                'subtopics': slot.get('subtopics', []),
                'start_at': postponed_start.isoformat(),
                'end_at': postponed_end.isoformat(),
                'estimated_minutes': slot.get('estimated_minutes', 60),
                'status': 'pending',
            })

        plan['updated_at'] = now.isoformat()
        learning_plans_collection.replace_one(
            {'email': plan['email'], 'plan_date': plan['plan_date']},
            plan,
            upsert=True,
        )
        return plan

    def _build_client(self):
        if not OpenAI or not self.api_key:
            return None
        return OpenAI(base_url=self.base_url, api_key=self.api_key)

    def _build_outline(self, goal: str) -> dict[str, object]:
        fallback = self._fallback_outline(goal)
        if not self.client:
            return fallback

        prompt = self._build_outline_prompt(goal)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
            )
            content = response.choices[0].message.content or ''
            parsed = self._parse_outline(content)
            if parsed:
                return parsed
        except Exception:
            pass

        return fallback

    def _build_outline_prompt(self, goal: str) -> str:
        return '\n'.join([
            'You are a study planner.',
            'Break the user goal into a deep learning outline with major topics and subtopics.',
            'Return ONLY valid JSON with this structure:',
            '{',
            '  "summary": "short overview",',
            '  "modules": [',
            '    {',
            '      "title": "major topic",',
            '      "description": "what this block covers",',
            '      "subtopics": ["subtopic 1", "subtopic 2"],',
            '      "estimated_minutes": 60',
            '    }',
            '  ]',
            '}',
            'Requirements:',
            '1. Create 3 to 6 modules.',
            '2. Each module should contain 2 to 5 subtopics.',
            '3. Keep module titles concise and specific.',
            '4. Use practical ordering from fundamentals to practice.',
            '5. The plan should reflect the exact goal, not generic filler.',
            '',
            f'User goal: {goal}',
        ])

    def _parse_outline(self, content: str) -> dict[str, object] | None:
        text = content.strip()
        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if match:
            text = match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        modules = data.get('modules')
        summary = (data.get('summary') or '').strip()
        if not isinstance(modules, list) or not summary:
            return None

        cleaned_modules = []
        for module in modules[:6]:
            if not isinstance(module, dict):
                continue
            title = str(module.get('title', '')).strip()
            description = str(module.get('description', '')).strip()
            subtopics = [str(item).strip() for item in module.get('subtopics', []) if str(item).strip()]
            estimated_minutes = int(module.get('estimated_minutes', 60) or 60)
            if not title:
                continue
            cleaned_modules.append({
                'title': title,
                'description': description or f'Focus on {title.lower()}',
                'subtopics': subtopics[:5] or [title],
                'estimated_minutes': max(30, min(120, estimated_minutes)),
            })

        if not cleaned_modules:
            return None

        return {
            'summary': summary,
            'modules': cleaned_modules,
        }

    def _fallback_outline(self, goal: str) -> dict[str, object]:
        normalized_goal = goal.strip().rstrip('.')
        keywords = [part.strip() for part in re.split(r',|;| and | then | after ', normalized_goal) if part.strip()]
        if not keywords:
            keywords = [normalized_goal]

        modules = []
        for index, keyword in enumerate(keywords[:5], start=1):
            title = keyword[:1].upper() + keyword[1:] if keyword else f'Topic {index}'
            modules.append({
                'title': title,
                'description': f'Build understanding of {title.lower()} from basics to practice.',
                'subtopics': [
                    f'{title} fundamentals',
                    f'{title} core ideas',
                    f'{title} practice questions',
                ],
                'estimated_minutes': 60,
            })

        if not modules:
            modules = [{
                'title': normalized_goal[:1].upper() + normalized_goal[1:],
                'description': f'Explore {normalized_goal.lower()} in depth.',
                'subtopics': [normalized_goal],
                'estimated_minutes': 60,
            }]

        return {
            'summary': f'Focus on {normalized_goal} with conceptual understanding, examples, and practice.',
            'modules': modules,
        }

    def _build_short_term_calendar(self, modules: list[dict[str, object]], start_time: datetime) -> list[dict[str, object]]:
        slots = []
        current_start = start_time

        for index, module in enumerate(modules, start=1):
            duration_minutes = int(module.get('estimated_minutes', 60) or 60)
            end_time = current_start + timedelta(minutes=duration_minutes)
            slots.append({
                'slot_id': f'slot-{index}-{uuid4().hex[:6]}',
                'date': current_start.date().isoformat(),
                'topic': module['title'],
                'description': module.get('description', ''),
                'subtopics': module.get('subtopics', []),
                'estimated_minutes': duration_minutes,
                'start_at': current_start.isoformat(),
                'end_at': end_time.isoformat(),
                'status': 'pending',
            })
            current_start = end_time + timedelta(minutes=10)

        return slots

    def _build_long_term_calendar(self, modules: list[dict[str, object]], start_date: date, end_date: date) -> list[dict[str, object]]:
        slots = []
        current_date = start_date
        module_index = 0
        total_days = (end_date - start_date).days + 1

        while current_date <= end_date:
            module = modules[module_index % len(modules)]
            day_start = datetime.combine(current_date, datetime.min.time()).replace(hour=9, minute=0)
            duration_minutes = int(module.get('estimated_minutes', 60) or 60)
            if total_days > len(modules):
                duration_minutes = max(45, min(120, duration_minutes))
            day_end = day_start + timedelta(minutes=duration_minutes)
            slots.append({
                'slot_id': f'calendar-{current_date.isoformat()}-{uuid4().hex[:6]}',
                'date': current_date.isoformat(),
                'topic': module['title'],
                'description': module.get('description', ''),
                'subtopics': module.get('subtopics', []),
                'estimated_minutes': duration_minutes,
                'start_at': day_start.isoformat(),
                'end_at': day_end.isoformat(),
                'status': 'pending',
            })
            current_date += timedelta(days=1)
            module_index += 1

        return slots

    def _shift_following_slots(self, slots: list[dict[str, object]], slot_id: str, delta: timedelta) -> None:
        shift_started = False
        for item in slots:
            if item['slot_id'] == slot_id:
                shift_started = True
                continue
            if shift_started and item['status'] != 'completed':
                item['start_at'] = (datetime.fromisoformat(item['start_at']) + delta).isoformat()
                item['end_at'] = (datetime.fromisoformat(item['end_at']) + delta).isoformat()
