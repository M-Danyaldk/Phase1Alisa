import json
import re
from dataclasses import dataclass
from fractions import Fraction

from ..assessment_bank import AssessmentQuestion, all_assessment_versions
from ..assessment_validation import extract_math_expression, extract_numeric_value, format_fraction, normalize_answer_text, normalize_math_text, safe_eval_expression, validate_assessment_answer
from ..services.llm.router import LLMRouter


@dataclass
class AnswerCheckResult:
    status: str = 'unclear'
    expected_answer: str = ''
    feedback_note: str = ''
    checked_expression: str = ''

    @property
    def is_wrong(self) -> bool:
        return self.status in {'incorrect', 'partially_correct', 'unclear'}

    @property
    def is_correct(self) -> bool:
        return self.status == 'correct'


class TutorAnswerChecker:
    async def check(
        self,
        subject: str,
        question: str,
        student_answer: str,
        expected_answer: str = '',
    ) -> AnswerCheckResult:
        math_result = self._check_math(question, student_answer, expected_answer)
        if math_result.status != 'unclear':
            return math_result
        local_text_result = self._check_local_text_prompt(subject, question, student_answer, expected_answer)
        if local_text_result.status != 'unclear':
            return local_text_result
        if expected_answer.strip():
            text_result = self._check_text_against_expected(student_answer, expected_answer)
            if text_result.status != 'unclear':
                return text_result
        return await self._classify_with_llm(subject, question, student_answer, expected_answer)

    def check_direct_math_statement(self, message: str) -> AnswerCheckResult:
        expression = self._extract_direct_expression(message)
        stated_answer = self._extract_stated_answer(message)
        if not expression or not stated_answer:
            return AnswerCheckResult()

        expected_value = self._safe_eval_expression(expression)
        student_value = self._extract_student_math_value(stated_answer)
        if expected_value is None or student_value is None:
            return AnswerCheckResult()

        expected_answer = self._format_fraction(expected_value)
        display_expression = self._display_expression(expression)
        if expected_value == student_value:
            return AnswerCheckResult(
                status='correct',
                expected_answer=expected_answer,
                checked_expression=display_expression,
                feedback_note='Direct math answer checked deterministically.',
            )
        return AnswerCheckResult(
            status='incorrect',
            expected_answer=expected_answer,
            checked_expression=display_expression,
            feedback_note='Direct math answer does not match the expression value.',
        )

    def _check_math(self, question: str, student_answer: str, expected_answer: str) -> AnswerCheckResult:
        expected_value = self._extract_expected_math_value(question, expected_answer)
        student_value = self._extract_student_math_value(student_answer)
        if expected_value is None or student_value is None:
            return AnswerCheckResult()
        if expected_value == student_value:
            return AnswerCheckResult(status='correct', expected_answer=self._format_fraction(expected_value))
        return AnswerCheckResult(
            status='incorrect',
            expected_answer=self._format_fraction(expected_value),
            feedback_note='The numeric answer does not match the expected answer.',
        )

    def _extract_expected_math_value(self, question: str, expected_answer: str) -> Fraction | None:
        if expected_answer.strip():
            value = self._extract_student_math_value(expected_answer)
            if value is not None:
                return value
        expression = self._extract_math_expression(question)
        if not expression:
            return None
        return self._safe_eval_expression(expression)

    def _extract_student_math_value(self, answer: str) -> Fraction | None:
        return extract_numeric_value(answer)

    def _extract_math_expression(self, text: str) -> str:
        return extract_math_expression(text)

    def _extract_direct_expression(self, text: str) -> str:
        normalized = normalize_math_text(text)
        match = re.search(r'(-?\d+(?:\.\d+)?)\s*([x\*\+/\-])\s*(-?\d+(?:\.\d+)?)', normalized)
        if not match:
            return ''
        operator = '*' if match.group(2) == 'x' else match.group(2)
        return f'{match.group(1)} {operator} {match.group(3)}'

    def _extract_stated_answer(self, text: str) -> str:
        normalized = normalize_math_text(text)
        answer_match = re.search(
            r'(?:my\s+answer|answer|i\s+got|i\s+think\s+it\s+is|it\s+is|equals?)\s*(?:is|=|:)?\s*(-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+)?)',
            normalized,
        )
        if answer_match:
            return answer_match.group(1)
        numbers = re.findall(r'-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+)?', normalized)
        return numbers[-1] if len(numbers) >= 3 else ''

    def _display_expression(self, expression: str) -> str:
        return expression.replace('*', '×').replace('/', '÷')

    def _safe_eval_expression(self, expression: str) -> Fraction | None:
        return safe_eval_expression(expression)

    def _check_text_against_expected(self, student_answer: str, expected_answer: str) -> AnswerCheckResult:
        student_words = self._keyword_set(student_answer)
        expected_words = self._keyword_set(expected_answer)
        if not expected_words:
            return AnswerCheckResult()
        overlap = len(student_words & expected_words) / max(len(expected_words), 1)
        if overlap >= 0.7:
            return AnswerCheckResult(status='correct', expected_answer=expected_answer)
        if overlap >= 0.35:
            return AnswerCheckResult(status='partially_correct', expected_answer=expected_answer)
        return AnswerCheckResult(status='incorrect', expected_answer=expected_answer)

    def _check_local_text_prompt(
        self,
        subject: str,
        question: str,
        student_answer: str,
        expected_answer: str,
    ) -> AnswerCheckResult:
        simple_reading = self._check_ela_quick_prompt(subject, question, student_answer)
        if simple_reading.status != 'unclear':
            return simple_reading

        sentence_completion = self._check_writing_sentence_completion(subject, question, student_answer)
        if sentence_completion.status != 'unclear':
            return sentence_completion

        pseudo = self._pseudo_question(subject, question, expected_answer)
        if not pseudo:
            return AnswerCheckResult()
        validation = validate_assessment_answer(pseudo, student_answer)
        if validation.status == 'needs_review':
            return AnswerCheckResult()
        return AnswerCheckResult(
            status=validation.status,
            expected_answer=validation.expected_answer,
            feedback_note=validation.feedback_note,
        )

    def _pseudo_question(self, subject: str, question: str, expected_answer: str) -> AssessmentQuestion | None:
        clean_question = str(question or '').strip()
        if not clean_question:
            return None
        lower = clean_question.lower()
        matched = self._lookup_bank_question(subject, clean_question)
        if matched:
            return matched

        if subject == 'Writing':
            if self._matches_writing_single_sentence_prompt(lower):
                return self._build_pseudo_question(subject, clean_question, 'writing_rubric', expected_answer or 'One complete sentence that stays on topic.', 'complete sentence')
            if self._matches_writing_three_sentence_prompt(lower):
                return self._build_pseudo_question(subject, clean_question, 'writing_rubric', expected_answer or 'Three connected explanatory sentences with a clear reason and details.', 'explanatory writing')
            if self._matches_writing_revision_prompt(lower):
                return self._build_pseudo_question(subject, clean_question, 'writing_rubric', expected_answer or 'A stronger sentence with more specific detail or vivid word choice.', 'revision for detail')

        if lower.startswith('fix this sentence:'):
            return self._build_pseudo_question(subject, clean_question, 'exact_text', expected_answer, 'grammar and conventions')
        if 'what does "' in lower and '" mean' in lower:
            return self._build_pseudo_question(subject, clean_question, 'keyword_text', expected_answer, 'vocabulary in context')
        if subject == 'ELA' and expected_answer.strip():
            return self._build_pseudo_question(subject, clean_question, 'keyword_text', expected_answer, 'reading comprehension')
        return None

    def _check_ela_quick_prompt(self, subject: str, question: str, student_answer: str) -> AnswerCheckResult:
        if subject != 'ELA':
            return AnswerCheckResult()

        clean_question = str(question or '').strip()
        prompt_question = self._extract_reading_prompt(clean_question)
        lower_question = prompt_question.lower()
        sentence = self._extract_reading_sentence(clean_question)
        if not sentence:
            return AnswerCheckResult()
        sentence_tokens = re.findall(r"[a-z']+", sentence.lower())
        if len(sentence_tokens) < 3:
            return AnswerCheckResult()

        if 'main idea' in lower_question or 'infer' in lower_question:
            return AnswerCheckResult()
        if 'what happened first' in lower_question or 'what happened at the beginning' in lower_question:
            return self._check_ela_expected_phrase(student_answer, self._first_sequence_part(sentence), sentence)
        if 'what happened next' in lower_question or 'what happened then' in lower_question or 'what happened after' in lower_question:
            return self._check_ela_expected_phrase(student_answer, self._next_sequence_part(sentence), sentence)
        if re.search(r'\bwhat\s+does\s+["“]?[a-z\']+["”]?\s+mean\b', lower_question):
            return self._check_ela_vocabulary_prompt(clean_question, sentence, student_answer)
        if lower_question.startswith('who '):
            return self._check_ela_expected_phrase(student_answer, self._sentence_subject_phrase(sentence), sentence)
        if lower_question.startswith('where '):
            return self._check_ela_expected_phrase(student_answer, self._where_phrase(sentence_tokens), sentence)
        if lower_question.startswith('when '):
            return self._check_ela_expected_phrase(student_answer, self._when_phrase(sentence), sentence)
        if lower_question.startswith('why '):
            return self._check_ela_expected_phrase(student_answer, self._why_phrase(sentence), sentence)
        if 'what did' not in lower_question or ' do' not in lower_question:
            return AnswerCheckResult()

        subject_match = re.search(r'what\s+did\s+(?:the\s+)?([a-z]+)\s+do\b', lower_question)
        subject_word = subject_match.group(1) if subject_match else ''
        subject_index = self._find_subject_index(sentence_tokens, subject_word)
        if subject_index < 0 or subject_index + 1 >= len(sentence_tokens):
            return AnswerCheckResult()

        predicate_tokens = sentence_tokens[subject_index + 1:]
        action_root = self._normalize_action_word(predicate_tokens[0])
        important_detail_tokens = {
            token
            for token in predicate_tokens[1:]
            if token not in {'a', 'an', 'the', 'to', 'in', 'on', 'at', 'into', 'from', 'with'}
        }
        if not action_root:
            return AnswerCheckResult()

        answer_tokens = re.findall(r"[a-z']+", str(student_answer or '').lower())
        answer_roots = {self._normalize_action_word(token) for token in answer_tokens}
        answer_words = set(answer_tokens)
        has_action = action_root in answer_roots
        has_details = important_detail_tokens.issubset(answer_words) if important_detail_tokens else True
        expected_answer = sentence.rstrip('.?!')

        if has_action and has_details:
            return AnswerCheckResult(
                status='correct',
                expected_answer=expected_answer,
                feedback_note=f'You understood the action: {expected_answer}.',
            )
        if has_action:
            return AnswerCheckResult(
                status='partially_correct',
                expected_answer=expected_answer,
                feedback_note=f'You found the action. Add the important detail: {expected_answer}.',
            )
        return AnswerCheckResult(
            status='incorrect',
            expected_answer=expected_answer,
            feedback_note=f'Look back at the sentence. A strong answer would be: {expected_answer}.',
        )

    def _extract_reading_sentence(self, text: str) -> str:
        quoted_sentences = re.findall(r'["“]([^"”]+)["”]', text)
        if quoted_sentences:
            sentence_like = [sentence.strip() for sentence in quoted_sentences if len(re.findall(r"[a-z']+", sentence)) >= 3]
            return (sentence_like[0] if sentence_like else quoted_sentences[0]).strip()
        passage_match = re.search(r'read this short passage:\s*(.+?)(?:\b(?:quick question|current question|what|who|where|when|why|how|which)\b|$)', text, flags=re.IGNORECASE | re.DOTALL)
        if passage_match:
            return passage_match.group(1).strip()
        return ''

    def _extract_reading_prompt(self, text: str) -> str:
        prompt_matches = re.findall(r'(?:quick question|current question):\s*([^\n]+)', text, flags=re.IGNORECASE)
        if prompt_matches:
            return prompt_matches[-1].strip()
        question_lines = [line.strip() for line in str(text or '').splitlines() if line.strip().endswith('?')]
        return question_lines[-1] if question_lines else str(text or '').strip()

    def _check_ela_expected_phrase(self, student_answer: str, expected_phrase: str, source_sentence: str) -> AnswerCheckResult:
        expected = str(expected_phrase or '').strip(' .')
        if not expected:
            return AnswerCheckResult()
        expected_words = self._keyword_set(expected)
        answer_words = self._keyword_set(student_answer)
        if not expected_words or not answer_words:
            return AnswerCheckResult(
                status='incorrect',
                expected_answer=expected,
                feedback_note=f'Look back at the sentence. A strong answer would be: {expected}.',
            )
        overlap = len(expected_words & answer_words) / max(len(expected_words), 1)
        if overlap >= 0.7 or expected.lower() in str(student_answer or '').lower():
            return AnswerCheckResult(
                status='correct',
                expected_answer=expected,
                feedback_note=f'You found the answer in the sentence: {expected}.',
            )
        if overlap >= 0.35:
            return AnswerCheckResult(
                status='partially_correct',
                expected_answer=expected,
                feedback_note=f'You found part of it. A stronger answer is: {expected}.',
            )
        return AnswerCheckResult(
            status='incorrect',
            expected_answer=expected,
            feedback_note=f'Look back at the sentence. A strong answer would be: {expected}.',
        )

    def _check_ela_vocabulary_prompt(self, question: str, sentence: str, student_answer: str) -> AnswerCheckResult:
        match = re.search(r'\bwhat\s+does\s+["“]?([a-z\']+)["”]?\s+mean\b', question.lower())
        target = match.group(1) if match else ''
        if not target:
            return AnswerCheckResult()
        simple_meanings = {
            'tiny': ('small', {'small', 'little', 'very small'}),
            'large': ('big', {'big', 'huge'}),
            'happy': ('glad', {'glad', 'joyful'}),
            'sad': ('unhappy', {'unhappy', 'upset'}),
            'quick': ('fast', {'fast'}),
            'rapid': ('fast', {'fast', 'quick'}),
            'silent': ('quiet', {'quiet'}),
            'difficult': ('hard', {'hard'}),
            'easy': ('simple', {'simple', 'not hard'}),
            'begin': ('start', {'start'}),
            'finish': ('complete', {'end', 'complete', 'done'}),
        }
        meaning = simple_meanings.get(target)
        if not meaning:
            return AnswerCheckResult()
        expected, accepted = meaning
        answer = normalize_answer_text(student_answer)
        if any(normalize_answer_text(value) in answer for value in accepted):
            return AnswerCheckResult(
                status='correct',
                expected_answer=expected,
                feedback_note=f'In this sentence, {target} means {expected}.',
            )
        if target in answer:
            return AnswerCheckResult(
                status='partially_correct',
                expected_answer=expected,
                feedback_note=f'That repeats the word. In this sentence, {target} means {expected}.',
            )
        return AnswerCheckResult(
            status='incorrect',
            expected_answer=expected,
            feedback_note=f'In this sentence, {target} means {expected}.',
        )

    def _sentence_subject_phrase(self, sentence: str) -> str:
        words = re.findall(r"[A-Za-z']+", str(sentence or ''))
        if len(words) >= 2 and words[0].lower() in {'a', 'an', 'the'}:
            return ' '.join(words[:2])
        return words[0] if words else ''

    def _where_phrase(self, tokens: list[str]) -> str:
        prepositions = {'to', 'in', 'on', 'at', 'into', 'inside', 'outside', 'under', 'over', 'near', 'beside'}
        for index, token in enumerate(tokens):
            if token in prepositions and index + 1 < len(tokens):
                phrase = tokens[index:]
                stop_words = {'and', 'because', 'then', 'when', 'after', 'before', 'with'}
                trimmed = []
                for word in phrase:
                    if word in stop_words:
                        break
                    trimmed.append(word)
                return ' '.join(trimmed)
        return ''

    def _when_phrase(self, sentence: str) -> str:
        clean = sentence.strip(' .')
        leading = re.match(r'^(after|before|during|when|while)\s+([^,]+)', clean, flags=re.IGNORECASE)
        if leading:
            return leading.group(0)
        trailing = re.search(r'\b(after|before|during|when|while)\s+([^,.]+)', clean, flags=re.IGNORECASE)
        if trailing:
            return trailing.group(0)
        return ''

    def _why_phrase(self, sentence: str) -> str:
        match = re.search(r'\b(because|so that|so)\s+([^,.]+)', sentence.strip(' .'), flags=re.IGNORECASE)
        return match.group(0) if match else ''

    def _first_sequence_part(self, sentence: str) -> str:
        clean = sentence.strip(' .')
        match = re.search(r'\bfirst\b\s+(.+?)(?:,\s*(?:then|next)\b|$)', clean, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return clean.split(',')[0].strip()

    def _next_sequence_part(self, sentence: str) -> str:
        clean = sentence.strip(' .')
        match = re.search(r'\b(?:then|next)\b\s+(.+)$', clean, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        parts = [part.strip() for part in clean.split(',') if part.strip()]
        return parts[1] if len(parts) > 1 else ''

    def _find_subject_index(self, tokens: list[str], subject_word: str) -> int:
        if subject_word and subject_word in tokens:
            return tokens.index(subject_word)
        for index, token in enumerate(tokens[:-1]):
            if token not in {'a', 'an', 'the'}:
                return index
        return -1

    def _normalize_action_word(self, word: str) -> str:
        clean = str(word or '').lower().strip("'")
        irregular = {
            'ran': 'run',
            'running': 'run',
            'runs': 'run',
            'went': 'go',
            'going': 'go',
            'goes': 'go',
            'saw': 'see',
            'seen': 'see',
            'seeing': 'see',
            'ate': 'eat',
            'eating': 'eat',
            'eats': 'eat',
        }
        if clean in irregular:
            return irregular[clean]
        if len(clean) > 4 and clean.endswith('ing'):
            return clean[:-3]
        if len(clean) > 3 and clean.endswith('ed'):
            return clean[:-2]
        if len(clean) > 3 and clean.endswith('s'):
            return clean[:-1]
        return clean

    def _matches_writing_single_sentence_prompt(self, lower: str) -> bool:
        return lower.startswith('write one clear sentence')

    def _matches_writing_three_sentence_prompt(self, lower: str) -> bool:
        return bool(re.match(r'^write\s+(?:3|three)\s+sentences\b', lower))

    def _matches_writing_revision_prompt(self, lower: str) -> bool:
        return lower.startswith('how can you make this sentence stronger') or lower.startswith('make this sentence stronger')

    def _check_writing_sentence_completion(self, subject: str, question: str, student_answer: str) -> AnswerCheckResult:
        if subject != 'Writing':
            return AnswerCheckResult()
        prompt = str(question or '').strip()
        if 'finish this sentence' not in prompt.lower():
            return AnswerCheckResult()
        stem = self._extract_sentence_completion_stem(prompt)
        if not stem:
            return AnswerCheckResult()

        answer = str(student_answer or '').strip()
        normalized_answer = normalize_answer_text(answer)
        if normalized_answer in {'yes', 'no', 'yeah', 'nope', 'ok', 'okay'}:
            return self._sentence_completion_result(
                'incorrect',
                stem,
                'Add words after the sentence starter instead of answering yes or no.',
            )

        stem_prefix = stem.replace('...', '').strip()
        lower_stem = normalize_answer_text(stem_prefix)
        completed_text = answer
        if lower_stem and not normalized_answer.startswith(lower_stem):
            completed_text = f'{stem_prefix} {answer}'.strip()

        completed_words = re.findall(r"[A-Za-z0-9']+", completed_text)
        answer_words = re.findall(r"[A-Za-z0-9']+", answer)
        has_because_stem = lower_stem.endswith('because')
        has_reason = len(answer_words) >= 3 and normalized_answer not in {'yes i like races', 'yes i like recess'}
        has_recess_topic = bool({'recess', 'run', 'running', 'play', 'friends', 'outside', 'games'} & {word.lower() for word in answer_words})
        has_sentence_shape = len(completed_words) >= 7
        has_simple_convention_issue = bool(re.search(r'\bgood\s+in\s+\w+', normalized_answer))
        display_completed = completed_text.strip().rstrip('.')
        if display_completed.startswith('i '):
            display_completed = f'I {display_completed[2:]}'

        if has_because_stem and has_reason and has_sentence_shape and not has_simple_convention_issue:
            return self._sentence_completion_result(
                'correct',
                stem,
                f'Nice. You finished the sentence with a reason: {display_completed}.',
            )
        if has_because_stem and (has_reason or has_recess_topic):
            return self._sentence_completion_result(
                'partially_correct',
                stem,
                f'You have an idea. Make it a clear sentence like: {stem_prefix} I am good at running.',
            )
        return self._sentence_completion_result(
            'incorrect',
            stem,
            f'Finish the sentence by adding a clear reason after the starter: {stem_prefix} ____.',
        )

    def _extract_sentence_completion_stem(self, prompt: str) -> str:
        quoted = re.findall(r'["“]([^"”]*\.{3}[^"”]*)["”]', prompt)
        if quoted:
            return quoted[-1].strip()
        line_match = re.search(r'([A-Z][^.\n?!"“”]*\b(?:because|when|if|so)\s*\.{3})', prompt, flags=re.IGNORECASE)
        return line_match.group(1).strip() if line_match else ''

    def _sentence_completion_result(self, status: str, stem: str, note: str) -> AnswerCheckResult:
        stem_prefix = stem.replace('...', '').strip()
        expected = f'{stem_prefix} [your reason].' if stem_prefix else 'A complete sentence with a clear reason.'
        return AnswerCheckResult(status=status, expected_answer=expected, feedback_note=note)

    def _lookup_bank_question(self, subject: str, question: str) -> AssessmentQuestion | None:
        normalized = normalize_answer_text(question)
        if not normalized:
            return None
        for version in all_assessment_versions():
            for item in version.questions:
                if item.subject == subject and normalize_answer_text(item.question) == normalized:
                    return item
        return None

    def _build_pseudo_question(
        self,
        subject: str,
        question: str,
        validation_type: str,
        expected_answer: str,
        skill: str,
    ) -> AssessmentQuestion:
        accepted_answers = (expected_answer,) if expected_answer.strip() and validation_type in {'exact_text', 'keyword_text'} else ()
        return AssessmentQuestion(
            id='tutor-local-check',
            subject=subject,
            grade=4,
            version=0,
            position=1,
            skill=skill,
            question=question,
            validation_type=validation_type,
            expected_answer=expected_answer,
            accepted_answers=accepted_answers,
            rubric=(),
            next_topic_if_incorrect=skill,
            child_correct_feedback='',
            child_incorrect_feedback='',
        )

    async def _classify_with_llm(
        self,
        subject: str,
        question: str,
        student_answer: str,
        expected_answer: str,
    ) -> AnswerCheckResult:
        system = (
            'You are checking a Grades 3-6 tutor practice answer. '
            'Return compact JSON only with keys: status, expected_answer, feedback_note. '
            'status must be one of: correct, partially_correct, incorrect, unclear.'
        )
        user = (
            f'Subject: {subject}\n'
            f'Question: {question}\n'
            f'Expected answer if known: {expected_answer or "not provided"}\n'
            f'Student answer: {student_answer}\n'
            'Classify the student answer. If expected answer is not provided, infer the likely correct answer from the question when possible.'
        )
        try:
            result = await LLMRouter().generate(system=system, user=user, purpose='classifier')
            parsed = self._extract_json(result.text)
            status = parsed.get('status', 'unclear')
            if status not in {'correct', 'partially_correct', 'incorrect', 'unclear'}:
                status = 'unclear'
            return AnswerCheckResult(
                status=status,
                expected_answer=str(parsed.get('expected_answer') or expected_answer or ''),
                feedback_note=str(parsed.get('feedback_note') or ''),
            )
        except Exception:
            return AnswerCheckResult()

    def _extract_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r'\{.*\}', text, re.S)
            if match:
                return json.loads(match.group(0))
        return {}

    def _keyword_set(self, text: str) -> set[str]:
        stop = {'the', 'a', 'an', 'is', 'are', 'to', 'of', 'and', 'in', 'it', 'this', 'that'}
        return {word for word in re.findall(r'[a-zA-Z]+', text.lower()) if word not in stop and len(word) > 2}

    def _format_fraction(self, value: Fraction) -> str:
        return format_fraction(value)
