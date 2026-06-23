from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from ..assessment_validation import extract_math_expression, format_fraction, normalize_math_text, safe_eval_expression
from ..models import TutorStepSupportState, TutoringState
from ..utils.attempt_policy import attempt_scope_key
from .llm.router import LLMRouter
from .tutor_question_type_router import infer_active_question_type


MAX_HELP_LEVEL = 4
MAX_HINT_CHARS = 260
MAX_FOLLOWUP_CHARS = 140


class StrictHintProposal(BaseModel):
    level: int = Field(ge=1, le=4)
    hint_kind: str
    hint_text: str
    follow_up_question: str = ''
    reveals_final_answer: bool = False


class TutorProgressiveHintGenerator:
    """Progressive math hints with a strict LLM fallback for non-arithmetic steps."""

    def __init__(self, router: LLMRouter | None = None) -> None:
        self.router = router or LLMRouter()

    async def build(
        self,
        state: TutoringState,
        *,
        help_request: bool,
    ) -> tuple[str, TutoringState, str, bool]:
        support = current_step_support(state)
        level = _next_help_level(state, support, help_request=help_request)
        hint_id = _hint_id(level)
        if hint_id in support.shown_hint_ids:
            level = min(MAX_HELP_LEVEL, level + 1)
            hint_id = _hint_id(level)

        if not _should_try_llm_fallback(state, level, support):
            reply, next_state = build_progressive_hint_reply(state, help_request=help_request)
            return reply, next_state, 'deterministic-progressive-hint', False

        proposal = await self._generate_strict_hint(state, level)
        if not proposal:
            reply, next_state = build_progressive_hint_reply(state, help_request=help_request)
            return reply, next_state, 'deterministic-progressive-hint', False

        question = _display_expression(_current_expression(state)) or state.current_question or state.current_step
        headings = {
            1: 'Here is the first hint.',
            2: 'Here is a stronger hint.',
            3: 'Let’s work one small part together.',
            4: 'Let’s finish this current step together.',
        }
        lines = [headings[level], '', proposal.hint_text.strip()]
        follow_up = proposal.follow_up_question.strip()
        if level < MAX_HELP_LEVEL:
            lines.extend(['', follow_up or f'Now try this step: {question}'])
        next_state = record_step_hint(state, level, f'llm_{hint_id}')
        return '\n'.join(lines), next_state, 'strict-llm-progressive-hint', True

    async def _generate_strict_hint(self, state: TutoringState, level: int) -> StrictHintProposal | None:
        expected_kind = _hint_id(level)
        system = (
            'You are a strict Grades 3-6 Math tutor hint generator. Return one JSON object only. '
            'Use the supplied schema exactly. Give guidance for only the current step. '
            'Do not solve the final answer unless level is 4. '
            'Keep the wording short, warm, and child friendly. '
            f'JSON schema: {json.dumps(StrictHintProposal.model_json_schema(), separators=(",", ":"))}'
        )
        user = json.dumps({
            'level': level,
            'required_hint_kind': expected_kind,
            'question_type': infer_active_question_type(state),
            'skill': state.skill,
            'topic': state.tutor_practice_topic,
            'current_problem': state.full_problem or state.main_problem or state.active_problem,
            'current_step': state.current_step or state.current_question,
            'current_question': state.current_question,
            'expected_answer': state.expected_answer,
            'answer_label': state.answer_label,
            'already_shown_hint_ids': current_step_support(state).shown_hint_ids,
            'rules': [
                'For levels 1-3, do not include the expected answer.',
                'For levels 1-2, do not do calculations; only guide thinking.',
                'For level 3, do at most one small substep and ask the student to try the next tiny part.',
                'For level 4, solve only the current step, not unrelated future steps.',
            ],
        }, separators=(',', ':'))
        try:
            result = await self.router.generate(system=system, user=user, purpose='classifier')
            proposal = StrictHintProposal.model_validate(_extract_json(result.text))
        except Exception:
            return None
        return proposal if _validate_llm_hint(proposal, state, level) else None


def current_step_support(state: TutoringState) -> TutorStepSupportState:
    key = attempt_scope_key(state)
    return state.support_per_step.get(key, TutorStepSupportState())


