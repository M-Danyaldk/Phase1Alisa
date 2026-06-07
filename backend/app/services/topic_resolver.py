from typing import Literal
import re

from ..models import Subject

TopicSource = Literal['manual', 'default', 'assessment']


class TopicResolver:
    def resolve(
        self,
        *,
        subject: Subject,
        topic: str,
        topic_source: str | None,
        assessment_context: dict | None,
    ) -> dict:
        normalized_source = topic_source if topic_source in ('manual', 'default', 'assessment') else 'manual'
        clean_topic = self._safe_topic(subject, topic)
        if normalized_source == 'manual':
            return {
                'subject': subject,
                'topic': clean_topic,
                'assessed_level': assessment_context.get('assessed_level') if assessment_context else None,
                'reason': 'Manual topic selected.',
                'source': 'manual',
            }

        assessment_topic = self._assessment_topic(subject, assessment_context)
        if assessment_topic:
            return {
                'subject': subject,
                'topic': assessment_topic,
                'assessed_level': assessment_context.get('assessed_level') if assessment_context else None,
                'reason': 'Selected from the latest assessment learning gaps or recommendations.',
                'source': 'assessment',
            }

        return {
            'subject': subject,
            'topic': clean_topic,
            'assessed_level': assessment_context.get('assessed_level') if assessment_context else None,
            'reason': 'No assessment topic was available; using the existing default topic.',
            'source': 'default',
        }

    def _assessment_topic(self, subject: Subject, assessment_context: dict | None) -> str:
        if not assessment_context:
            return ''
        for key in ('recommended_next_topics', 'learning_gaps', 'recommended_next_steps'):
            values = assessment_context.get(key) or []
            if values:
                return self._topic_from_text(subject, str(values[0]))
        return ''

    def _topic_from_text(self, subject: Subject, value: str) -> str:
        text = value.strip()
        if not text:
            return ''
        for separator in (':', '-', '–', '—'):
            if separator in text:
                candidate = text.split(separator, 1)[-1].strip()
                if candidate:
                    text = candidate
                    break
        return self._safe_topic(subject, text)

    def _safe_topic(self, subject: Subject, value: str | None) -> str:
        text = str(value or '').strip()
        text = re.sub(r'[*_`#>\[\]()]', '', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\s+', ' ', text).strip(' .,:;-')
        if len(text) < 3 or not re.search(r'[A-Za-z]', text):
            return self._default_topic(subject)
        if any(marker in text.lower() for marker in ('i need help', "i don't know", 'i dont know', 'good try', 'you are close', "you're close", 'we just found', 'student:', 'msalisia:')):
            return self._default_topic(subject)
        return text[:80]

    def _default_topic(self, subject: Subject) -> str:
        if subject == 'Math':
            return 'multiplication facts'
        if subject == 'ELA':
            return 'reading vocabulary'
        if subject == 'Writing':
            return 'sentence writing'
        return 'guided practice'
