from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CRITICAL_PYTHON_FILES = [
    'backend/app/main.py',
    'backend/app/services/voice_service.py',
    'backend/app/services/tutor_intent_classifier.py',
    'backend/app/services/tutor_semantic_interpreter.py',
    'backend/app/services/tutor_semantic_policy.py',
    'backend/app/services/tutor_math_response_guard.py',
    'backend/app/services/tutor_word_problem.py',
    'backend/app/schemas/tutor_interpretation.py',
    'backend/app/utils/task_lifecycle.py',
    'backend/scripts/check_tutor_flow_all.py',
]

REQUIRED_FLOW_CHECKS = [
    'check_tutoring_ladder',
    'check_tutor_flow_architecture',
    'check_tutor_edge_matrix',
    'check_tutor_intent_routing',
    'check_tutor_task_lifecycle',
    'check_tutor_attempt_policy',
    'check_tutor_word_problem_schema',
    'check_tutor_interpretation_schema',
    'check_tutor_semantic_interpreter',
    'check_tutor_semantic_policy',
    'check_tutor_emotional_support',
    'check_tutor_math_response_guard',
    'check_tutor_math_e2e',
    'check_tutor_voice_parity',
    'check_tutor_generated_invariants',
    'check_tutor_production_readiness',
]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding='utf-8')


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _index(text: str, needle: str) -> int:
    return text.find(needle)


def _ordered(text: str, *needles: str) -> bool:
    cursor = -1
    for needle in needles:
        position = text.find(needle, cursor + 1)
        if position == -1:
            return False
        cursor = position
    return True


def _assert_parseable(relative_path: str, failures: list[str]) -> None:
    try:
        ast.parse(_read(relative_path), filename=relative_path)
    except SyntaxError as exc:
        failures.append(f'{relative_path} is not parseable Python: {exc}')


def _assert_no_conflict_markers(relative_path: str, failures: list[str]) -> None:
    text = _read(relative_path)
    markers = ('<<<<<<<', '=======', '>>>>>>>')
    if any(marker in text for marker in markers):
        failures.append(f'{relative_path} contains unresolved merge-conflict markers.')


def main() -> None:
    failures: list[str] = []

    for relative_path in CRITICAL_PYTHON_FILES:
        _assert_parseable(relative_path, failures)
        _assert_no_conflict_markers(relative_path, failures)

    flow_all = _read('backend/scripts/check_tutor_flow_all.py')
    for module_name in REQUIRED_FLOW_CHECKS:
        _expect(module_name in flow_all, f'Full tutor suite is missing {module_name}.', failures)

    schema = _read('backend/app/schemas/tutor_interpretation.py')
    _expect("extra='forbid'" in schema and 'strict=True' in schema, 'Tutor interpretation schemas are not strict/closed.', failures)
    _expect('safe_eval_expression' in schema, 'Tutor schema no longer requires deterministic expression validation.', failures)
    _expect('Low-confidence interpretations must request clarification' in schema, 'Low-confidence semantic payloads are not forced to clarify.', failures)

    classifier = _read('backend/app/services/tutor_intent_classifier.py')
    _expect('TutorSemanticInterpreter' in classifier, 'Intent classifier is not wired to the semantic interpreter.', failures)
    _expect('TutorSemanticPolicy' in classifier, 'Intent classifier is not wired to the semantic policy.', failures)
    _expect('self.semantic_policy.resolve' in classifier, 'Intent classifier does not route LLM interpretation through deterministic policy.', failures)

    interpreter = _read('backend/app/services/tutor_semantic_interpreter.py')
    _expect('TutorInputInterpretation.model_validate' in interpreter, 'Semantic interpreter does not validate against the strict Pydantic schema.', failures)
    _expect("intent='unclear'" in interpreter, 'Semantic interpreter lacks safe unclear fallback.', failures)

    guard = _read('backend/app/services/tutor_math_response_guard.py')
    _expect('reconcile_task_lifecycle(state)' in guard, 'Response guard does not verify lifecycle state before validation/repair.', failures)
    _expect('active_problem or state.main_problem' in guard, 'Response guard does not prefer the active problem over stale main_problem.', failures)

    word_problem = _read('backend/app/services/tutor_word_problem.py')
    _expect('StructuredMathProblem.model_validate' in word_problem, 'Word-problem LLM output is not validated through the strict schema.', failures)
    _expect('safe_eval_expression' in word_problem, 'Word-problem expression is not deterministically checked.', failures)

    for surface in ('backend/app/main.py', 'backend/app/services/voice_service.py'):
        source = _read(surface)
        _expect('reconcile_task_lifecycle' in source, f'{surface} is missing lifecycle reconciliation.', failures)
        _expect('TutorIntentClassifier().classify_if_needed' in source, f'{surface} is missing intent classification.', failures)
        _expect('TutorMathResponseGuard()' in source, f'{surface} is missing Math response guard.', failures)
        _expect('math_response_guard.validate' in source, f'{surface} does not validate Math replies.', failures)
        _expect('math_response_guard.apply_metadata' in source, f'{surface} does not store response-guard metadata.', failures)
        _expect(
            _index(source, 'reconcile_task_lifecycle') < _index(source, 'TutorIntentClassifier().classify_if_needed'),
            f'{surface} classifies intent before lifecycle reconciliation.',
            failures,
        )
        _expect(
            _ordered(source, 'TutorMathResponseGuard()', 'math_response_guard.validate', 'math_response_guard.apply_metadata'),
            f'{surface} response guard validate/apply order is not intact.',
            failures,
        )

    if failures:
        print('Tutor production-readiness check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor production-readiness check passed.')
    print('- Critical Math tutor files parse cleanly and contain no conflict markers.')
    print('- Full verification suite includes lifecycle, semantic, guard, chat, and voice checks.')
    print('- Chat and voice both use lifecycle reconciliation, strict semantic policy, and response guarding.')


if __name__ == '__main__':
    main()