def record_step_hint(state: TutoringState, help_level: int, hint_id: str) -> TutoringState:
    key = attempt_scope_key(state)
    support = current_step_support(state)
    shown = list(support.shown_hint_ids)
    if hint_id and hint_id not in shown:
        shown.append(hint_id)
    support_map = dict(state.support_per_step)
    support_map[key] = TutorStepSupportState(
        help_level=max(support.help_level, help_level),
        shown_hint_ids=shown,
    )
    return state.model_copy(update={
        'support_per_step': support_map,
        'hint_given': True,
        'student_answer': state.student_answer,
        'status': 'waiting_for_student',
    })


def build_progressive_hint_reply(state: TutoringState, *, help_request: bool) -> tuple[str, TutoringState]:
    support = current_step_support(state)
    level = _next_help_level(state, support, help_request=help_request)

    hint_id = _hint_id(level)
    if hint_id in support.shown_hint_ids:
        level = min(MAX_HELP_LEVEL, level + 1)
        hint_id = _hint_id(level)
    if hint_id in support.shown_hint_ids:
        question = _display_expression(_current_expression(state)) or state.current_question or state.current_step
        return (
            f'We have already worked through every hint for this step.\n\n'
            f'**Current step:** {question}',
            state,
        )

    expression = _current_expression(state)
    hint = _hint_for_state(state, level)
    question = _display_expression(expression) or state.current_question or state.current_step
    headings = {
        1: 'Here is the first hint.',
        2: 'Here is a stronger hint.',
        3: 'Let’s work one small part together.',
        4: 'Let’s finish this current step together.',
    }
    lines = [headings[level], '', hint]
    if level < MAX_HELP_LEVEL and question and '?' not in hint:
        lines.extend(['', f'Now try this step: {question}'])
    next_state = record_step_hint(state, level, hint_id)
    return '\n'.join(lines), next_state


async def build_progressive_hint_reply_with_fallback(
    state: TutoringState,
    *,
    help_request: bool,
    router: LLMRouter | None = None,
) -> tuple[str, TutoringState, str, bool]:
    return await TutorProgressiveHintGenerator(router).build(state, help_request=help_request)


def _next_help_level(state: TutoringState, support: TutorStepSupportState, *, help_request: bool) -> int:
    requested_level = support.help_level + 1 if help_request else max(1, state.attempt_count)
    return min(MAX_HELP_LEVEL, max(requested_level, state.attempt_count, support.help_level))


def _hint_id(level: int) -> str:
    return {
        1: 'concept',
        2: 'strategy',
        3: 'worked_substep',
        4: 'worked_step',
    }[level]


def _should_try_llm_fallback(state: TutoringState, level: int, support: TutorStepSupportState) -> bool:
    if level >= MAX_HELP_LEVEL:
        return False
    hint_id = _hint_id(level)
    if f'llm_{hint_id}' in support.shown_hint_ids:
        return False
    question_type = infer_active_question_type(state)
    if question_type in {'fraction_comparison', 'equivalent_fraction', 'conceptual_math', 'word_problem'}:
        return True
    expression = _current_expression(state)
    if _simple_expression(expression):
        return False
    if state.problem_kind == 'word_problem':
        return True
    current_text = ' '.join([state.full_problem, state.main_problem, state.active_problem, state.current_step, state.current_question]).lower()
    return bool(re.search(r'[a-z]{3,}', current_text)) and bool(re.search(r'\d', current_text))


def _validate_llm_hint(proposal: StrictHintProposal, state: TutoringState, level: int) -> bool:
    if proposal.level != level or proposal.hint_kind != _hint_id(level):
        return False
    hint = ' '.join(proposal.hint_text.strip().split())
    follow_up = ' '.join(proposal.follow_up_question.strip().split())
    if not hint or len(hint) > MAX_HINT_CHARS or len(follow_up) > MAX_FOLLOWUP_CHARS:
        return False
    if hint.count('?') + follow_up.count('?') > 1:
        return False
    expected = str(state.expected_answer or '').strip()
    combined = f'{hint} {follow_up}'.lower()
    if level < MAX_HELP_LEVEL:
        if proposal.reveals_final_answer:
            return False
        if expected and re.search(rf'(?<![\d/]){re.escape(expected.lower())}(?![\d/])', combined):
            return False
        if re.search(r'\b(?:the\s+)?answer\s+(?:is|equals|=)\b|\bfinal answer\b', combined):
            return False
    if not _hint_matches_question_route(hint, follow_up, state, level):
        return False
    return True


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', str(text or ''), re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {}


