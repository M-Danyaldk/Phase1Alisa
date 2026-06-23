from pydantic import ValidationError

from backend.app.schemas.tutor_interpretation import (
    StructuredMathProblem,
    TutorInputInterpretation,
    TutorQuantity,
)


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _expect_rejected(payload: dict, message: str, failures: list[str]) -> None:
    try:
        TutorInputInterpretation.model_validate(payload)
    except ValidationError:
        return
    failures.append(message)


def main() -> None:
    failures: list[str] = []

    answer = TutorInputInterpretation.model_validate({
        'schema_version': '1.0',
        'intent': 'answer_current_step',
        'confidence': 'high',
        'answer': 'seventy-eight',
        'normalized_expression': None,
        'problem': None,
        'question_type': 'arithmetic_single_step',
        'refers_to_task': 'active_task',
        'requested_action': 'check_answer',
        'emotion': None,
        'needs_clarification': False,
        'clarification_question': None,
        'interpretation_note': 'Student supplied a likely answer to the active step.',
    })
    _expect(answer.answer == 'seventy-eight', 'Flexible student answer text was not preserved.', failures)

    word_problem = StructuredMathProblem.model_validate({
        'original_text': 'There are 7 boxes and each box holds 2 balls. How many balls are needed?',
        'problem_kind': 'word_problem',
        'quantities': [
            {'value': '7', 'unit': 'boxes', 'label': 'number of boxes', 'role': 'group_count'},
            {'value': '2', 'unit': 'balls', 'label': 'balls per box', 'role': 'group_size'},
        ],
        'operation': 'multiplication',
        'confidence': 'high',
        'expression': '7 * 2',
        'requested_value': 'total balls',
        'unit': 'balls',
        'sufficient_information': True,
        'assumptions': [],
    })
    new_problem = TutorInputInterpretation.model_validate({
        'schema_version': '1.0',
        'intent': 'new_problem',
        'confidence': 'high',
        'answer': None,
        'normalized_expression': '7 * 2',
        'problem': word_problem.model_dump(),
        'question_type': 'word_problem',
        'refers_to_task': 'new_task',
        'requested_action': 'solve',
        'emotion': None,
        'needs_clarification': False,
        'clarification_question': None,
        'interpretation_note': 'Student supplied a complete multiplication word problem.',
    })
    _expect(new_problem.problem is not None and new_problem.problem.expression == '7 * 2', 'Structured word problem did not survive strict validation.', failures)

    fraction_problem = StructuredMathProblem.model_validate({
        'original_text': 'Write a fraction equivalent to 3/8 with denominator 16.',
        'problem_kind': 'conceptual',
        'quantities': [
            {'value': '3/8', 'unit': '', 'label': 'starting fraction', 'role': 'given'},
            {'value': '16', 'unit': '', 'label': 'target denominator', 'role': 'denominator'},
        ],
        'operation': 'equivalent_fraction',
        'confidence': 'high',
        'expression': '3 / 8 * 16',
        'requested_value': 'equivalent numerator',
        'unit': None,
        'sufficient_information': True,
        'assumptions': [],
    })
    _expect(fraction_problem.operation == 'equivalent_fraction', 'Equivalent-fraction operation was not supported.', failures)

    continuation = TutorInputInterpretation.model_validate({
        'schema_version': '1.0',
        'intent': 'continuation_yes',
        'confidence': 'high',
        'message_kind': 'continuation_choice',
        'answer': None,
        'normalized_expression': None,
        'problem': None,
        'question_type': 'continuation_choice',
        'refers_to_task': 'active_task',
        'requested_action': 'continue',
        'emotion': None,
        'contains_math_problem': False,
        'contains_answer_attempt': False,
        'contains_help_request': False,
        'contains_emotion_signal': False,
        'opening_acknowledgement': None,
        'continuation_choice': 'yes',
        'answer_format': None,
        'support_type': None,
        'switch_target_kind': None,
        'switch_target_value': None,
        'needs_clarification': False,
        'clarification_question': None,
        'interpretation_note': 'Student wants another practice question.',
    })
    _expect(continuation.question_type == 'continuation_choice', 'Continuation choice question type was not preserved.', failures)

    opening_reply = TutorInputInterpretation.model_validate({
        'schema_version': '1.0',
        'intent': 'new_problem',
        'confidence': 'high',
        'message_kind': 'opening_reply',
        'answer': None,
        'normalized_expression': '8 + 9',
        'problem': None,
        'question_type': None,
        'refers_to_task': 'new_task',
        'requested_action': 'solve',
        'emotion': 'happy',
        'contains_math_problem': True,
        'contains_answer_attempt': False,
        'contains_help_request': False,
        'contains_emotion_signal': True,
        'opening_acknowledgement': 'I am happy',
        'continuation_choice': None,
        'answer_format': None,
        'support_type': None,
        'switch_target_kind': None,
        'switch_target_value': None,
        'needs_clarification': False,
        'clarification_question': None,
        'interpretation_note': 'Student replied to the opening check-in and also supplied a new Math problem.',
    })
    _expect(opening_reply.message_kind == 'opening_reply', 'Opening reply message kind was not preserved.', failures)
    _expect(opening_reply.contains_math_problem, 'Opening reply did not preserve embedded Math-problem detection.', failures)
    _expect(opening_reply.opening_acknowledgement == 'I am happy', 'Opening reply acknowledgement text was not preserved.', failures)

    unclear = TutorInputInterpretation.model_validate({
        'schema_version': '1.0',
        'intent': 'unclear',
        'confidence': 'low',
        'answer': None,
        'normalized_expression': None,
        'problem': None,
        'question_type': None,
        'refers_to_task': 'unknown',
        'requested_action': 'none',
        'emotion': None,
        'needs_clarification': True,
        'clarification_question': 'Do you want to answer the current step or start a new problem?',
        'interpretation_note': 'The message could refer to either task.',
    })
    _expect(unclear.needs_clarification, 'Low-confidence interpretation did not preserve clarification.', failures)

    base = answer.model_dump()
    _expect_rejected({**base, 'invented_state': 'finished'}, 'Unknown top-level fields were accepted.', failures)
    _expect_rejected({**base, 'active_problem': '64 + 55'}, 'LLM schema was allowed to write deterministic tutor state.', failures)
    _expect_rejected({**base, 'intent': 'make_up_a_task'}, 'Unknown intent value was accepted.', failures)
    _expect_rejected({**base, 'answer': 78}, 'Strict schema coerced a numeric answer into text.', failures)
    _expect_rejected({**base, 'intent': 'answer_current_step', 'answer': None}, 'Answer intent without an answer was accepted.', failures)
    _expect_rejected({**base, 'confidence': 'low'}, 'Low confidence without clarification was accepted.', failures)
    _expect_rejected({**base, 'intent': 'greeting', 'answer': '78'}, 'Greeting was allowed to carry an answer payload.', failures)
    _expect_rejected({
        **continuation.model_dump(),
        'answer': 'yes',
    }, 'Continuation choice was allowed to carry an answer payload.', failures)
    _expect_rejected({
        **continuation.model_dump(),
        'intent': 'related_question',
    }, 'Continuation question type was allowed to use the wrong intent label.', failures)
    _expect_rejected({
        **continuation.model_dump(),
        'continuation_choice': None,
    }, 'Continuation-choice messages were allowed to omit the interpreted choice.', failures)
    _expect_rejected({
        **opening_reply.model_dump(),
        'message_kind': 'opening_reply',
        'opening_acknowledgement': None,
        'contains_math_problem': False,
        'contains_answer_attempt': False,
        'contains_help_request': False,
        'contains_emotion_signal': False,
        'intent': 'acknowledge',
    }, 'Opening reply without any structured opening details was accepted.', failures)
    _expect_rejected({
        **base,
        'intent': 'switch_problem',
        'answer': None,
        'normalized_expression': None,
        'problem': None,
        'requested_action': 'switch',
    }, 'Problem switch without a problem payload was accepted.', failures)
    _expect_rejected({
        **new_problem.model_dump(),
        'problem': {**word_problem.model_dump(), 'surprise': True},
    }, 'Unknown nested problem fields were accepted.', failures)
    _expect_rejected({
        **new_problem.model_dump(),
        'normalized_expression': '7 * unknown',
    }, 'Non-evaluable expression was accepted.', failures)

    try:
        TutorQuantity.model_validate({'value': 'two', 'unit': 'balls', 'label': '', 'role': 'given'})
    except ValidationError:
        pass
    else:
        failures.append('Non-normalized quantity text was accepted as a numeric quantity.')

    try:
        StructuredMathProblem.model_validate({
            **word_problem.model_dump(),
            'sufficient_information': False,
        })
    except ValidationError:
        pass
    else:
        failures.append('Insufficient problem was allowed to claim a complete expression.')

    schema = TutorInputInterpretation.model_json_schema()
    _expect(schema.get('additionalProperties') is False, 'Generated JSON schema does not forbid unknown top-level properties.', failures)
    _expect('intent' in (schema.get('required') or []), 'Generated JSON schema does not require intent.', failures)

    if failures:
        print('Tutor interpretation schema check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor interpretation schema check passed.')
    print('- Intent, task reference, requested action, answer, emotion, and confidence use strict contracts.')
    print('- Structured Math problems require typed quantities and deterministically evaluable expressions.')
    print('- Contradictory, low-confidence, invented-field, and malformed-expression payloads are rejected.')


if __name__ == '__main__':
    main()
