import asyncio

from backend.app.models import TutoringState
from backend.app.services.tutor_word_problem import StructuredWordProblem, TutorWordProblemInterpreter, apply_word_problem_state
from backend.app.utils.multi_step_progress import has_structured_math_problem, update_multi_step_progress


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


async def _run() -> list[str]:
    failures: list[str] = []
    interpreter = TutorWordProblemInterpreter()
    boxes = await interpreter.interpret_if_needed('Math', 'There are 7 boxes and each box has a capacity of 2 balls. How many balls are needed?')
    _expect(boxes.accepted, 'Equal-groups word problem was not accepted.', failures)
    _expect(boxes.expression == '7 * 2' and boxes.expected_answer == '14', 'Equal-groups schema was incorrect.', failures)
    auditorium = await interpreter.interpret_if_needed('Math', 'An auditorium has 28 rows with 35 seats in each row. If 180 students attend, how many seats are empty?')
    _expect(auditorium.expression == '28 * 35 - 180', 'Multi-step seat expression was incorrect.', failures)
    _expect(auditorium.expected_answer == '800', 'Multi-step seat answer was not verified.', failures)
    cookies = await interpreter.interpret_if_needed('Math', 'A bakery made 72 cookies, sold 48, then baked 36 more. How many cookies are there now?')
    _expect(cookies.expression == '72 - 48 + 36' and cookies.expected_answer == '60', 'Subtract-then-add schema was incorrect.', failures)
    shared = await interpreter.interpret_if_needed('Math', '24 balls are shared equally among 6 boxes. How many balls go in each box?')
    _expect(shared.expression == '24 / 6' and shared.expected_answer == '4', 'Equal-sharing problem was not treated as division.', failures)
    reversed_shared = await interpreter.interpret_if_needed('Math', '6 children share 24 balls equally. How many balls does each child get?')
    _expect(reversed_shared.expression == '24 / 6' and reversed_shared.expected_answer == '4', 'Separated equal-sharing language was mistaken for multiplication.', failures)
    word_number_shared = await interpreter.interpret_if_needed('Math', 'Four trays share 24 muffins equally. How many muffins go on each tray?')
    _expect(word_number_shared.expression == '24 / 4' and word_number_shared.expected_answer == '6', 'A number-word quantity bypassed equal-sharing interpretation.', failures)
    group_count = await interpreter.interpret_if_needed('Math', 'There are 24 balls and each box holds 6 balls. How many boxes are needed?')
    _expect(group_count.expression == '24 / 6' and group_count.expected_answer == '4', 'Unknown-group problem was not treated as division.', failures)
    reversed_group_count = await interpreter.interpret_if_needed('Math', 'Each box holds 6 balls and there are 24 balls total. How many boxes are needed?')
    _expect(reversed_group_count.expression == '24 / 6' and reversed_group_count.expected_answer == '4', 'Reordered unknown-group quantities changed the division direction.', failures)
    capacity_group_count = await interpreter.interpret_if_needed('Math', 'A tray holds 6 muffins. How many trays are needed for 24 muffins?')
    _expect(capacity_group_count.expression == '24 / 6' and capacity_group_count.expected_answer == '4', 'Capacity wording reversed total and per-group quantities.', failures)
    fractional_sharing = await interpreter.interpret_if_needed('Math', 'Split 1/2 gallon equally among 2 children. How much does each child get?')
    _expect(fractional_sharing.expression == '1/2 / 2' and fractional_sharing.expected_answer == '1/4', 'Fractional equal sharing used the wrong division direction.', failures)
    comparison = await interpreter.interpret_if_needed('Math', 'Mia has 3 marbles and Sam has 8 marbles. How many more marbles does Sam have?')
    _expect(comparison.expression == '8 - 3' and comparison.expected_answer == '5', 'Comparison wording was not treated as a positive difference.', failures)
    inverse_comparison = await interpreter.interpret_if_needed('Math', 'Kim has 14 marbles, which is 5 more than Jo. How many marbles does Jo have?')
    _expect(inverse_comparison.expression == '14 - 5' and inverse_comparison.expected_answer == '9', 'Inverse comparison wording was incorrectly added.', failures)
    occupied = await interpreter.interpret_if_needed('Math', 'A bus has 40 seats and 13 are occupied. How many seats are empty?')
    _expect(occupied.expression == '40 - 13' and occupied.expected_answer == '27', 'Occupied/empty complement wording was not subtraction.', failures)
    cited = await interpreter.interpret_if_needed('Math', 'An auditorium has 28 rows with 35 seats in each row [cite: 1.3.12]. If 180 students attend, how many seats are empty?')
    _expect(cited.expression == '28 * 35 - 180' and cited.expected_answer == '800', 'Citation numbers contaminated the word-problem quantities.', failures)
    fraction = await interpreter.interpret_if_needed('Math', 'Mia ate 1/4 of a pizza and Sam ate 2/4. How much did they eat in total?')
    _expect(fraction.expression == '1/4 + 2/4' and fraction.expected_answer == '3/4', 'Fraction quantities were not parsed safely.', failures)
    extra_quantity = interpreter._deterministic_parse('4 children each have 3 marbles and then receive 2 more. How many marbles are there?')
    _expect(not extra_quantity.expression, 'An unsupported third quantity was silently ignored.', failures)
    ambiguous = await interpreter.interpret_if_needed('Math', 'There are 7 red cards and 3 blue cards. Which color is nicer?')
    _expect(not ambiguous.accepted, 'Ambiguous prose was incorrectly converted into arithmetic.', failures)
    hallucinated = StructuredWordProblem(original_text='There are 7 boxes with 2 balls each.', expression='7 * 999', confidence='high', source='llm')
    _expect(not interpreter._validate(hallucinated.original_text, hallucinated).accepted, 'A hallucinated quantity passed validation.', failures)
    duplicated = StructuredWordProblem(original_text='There are 7 boxes with 2 balls each.', expression='7 * 7', confidence='high', source='llm')
    _expect(not interpreter._validate(duplicated.original_text, duplicated).accepted, 'A duplicated quantity passed validation.', failures)
    wrong_operation = StructuredWordProblem(original_text='There are 7 boxes with 2 balls each.', expression='7 + 2', confidence='high', source='llm')
    _expect(not interpreter._validate(wrong_operation.original_text, wrong_operation).accepted, 'An LLM operation that contradicted the wording passed validation.', failures)
    initial = TutoringState(current_subject='Math')
    box_state = apply_word_problem_state(initial, initial, boxes)
    _expect(box_state.problem_kind == 'word_problem' and box_state.expected_answer == '14', 'Verified schema was not stored in state.', failures)
    _expect(bool(box_state.active_task_id), 'Word problem did not enter the task lifecycle.', failures)
    planned = apply_word_problem_state(initial, update_multi_step_progress(auditorium.expression, initial), auditorium)
    _expect(has_structured_math_problem(planned), 'Multi-step word problem did not use the step planner.', failures)
    _expect(planned.word_problem_schema.get('original_text') == auditorium.original_text, 'Original prose was lost.', failures)
    return failures


def main() -> None:
    failures = asyncio.run(_run())
    if failures:
        print('Tutor word-problem schema check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)
    print('Tutor word-problem schema check passed.')
    print('- Prose becomes a verified schema and deterministic expression.')
    print('- Hallucinated or ambiguous interpretations are rejected safely.')
    print('- One-step and multi-step problems share task and progress state.')


if __name__ == '__main__':
    main()