def _current_expression(state: TutoringState) -> str:
    source = state.current_step or state.current_question or state.active_problem
    normalized = normalize_math_text(source)
    return extract_math_expression(normalized) or normalized.strip()


def _hint_for_state(state: TutoringState, level: int) -> str:
    question_type = infer_active_question_type(state)
    if question_type == 'fraction_comparison':
        return _fraction_comparison_hint(state, level)
    if question_type == 'equivalent_fraction':
        return _equivalent_fraction_hint(state, level)
    if question_type == 'conceptual_math':
        return _conceptual_math_hint(state, level)

    expression = _current_expression(state)
    parsed = _simple_expression(expression)
    if not parsed:
        if level == 1:
            return 'Focus only on the current step and identify what the question asks you to find.'
        if level == 2:
            return 'Name the operation for this step, then use only the numbers shown in it.'
        if level == 3:
            return 'Write the operation as a number sentence before calculating.'
        return f'The current step result is {state.expected_answer}.' if state.expected_answer else 'Work through the current number sentence one operation at a time.'

    left, operator, right = parsed
    if level == 1:
        return _concept_hint(left, operator, right)
    if level == 2:
        return _strategy_hint(left, operator, right)
    if level == 3:
        return _worked_substep_hint(left, operator, right)

    value = safe_eval_expression(f'{left} {operator} {right}')
    answer = format_fraction(value) if value is not None else state.expected_answer
    return f'{_display_expression(left)} {_display_operator(operator)} {_display_expression(right)} = {answer}.'


def _fraction_comparison_hint(state: TutoringState, level: int) -> str:
    choices = _comparison_choices(state)
    if len(choices) < 2:
        return _conceptual_math_hint(state, level)
    left, right = choices[0], choices[1]
    left_num, left_den = _fraction_parts(left)
    right_num, right_den = _fraction_parts(right)
    if level == 1:
        if left_den and left_den == right_den:
            return 'Both fractions have the same denominator, so look closely at the numerators.'
        return 'Compare the two fractions by noticing which amount is larger.'
    if level == 2:
        if left_den and left_den == right_den:
            return f'Both fractions are in {left_den}ths. Decide which numerator is greater: {left_num} or {right_num}.'
        return f'Look at the two choices carefully: {left} and {right}. Which one shows more of the whole?'
    if level == 3:
        if left_den and left_den == right_den:
            bigger = left if int(left_num) > int(right_num) else right
            return f'When the denominators match, the fraction with the bigger numerator is larger. Now choose between {left} and {right}.'
        return f'Say each choice out loud as part of a whole, then decide whether {left} or {right} is larger.'
    expected = state.expected_answer or left
    return f'The larger fraction here is {expected}.'


def _equivalent_fraction_hint(state: TutoringState, level: int) -> str:
    choices = _comparison_choices(state)
    prompt = ' '.join([state.current_question, state.current_step, state.active_problem]).lower()
    target_fraction = _first_fraction_in_text(prompt)
    if level == 1:
        return 'Equivalent fractions name the same amount, even if the numbers look different.'
    if level == 2:
        if target_fraction:
            return f'Think about which choice shows the same amount as {target_fraction}.'
        return 'Look for the choice that keeps the same amount of the whole.'
    if level == 3:
        if choices:
            return f'Check each choice one at a time and keep the one that matches the same amount.'
        return 'Write the starting fraction and compare it to the answer choice you picked.'
    expected = state.expected_answer or (choices[0] if choices else '')
    return f'The equivalent fraction for this step is {expected}.'


