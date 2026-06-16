import json
import re

from .base import LLMResult
from .claude_provider import ClaudeProvider
from .groq_provider import GroqProvider
from ...assessment_validation import extract_math_expression, normalize_math_text, normalize_word_numbers_in_text, safe_eval_expression
from ...config import get_settings
from ..app_data_service import AppDataService

class LLMRouter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.providers = {
            'claude': ClaudeProvider(),
            'groq': GroqProvider(),
        }

    async def generate(self, system: str, user: str, purpose: str = 'chat') -> LLMResult:
        primary = self._resolve_provider(self.settings.primary_llm_provider)
        fallback = self._resolve_provider(self.settings.fallback_llm_provider)
        max_tokens = self._max_tokens_for_purpose(purpose)

        if primary is None:
            if fallback is not None and fallback.available():
                result = await fallback.generate(system, user, max_tokens=max_tokens)
                result.fallback_used = True
                await self._record(result, purpose)
                return result
            return self._local_fallback(purpose, fallback_used=False, system=system, user=user)

        if primary.available():
            try:
                result = await primary.generate(system, user, max_tokens=max_tokens)
                await self._record(result, purpose)
                return result
            except Exception as exc:
                if not self.settings.fallback_on_llm_error:
                    raise exc
                if fallback is not None and fallback.provider_name != primary.provider_name and fallback.available():
                    result = await fallback.generate(system, user, max_tokens=max_tokens)
                    result.fallback_used = True
                    await self._record(result, purpose)
                    return result
                return self._local_fallback(purpose, fallback_used=True, system=system, user=user)

        if fallback is not None and fallback.provider_name != primary.provider_name and fallback.available():
            result = await fallback.generate(system, user, max_tokens=max_tokens)
            result.fallback_used = True
            await self._record(result, purpose)
            return result

        return self._local_fallback(purpose, fallback_used=False, system=system, user=user)

    def _resolve_provider(self, provider_name: str):
        normalized = self.settings.normalized_llm_provider(provider_name)
        if not self.settings.llm_provider_supported(normalized):
            return None
        return self.providers[normalized]

    def _max_tokens_for_purpose(self, purpose: str) -> int:
        if purpose == 'chat':
            return min(self.settings.chat_max_output_tokens, 800)
        if purpose == 'opening':
            return min(self.settings.chat_max_output_tokens, 220)
        if purpose == 'assessment':
            return min(self.settings.assessment_max_output_tokens, 1600)
        if purpose == 'report':
            return min(self.settings.report_max_output_tokens, 1600)
        if purpose == 'homework':
            return min(self.settings.homework_max_output_tokens, 1200)
        if purpose == 'classifier':
            return min(self.settings.classifier_max_output_tokens, 300)
        return self.settings.max_output_tokens

    async def _record(self, result: LLMResult, purpose: str) -> None:
        try:
            await AppDataService().record_llm_event(result.provider, result.model, purpose, result.fallback_used)
        except Exception:
            pass

    def _local_fallback(self, purpose: str, fallback_used: bool, system: str = '', user: str = '') -> LLMResult:
        templates = {
            'chat': 'No worries, I will help. Let us do one small step at a time, and I will show the next part clearly.',
            'opening': 'Hi! I am glad you are here. Before we start, how are you feeling today? Then I can ask one quick thing so I know how to help.',
            'assessment': '{"estimated_level":"Needs live LLM evaluation","score_label":"Local fallback","strengths":["Student attempted the task"],"learning_gaps":["Connect Claude or Groq to evaluate accurately"],"recommended_progression":["Review one concept at a time with Ms Alisia"],"parent_summary":"The assessment was received, but live LLM evaluation is not connected yet."}',
            'homework': 'Nice try. Your file was received in Phase 1, but detailed worksheet and handwriting analysis will be added in the next phase. For now, I can help from your note and suggest one small next step.'
        }
        if purpose == 'classifier':
            text = self._local_classifier_fallback(system, user)
        else:
            text = templates.get(purpose, templates['chat'])
        return LLMResult(text=text, provider='local_fallback', model='rules', fallback_used=fallback_used)

    def _local_classifier_fallback(self, system: str, user: str) -> str:
        system_text = str(system or '').lower()
        if 'normalize grades 3-6 student math input' in system_text:
            return self._local_math_normalization_json(user)
        if 'classify a child tutor message for grades 3-6' in system_text:
            return self._local_intent_json(user)
        if 'classify whether a grades 3-6 student message fits the current tutor subject' in system_text:
            return self._local_subject_json(user)
        return json.dumps({'label': 'unknown', 'confidence': 'medium', 'reason': 'Local fallback returned a safe unknown classification.'})

    def _local_math_normalization_json(self, user: str) -> str:
        message = self._extract_labeled_value(user, 'Student math input')
        expression = self._normalize_word_math_expression(message)
        if not expression:
            payload = {'normalized_expression': '', 'confidence': 'low', 'reason': 'Local fallback could not repair the math safely.'}
            return json.dumps(payload)
        payload = {'normalized_expression': expression, 'confidence': 'medium', 'reason': 'Local fallback normalized the math with deterministic rules.'}
        return json.dumps(payload)

    def _local_intent_json(self, user: str) -> str:
        message = self._extract_labeled_value(user, 'Student message').lower()
        if not message:
            return json.dumps({'label': 'unknown', 'confidence': 'low', 'reason': 'No student message was available.'})

        if self._looks_like_switch_request(message):
            return json.dumps({'label': 'switch_request', 'confidence': 'medium', 'reason': 'The student appears to want to do a different problem first.'})
        if any(marker in message for marker in ('how did', 'what do you mean', 'why did', 'how come', 'became', 'came from')):
            return json.dumps({'label': 'related_question', 'confidence': 'medium', 'reason': 'The student appears to be asking about the current problem.'})
        if any(marker in message for marker in ('i think', 'is it', 'my answer', 'it becomes')) and self._contains_math_content(message):
            return json.dumps({'label': 'answer_current_step', 'confidence': 'medium', 'reason': 'The student appears to be trying an answer for the current step.'})
        if self._contains_math_content(message):
            return json.dumps({'label': 'new_problem', 'confidence': 'medium', 'reason': 'The message looks like a different math problem.'})
        return json.dumps({'label': 'unknown', 'confidence': 'medium', 'reason': 'Local fallback could not confidently disambiguate the student message.'})

    def _local_subject_json(self, user: str) -> str:
        subject = self._extract_labeled_value(user, 'Current tutor subject')
        message = self._extract_labeled_value(user, 'Student message').lower()
        if not message:
            return json.dumps({'label': 'ambiguous', 'confidence': 'low', 'reason': 'No student message was available.'})

        if re.search(r'\b(switch|change|move|go)\s+(to|back to)\s+(math|reading|writing|ela)\b', message):
            return json.dumps({'label': 'explicit_subject_switch', 'confidence': 'high', 'reason': 'The student explicitly asked to change subjects.'})

        math_words = {'math', 'fraction', 'fractions', 'numerator', 'denominator', 'equation', 'expression', 'multiply', 'divide', 'addition', 'subtraction'}
        ela_words = {'reading', 'story', 'passage', 'character', 'theme', 'main idea', 'vocabulary', 'context clue', 'meaning', 'author', 'setting', 'plot'}
        writing_words = {'writing', 'write', 'revise', 'revision', 'rewrite', 'edit', 'essay', 'topic sentence', 'complete sentence', 'stronger sentence'}
        science_words = {'photosynthesis', 'leaf', 'leaves', 'plant', 'plants', 'sunlight', 'water', 'gravity', 'volcano', 'planet', 'weather', 'science', 'food chain'}
        reading_task = self._looks_like_reading_task(message)
        writing_task = self._looks_like_writing_task(message)

        if subject == 'Math':
            if self._contains_math_content(message) or any(word in message for word in math_words):
                return json.dumps({'label': 'in_subject', 'confidence': 'high', 'reason': 'The message is still about math.'})
            if any(word in message for word in science_words):
                return json.dumps({'label': 'off_subject', 'confidence': 'high', 'reason': 'The message is asking about science instead of math.'})
            if re.match(r'^(what|who|how|why|tell me|explain|help me|can you help|can you explain)\b', message):
                return json.dumps({'label': 'off_subject', 'confidence': 'medium', 'reason': 'The message looks like a non-math question while the tutor is in math.'})
            return json.dumps({'label': 'ambiguous', 'confidence': 'medium', 'reason': 'The message may be outside math, but local fallback is not fully certain.'})

        if subject in {'ELA', 'Writing'} and self._contains_math_content(message):
            return json.dumps({'label': 'off_subject', 'confidence': 'high', 'reason': 'The message is math while the current tutor subject is not math.'})

        if subject == 'ELA':
            if writing_task:
                return json.dumps({'label': 'off_subject', 'confidence': 'high', 'reason': 'The message is asking for writing work, not reading.'})
            if reading_task:
                return json.dumps({'label': 'in_subject', 'confidence': 'high', 'reason': 'The message is still about reading.'})
            if any(word in message for word in ela_words):
                return json.dumps({'label': 'in_subject', 'confidence': 'high', 'reason': 'The message is still about reading.'})
            if any(word in message for word in science_words):
                return json.dumps({'label': 'off_subject', 'confidence': 'medium', 'reason': 'The message looks like general knowledge rather than reading.'})
            return json.dumps({'label': 'ambiguous', 'confidence': 'medium', 'reason': 'Local fallback could not fully place the message inside reading.'})

        if subject == 'Writing':
            if reading_task:
                return json.dumps({'label': 'off_subject', 'confidence': 'high', 'reason': 'The message is asking for reading work, not writing.'})
            if writing_task:
                return json.dumps({'label': 'in_subject', 'confidence': 'high', 'reason': 'The message is still about writing.'})
            if any(word in message for word in writing_words):
                return json.dumps({'label': 'in_subject', 'confidence': 'high', 'reason': 'The message is still about writing.'})
            if any(word in message for word in science_words):
                return json.dumps({'label': 'off_subject', 'confidence': 'medium', 'reason': 'The message looks like general knowledge rather than writing.'})
            return json.dumps({'label': 'ambiguous', 'confidence': 'medium', 'reason': 'Local fallback could not fully place the message inside writing.'})

        return json.dumps({'label': 'ambiguous', 'confidence': 'medium', 'reason': 'Local fallback could not determine the subject.'})

    def _extract_labeled_value(self, text: str, label: str) -> str:
        pattern = rf'{re.escape(label)}:\s*(.*)'
        match = re.search(pattern, str(text or ''), re.I)
        return match.group(1).strip() if match else ''

    def _contains_math_content(self, message: str) -> bool:
        text = normalize_math_text(message)
        if re.search(r'\d', text) and any(symbol in text for symbol in ('+', '-', '*', '/', '(', ')', '=')):
            return True
        return any(word in text for word in ('plus', 'minus', 'times', 'multiplied by', 'divided by', 'over'))

    def _looks_like_switch_request(self, message: str) -> bool:
        switch_patterns = (
            r'\b(do|solve|try)\b.*\bfirst\b',
            r'\binstead\b',
            r'\bswitch\b',
            r'\bnew problem\b',
        )
        return any(re.search(pattern, message) for pattern in switch_patterns) and self._contains_math_content(message)

    def _normalize_word_math_expression(self, message: str) -> str:
        text = normalize_math_text(message).lower()
        if not text:
            return ''

        text = re.sub(r'^(what is|solve|find|compute|evaluate)\s+', '', text)
        replacements = (
            ('open parenthesis', ' ( '),
            ('close parenthesis', ' ) '),
            ('left parenthesis', ' ( '),
            ('right parenthesis', ' ) '),
            ('multiplied by', ' * '),
            ('divided by', ' / '),
            ('times', ' * '),
            ('plus', ' + '),
            ('minus', ' - '),
            ('over', ' / '),
        )
        for old, new in replacements:
            text = re.sub(rf'\b{re.escape(old)}\b', new, text)

        text = normalize_word_numbers_in_text(text)

        text = text.replace('[', '(').replace(']', ')').replace('{', '(').replace('}', ')')
        text = text.replace('//', '/').replace('**', '*')
        text = re.sub(r'[^0-9\+\-\*/\(\)\.\s]', ' ', text)
        text = re.sub(r'([+\-*/])\1+', r'\1', text)
        text = re.sub(r'\s+', ' ', text).strip()
        text = self._balance_parentheses(text)
        expression = extract_math_expression(text) or text

        if not expression or not any(symbol in expression for symbol in ('+', '-', '*', '/')):
            return ''
        if safe_eval_expression(expression) is None and not ('(' in expression and ')' in expression):
            return ''
        return expression

    def _balance_parentheses(self, expression: str) -> str:
        balanced: list[str] = []
        open_count = 0
        for char in expression:
            if char == '(':
                open_count += 1
                balanced.append(char)
            elif char == ')':
                if open_count > 0:
                    open_count -= 1
                    balanced.append(char)
            else:
                balanced.append(char)
        if open_count > 0:
            balanced.extend(')' for _ in range(open_count))
        return ''.join(balanced)

    def _looks_like_reading_task(self, message: str) -> bool:
        text = normalize_math_text(message).lower()
        phrases = (
            'main idea',
            'context clue',
            'what does',
            'meaning of',
            'character',
            'theme',
            'passage',
            'story',
            'reading',
            'vocabulary',
            'inference',
            'author',
            'setting',
            'plot',
        )
        starters = (
            'read this',
            'help me understand this passage',
            'help me with this passage',
            'help me with this text',
            'can you help me with this passage',
            'can you help me with this text',
            'help me read this',
            'what does',
            'what is the main idea',
            'who is the main character',
            'what is the theme',
        )
        return text.startswith(starters) or any(phrase in text for phrase in phrases)

    def _looks_like_writing_task(self, message: str) -> bool:
        text = normalize_math_text(message).lower()
        phrases = (
            'write one clear sentence',
            'write 3 sentences',
            'write three sentences',
            'fix this sentence',
            'make this sentence stronger',
            'how can you make this sentence stronger',
            'complete sentence',
            'topic sentence',
            'revise',
            'revision',
            'rewrite',
            'edit this',
            'writing',
            'essay',
        )
        starters = (
            'help me write',
            'help me with this paragraph',
            'help me with this sentence',
            'can you help me with this paragraph',
            'can you help me with this sentence',
            'check my sentence',
            'write ',
            'rewrite ',
            'revise ',
            'edit ',
            'fix this sentence',
            'how can you make this sentence stronger',
        )
        return text.startswith(starters) or any(phrase in text for phrase in phrases)
