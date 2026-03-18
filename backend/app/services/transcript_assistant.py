from __future__ import annotations

import os
import re
from collections import Counter

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'have', 'how', 'i', 'in', 'is',
    'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'was', 'what', 'when', 'where', 'which', 'who', 'why',
    'will', 'with', 'you', 'your', 'can', 'could', 'should', 'would', 'do', 'does', 'did', 'about', 'into',
}


class TranscriptAssistantService:
    def __init__(self) -> None:
        self.model = os.getenv('HF_CHAT_MODEL', 'openai/gpt-oss-20b')
        self.base_url = os.getenv('HF_BASE_URL', 'https://router.huggingface.co/v1')
        self.api_key = os.getenv('HF_TOKEN', '')
        self.client = self._build_client()

    def summarize(self, transcripts: list[dict[str, str]]) -> dict[str, object]:
        items = self._normalize(transcripts)
        if not items:
            return {
                'summary': 'No transcript is available yet. Start recording to generate a summary.',
                'highlights': [],
                'keywords': [],
            }

        keywords = self._top_keywords(items)
        highlights = [item['text'] for item in items[:3]]
        fallback_summary = self._fallback_summary(items, keywords)

        if not self.client:
            return {
                'summary': fallback_summary,
                'highlights': highlights,
                'keywords': keywords[:8],
            }

        prompt = self._build_summary_prompt(items, keywords)
        llm_summary = self._call_llm(prompt, fallback_summary)
        return {
            'summary': llm_summary,
            'highlights': highlights,
            'keywords': keywords[:8],
        }

    def answer(self, question: str, transcripts: list[dict[str, str]]) -> dict[str, object]:
        items = self._normalize(transcripts)
        if not items:
            fallback = 'There is no transcript context yet, so I am answering from general knowledge only. Start recording if you want transcript-grounded answers too.'
            prompt = self._build_general_prompt(question)
            answer = self._call_llm(prompt, fallback) if self.client else fallback
            return {
                'answer': answer,
                'matches': [],
            }

        ranked = self._retrieve(question, items)
        summary = self.summarize(transcripts)
        matches = [item['text'] for item in ranked[:4]]
        fallback_answer = self._fallback_answer(question, summary['summary'], matches)

        if not self.client:
            return {
                'answer': fallback_answer,
                'matches': matches,
            }

        prompt = self._build_chat_prompt(question, summary['summary'], matches)
        answer = self._call_llm(prompt, fallback_answer)
        return {
            'answer': answer,
            'matches': matches,
        }

    def _build_client(self):
        if not OpenAI or not self.api_key:
            return None
        return OpenAI(base_url=self.base_url, api_key=self.api_key)

    def _call_llm(self, prompt: str, fallback: str) -> str:
        if not self.client:
            return fallback

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
            )
            content = response.choices[0].message.content
            return content.strip() if content else fallback
        except Exception:
            return fallback

    def _build_summary_prompt(self, items: list[dict[str, str]], keywords: list[str]) -> str:
        transcript_context = '\n'.join(f'- {item["text"]}' for item in items[:8])
        return '\n'.join([
            'You are a helpful transcript analyst.',
            'Use the transcript context below to write a concise but slightly detailed summary in 4 to 6 sentences.',
            'Mention the key topics and any important decisions or explanations.',
            '',
            f'Keywords: {", ".join(keywords[:8])}',
            '',
            'Transcript context:',
            transcript_context,
        ])

    def _build_chat_prompt(self, question: str, summary: str, matches: list[str]) -> str:
        match_text = '\n'.join(f'- {item}' for item in matches) if matches else 'No direct transcript match was found for this question.'
        return '\n'.join([
            'You are a helpful assistant answering questions for a transcript-based workspace.',
            'Use transcript context when it is relevant and available.',
            'If the transcript does not contain the answer, say that clearly and then answer from general knowledge.',
            'Prefer grounded transcript details when they exist, but do not refuse general conceptual questions.',
            '',
            'Summary:',
            summary,
            '',
            'Retrieved transcript excerpts:',
            match_text,
            '',
            f'User question: {question}',
        ])

    def _build_general_prompt(self, question: str) -> str:
        return '\n'.join([
            'You are a helpful assistant.',
            'There is no transcript context available yet.',
            'Answer the user from general knowledge in a clear and concise way.',
            '',
            f'User question: {question}',
        ])

    def _fallback_summary(self, items: list[dict[str, str]], keywords: list[str]) -> str:
        summary_intro = 'Recent transcript activity focuses on '
        summary_intro += ', '.join(keywords[:4]) if keywords else 'the latest recorded discussion'
        summary_intro += '. '
        summary_intro += 'Key recent lines include: '
        summary_intro += ' '.join(item['text'] for item in items[:2])
        return summary_intro.strip()

    def _fallback_answer(self, question: str, summary: str, matches: list[str]) -> str:
        answer_lines = [
            f'Question: {question}',
            f'Transcript summary: {summary}',
        ]
        if matches:
            answer_lines.append('Relevant transcript context:')
            answer_lines.extend(matches[:3])
        else:
            answer_lines.append('No direct transcript match was found, so a general answer may be needed.')
        return '\n'.join(answer_lines)

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

    def _top_keywords(self, items: list[dict[str, str]]) -> list[str]:
        counts = Counter()
        for item in items:
            counts.update(self._tokenize(item['text']))
        return [word for word, _ in counts.most_common(8)]

    def _retrieve(self, question: str, items: list[dict[str, str]]) -> list[dict[str, str]]:
        query_terms = set(self._tokenize(question))
        if not query_terms:
            return items[:4]

        scored = []
        for index, item in enumerate(items):
            item_terms = set(self._tokenize(item['text']))
            overlap = len(query_terms & item_terms)
            recency_bonus = (len(items) - index) / max(len(items), 1)
            score = overlap + recency_bonus
            if overlap > 0:
                scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:4]]
