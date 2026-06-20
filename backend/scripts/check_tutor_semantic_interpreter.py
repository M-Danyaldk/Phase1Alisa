import asyncio
import json
from types import SimpleNamespace

from backend.app.models import ChatHistoryItem, TutoringState
from backend.app.services.tutor_intent_classifier import TutorIntentClassifier
from backend.app.services.tutor_math_normalizer import TutorMathNormalizer
from backend.app.services.tutor_semantic_interpreter import TutorSemanticInterpreter


class FakeRouter:
    def __init__(self, payload: dict | None = None, *, raw: str = '', error: Exception | None = None) -> None:
        self.payload = payload
        self.raw = raw
        self.error = error
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        text = self.raw or json.dumps(self.payload)
        return SimpleNamespace(text=text, provider='fake', model='fake-schema', fallback_used=False)


def _payload(**updates) -> dict:
    payload = {
        'schema_version': '1.0',
        'intent': 'answer_current_step',
        'confidence': 'high',
        'answer': '78',
        'normalized_expression': None,
        'problem': None,
        'refers_to_task': 'active_task',
        'requested_action': 'check_answer',
        'emotion': None,
        'needs_clarification': False,
        'clarification_question': None,
        'interpretation_note': 'Student marked 78 as the intended final answer.',
    }
    payload.update(updates)
    return payload


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def main() -> None:
    failures: list[str] = []
    state = TutoringState(
        current_subject='Math',
        active_problem='72 + 48',
        current_step='72 + 48',
        current_question='What is 72 + 48?',
        expected_answer='120',
        problem_status='awaiting_step',
        mode='practice',
        status='waiting_for_student',
    )
    history = [ChatHistoryItem(role='msalisia', content='What is 72 + 48?')]

    answer_router = FakeRouter(_payload())
    answer_classifier = TutorIntentClassifier(TutorSemanticInterpreter(answer_router))
    answer_result = await answer_classifier.classify_if_needed(
        'Math',
        'I got 80 first, but my final answer should be 78.',
        history,
        state,
    )
    _expect(answer_router.calls == 1, 'Ambiguous answer wording did not invoke the semantic interpreter exactly once.', failures)
    _expect(answer_result.label == 'answer_current_step', 'High-confidence semantic answer did not route to the current step.', failures)
    _expect(answer_result.answer == '78', 'Semantic interpreter did not preserve the extracted final answer.', failures)
    _expect(answer_result.interpretation_source == 'llm_schema', 'Semantic result did not record its schema source.', failures)
    _expect(
        not TutorMathNormalizer().should_use_fallback('Math', 'I got 80 first, but my final answer should be 78.', state),
        'Flexible answer wording was sent through the expression normalizer before semantic interpretation.',
        failures,
    )

    word_answer_router = FakeRouter(_payload())
    word_answer_classifier = TutorIntentClassifier(TutorSemanticInterpreter(word_answer_router))
    word_answer_result = await word_answer_classifier.classify_if_needed('Math', 'seventy-eight', history, state)
    _expect(word_answer_router.calls == 1, 'Number-word answer did not invoke semantic interpretation.', failures)
    _expect(word_answer_result.label == 'answer_current_step' and word_answer_result.answer == '78', 'Number-word answer was not extracted safely.', failures)

    deterministic_router = FakeRouter(_payload())
    deterministic_classifier = TutorIntentClassifier(TutorSemanticInterpreter(deterministic_router))
    deterministic_result = await deterministic_classifier.classify_if_needed('Math', '120', history, state)
    _expect(deterministic_result.label == 'answer_current_step', 'Clear numeric answer stopped using deterministic routing.', failures)
    _expect(deterministic_router.calls == 0, 'Clear numeric answer unnecessarily invoked the LLM.', failures)

    switch_router = FakeRouter(_payload(
        intent='switch_problem',
        confidence='medium',
        answer=None,
        normalized_expression='64 + 55',
        refers_to_task='new_task',
        requested_action='switch',
        interpretation_note='Student may want to solve a different expression first.',
    ))
    switch_classifier = TutorIntentClassifier(TutorSemanticInterpreter(switch_router))
    switch_result = await switch_classifier.classify_if_needed(
        'Math',
        'Maybe leave that one for now and do 64 + 55.',
        history,
        state,
    )
    _expect(switch_result.label == 'clarification_about_context', 'Medium-confidence task switch was applied without clarification.', failures)
    _expect(switch_result.needs_clarification, 'Medium-confidence task switch did not request clarification.', failures)

    related_router = FakeRouter(_payload(
        intent='related_question',
        confidence='medium',
        answer=None,
        refers_to_task='active_task',
        requested_action='explain',
        interpretation_note='Student is asking where the regrouping came from.',
    ))
    related_classifier = TutorIntentClassifier(TutorSemanticInterpreter(related_router))
    related_result = await related_classifier.classify_if_needed(
        'Math',
        'I mean, where did that regrouping come from?',
        history,
        state,
    )
    _expect(related_result.label == 'related_question', 'Medium-confidence non-mutating explanation request was not allowed.', failures)
    _expect(not related_result.needs_clarification, 'Clear non-mutating explanation request was unnecessarily blocked.', failures)

    invalid_router = FakeRouter({**_payload(), 'active_problem': 'hijacked'})
    invalid_classifier = TutorIntentClassifier(TutorSemanticInterpreter(invalid_router))
    invalid_result = await invalid_classifier.classify_if_needed(
        'Math',
        'I got 80 first, but my final answer should be 78.',
        history,
        state,
    )
    _expect(invalid_result.label == 'clarification_about_context', 'Invalid schema output did not fall back to clarification.', failures)
    _expect(invalid_result.needs_clarification, 'Invalid schema output did not preserve the current state safely.', failures)

    timeout_router = FakeRouter(error=TimeoutError('classifier timeout'))
    timeout_classifier = TutorIntentClassifier(TutorSemanticInterpreter(timeout_router))
    timeout_result = await timeout_classifier.classify_if_needed(
        'Math',
        'I got 80 first, but my final answer should be 78.',
        history,
        state,
    )
    _expect(timeout_result.label == 'clarification_about_context', 'LLM timeout did not fall back to clarification.', failures)
    _expect(timeout_result.answer == '', 'LLM timeout invented an answer.', failures)

    if failures:
        print('Tutor semantic interpreter check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor semantic interpreter check passed.')
    print('- Clear inputs stay deterministic and do not call the LLM.')
    print('- Flexible answer language is extracted through the strict schema.')
    print('- Medium-confidence state changes, malformed output, and timeouts become safe clarification.')
    print('- Medium-confidence non-mutating explanation requests can proceed without changing task state.')


if __name__ == '__main__':
    asyncio.run(main())