def _conceptual_math_hint(state: TutoringState, level: int) -> str:
    prompt = ' '.join([state.current_question, state.current_step, state.active_problem]).lower()
    if 'whole' in prompt and ('fourths' in prompt or 'fourths' in state.current_question.lower()):
        if level == 1:
            return 'A whole is made of all the equal parts together.'
        if level == 2:
            return 'If something is split into fourths, count how many fourth-size pieces make the full whole.'
        if level == 3:
            return 'Four fourths make one whole, so count 1/4, 2/4, 3/4, 4/4.'
        return f'The current step answer is {state.expected_answer}.' if state.expected_answer else 'The whole is made from all of the equal parts.'
    if level == 1:
        return 'Focus on the Math idea the question is asking about before you calculate anything.'
    if level == 2:
        return 'Use the words in the question to decide what Math rule or meaning fits this step.'
    if level == 3:
        return 'Say the Math idea in your own words, then use that idea to answer the question.'
    return f'The current step answer is {state.expected_answer}.' if state.expected_answer else 'Use the Math idea from the question to finish the step.'


def _hint_matches_question_route(hint: str, follow_up: str, state: TutoringState, level: int) -> bool:
    combined = f'{hint} {follow_up}'.lower()
    question_type = infer_active_question_type(state)
    current_text = ' '.join([
        str(state.full_problem or ''),
        str(state.main_problem or ''),
        str(state.active_problem or ''),
        str(state.current_step or ''),
        str(state.current_question or ''),
    ]).lower()

    if question_type == 'fraction_comparison':
        choices = _comparison_choices(state)
        allowed_markers = {'fraction', 'fractions', 'larger', 'greater', 'numerator', 'denominator', 'same'}
        if not any(marker in combined for marker in allowed_markers):
            return False
        if level < MAX_HELP_LEVEL and 'multiplication fact' in combined:
            return False
        if choices and not any(choice.lower().replace(' ', '') in combined.replace(' ', '') for choice in choices):
            return 'numerator' in combined or 'denominator' in combined
    if question_type == 'equivalent_fraction':
        if not any(marker in combined for marker in {'equivalent', 'same amount', 'fraction', 'whole'}):
            return False
        if level < MAX_HELP_LEVEL and any(marker in combined for marker in {'larger', 'greater'}) and 'same amount' not in combined:
            return False
    if question_type == 'conceptual_math':
        if 'what is' in combined and level < 4:
            return False
        if not any(token in current_text for token in ('fraction', 'whole', 'numerator', 'denominator', 'decimal', 'ratio', 'percent')):
            return True
        if not any(token in combined for token in ('whole', 'part', 'fraction', 'numerator', 'denominator', 'decimal', 'ratio', 'percent')):
            return False
    if question_type == 'word_problem':
        numbers = re.findall(r'-?\d+(?:\.\d+)?(?:/\d+)?', current_text)
        if numbers and not any(number in combined for number in numbers[:3]):
            if not any(marker in combined for marker in ('total', 'altogether', 'occupied', 'empty', 'difference', 'groups', 'each', 'rows', 'seats', 'whole')):
                return False
    return True


def _comparison_choices(state: TutoringState) -> list[str]:
    text = ' '.join([
        str(state.current_question or ''),
        str(state.current_step or ''),
        str(state.active_problem or ''),
    ])
    matches = re.findall(r'-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+(?:\.\d+)?)?%?', text)
    choices: list[str] = []
    seen: set[str] = set()
    for match in matches:
        cleaned = match.replace(' ', '')
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            choices.append(cleaned)
    return choices[:2]


def _fraction_parts(value: str) -> tuple[str, str]:
    match = re.fullmatch(r'(-?\d+)\s*/\s*(-?\d+)', str(value or '').strip())
    if not match:
        return '', ''
    return match.group(1), match.group(2)


def _first_fraction_in_text(text: str) -> str:
    match = re.search(r'-?\d+\s*/\s*-?\d+', str(text or ''))
    return match.group(0).replace(' ', '') if match else ''


