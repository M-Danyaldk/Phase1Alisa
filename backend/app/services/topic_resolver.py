from typing import Literal

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
        clean_topic = topic.strip() or 'general practice'
        if normalized_source == 'manual':
            return {
                'subject': subject,
                'topic': clean_topic,
                'assessed_level': assessment_context.get('assessed_level') if assessment_context else None,
                'reason': 'Manual topic selected.',
                'source': 'manual',
            }

        assessment_topic = self._assessment_topic(assessment_context)
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

    def _assessment_topic(self, assessment_context: dict | None) -> str:
        if not assessment_context:
            return ''
        for key in ('recommended_next_topics', 'learning_gaps', 'recommended_next_steps'):
            values = assessment_context.get(key) or []
            if values:
                return self._topic_from_text(str(values[0]))
        return ''

    def _topic_from_text(self, value: str) -> str:
        text = value.strip()
        if not text:
            return ''
        for separator in (':', '-', '–', '—'):
            if separator in text:
                candidate = text.split(separator, 1)[-1].strip()
                if candidate:
                    text = candidate
                    break
        return text[:80]
