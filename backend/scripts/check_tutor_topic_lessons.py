import asyncio

from backend.app.services.tutor_answer_checker import TutorAnswerChecker
from backend.app.services.tutor_intent_classifier import MATH_TOPIC_ALIASES
from backend.app.tutor_math_topic_lessons import all_topic_lessons, build_topic_lesson_intro, topic_lesson


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def main() -> None:
    failures: list[str] = []
    lessons = all_topic_lessons()
    lesson_keys = {lesson.topic_key for lesson in lessons}
    alias_keys = set(MATH_TOPIC_ALIASES)

    _expect(alias_keys <= lesson_keys, f'Topic lesson catalog is missing keys: {sorted(alias_keys - lesson_keys)}', failures)

    checker = TutorAnswerChecker()
    for lesson in lessons:
        _expect(topic_lesson(lesson.topic_key) == lesson, f'{lesson.topic_key} could not be loaded by key.', failures)
        for field_name in (
            'label',
            'explanation',
            'example',
            'starter_question',
            'expected_answer',
            'hint_1',
            'hint_2',
            'worked_explanation',
        ):
            value = getattr(lesson, field_name)
            _expect(bool(str(value).strip()), f'{lesson.topic_key} has empty {field_name}.', failures)

        intro = build_topic_lesson_intro(lesson)
        _expect(lesson.label.lower() in intro.lower(), f'{lesson.topic_key} intro does not mention the label.', failures)
        _expect(lesson.explanation in intro, f'{lesson.topic_key} intro does not include the explanation.', failures)
        _expect(lesson.example in intro, f'{lesson.topic_key} intro does not include the example.', failures)
        _expect(lesson.starter_question in intro, f'{lesson.topic_key} intro does not include the starter question.', failures)
        _expect('Now try one' in intro, f'{lesson.topic_key} intro does not move to a question.', failures)

        answer_check = await checker.check('Math', lesson.starter_question, lesson.expected_answer, lesson.expected_answer)
        _expect(
            answer_check.is_correct,
            f'{lesson.topic_key} starter answer was not checkable as correct: {answer_check}.',
            failures,
        )

    if failures:
        print('Tutor topic lesson check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor topic lesson check passed.')
    print('- Every known Math topic has a deterministic mini-lesson.')
    print('- Every mini-lesson includes explanation, example, starter question, hints, and worked answer.')
    print('- Starter answers are accepted by the existing answer checker.')


if __name__ == '__main__':
    asyncio.run(main())