def _simple_expression(expression: str) -> tuple[str, str, str] | None:
    compact = str(expression or '').replace(' ', '')
    match = re.fullmatch(r'(-?\d+(?:\.\d+)?(?:/\d+)?)?([+\-*/])(-?\d+(?:\.\d+)?(?:/\d+)?)', compact)
    if not match or not match.group(1):
        return None
    return match.group(1), match.group(2), match.group(3)


def _concept_hint(left: str, operator: str, right: str) -> str:
    if operator == '*':
        return f'Think of {_display_expression(left)} groups with {_display_expression(right)} in each group.'
    if operator == '/':
        return f'Think of sharing {_display_expression(left)} equally into {_display_expression(right)} groups.'
    if operator == '+':
        return 'Addition combines the two amounts. Keep the place values lined up.'
    return 'Subtraction finds how much remains or the difference between the two amounts.'


def _strategy_hint(left: str, operator: str, right: str) -> str:
    left_int = _whole_number(left)
    right_int = _whole_number(right)
    if operator == '*' and left_int is not None and right_int is not None:
        split = _multiplication_split(left_int, right_int)
        if split:
            first_left, first_right, second_left, second_right = split
            split_value = first_left + second_left if first_right == second_right else first_right + second_right
            first_part = first_left if first_right == second_right else first_right
            second_part = second_left if first_right == second_right else second_right
            return f'Break {split_value} into {first_part} and {second_part}. First find {first_left} × {first_right}.'
    if operator == '/' and left_int is not None and right_int:
        return f'Use the related multiplication fact: {right_int} × ? = {left_int}.'
    if operator == '+':
        return 'Add the ones first, then the tens, then any larger place values.'
    if operator == '-':
        return f'Subtract {_display_expression(right)} in smaller place-value parts from {_display_expression(left)}.'
    return f'Work with {_display_expression(left)} {_display_operator(operator)} {_display_expression(right)} one place value at a time.'


def _worked_substep_hint(left: str, operator: str, right: str) -> str:
    left_int = _whole_number(left)
    right_int = _whole_number(right)
    if operator == '*' and left_int is not None and right_int is not None:
        split = _multiplication_split(left_int, right_int)
        if split:
            first_left, first_right, second_left, second_right = split
            partial = first_left * first_right
            return f'{first_left} × {first_right} = {partial}. Now find {second_left} × {second_right}.'
    if operator == '/' and left_int is not None and right_int:
        chunk_groups = min(5, left_int // right_int)
        if chunk_groups > 0:
            chunk = chunk_groups * right_int
            remaining = left_int - chunk
            if remaining:
                return f'{right_int} × {chunk_groups} = {chunk}, leaving {remaining}. How many groups of {right_int} fit into {remaining}?'
        return f'Use {right_int} × ? = {left_int} to find the quotient.'
    if operator == '+' and left_int is not None and right_int is not None:
        ones = left_int % 10 + right_int % 10
        return f'The ones are {left_int % 10} + {right_int % 10} = {ones}. Now add the remaining place values.'
    if operator == '-' and left_int is not None and right_int is not None:
        tens_part = (right_int // 10) * 10
        if tens_part:
            partial = left_int - tens_part
            return f'First subtract the tens: {left_int} - {tens_part} = {partial}. Now subtract {right_int - tens_part}.'
    value = safe_eval_expression(f'{left} {operator} {right}')
    answer = format_fraction(value) if value is not None else ''
    return f'Work this small calculation: {_display_expression(left)} {_display_operator(operator)} {_display_expression(right)}{f" = {answer}" if answer else ""}.'


def _multiplication_split(left: int, right: int) -> tuple[int, int, int, int] | None:
    split_right = right >= 10
    split_value, fixed = (right, left) if split_right else (left, right)
    place = 10 ** (len(str(abs(split_value))) - 1)
    tens = (split_value // place) * place
    remainder = split_value - tens
    if tens and remainder:
        return (fixed, tens, fixed, remainder) if split_right else (tens, fixed, remainder, fixed)
    return None


def _whole_number(value: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _display_operator(operator: str) -> str:
    return {'*': '×', '/': '÷'}.get(operator, operator)


def _display_expression(expression: str) -> str:
    return str(expression or '').replace('*', ' × ').replace('/', ' ÷ ')
