from __future__ import annotations

from dataclasses import dataclass

from .models import TutoringState
from .utils.task_lifecycle import transition_to_task


@dataclass(frozen=True)
class TutorMathTopicLesson:
    topic_key: str
    label: str
    explanation: str
    example: str
    starter_question: str
    expected_answer: str
    hint_1: str
    hint_2: str
    worked_explanation: str


MATH_TOPIC_LESSONS: dict[str, TutorMathTopicLesson] = {
    'fraction': TutorMathTopicLesson(
        topic_key='fraction',
        label='fractions',
        explanation='A fraction shows part of a whole.',
        example='If a pizza is cut into 4 equal slices and you eat 1 slice, you ate 1/4 of the pizza.',
        starter_question='What fraction shows 1 part out of 4 equal parts?',
        expected_answer='1/4',
        hint_1='The top number tells how many parts we have.',
        hint_2='The bottom number tells how many equal parts make the whole.',
        worked_explanation='1 part out of 4 equal parts is 1/4.',
    ),
    'lcm': TutorMathTopicLesson(
        topic_key='lcm',
        label='LCM',
        explanation='LCM means Least Common Multiple: the smallest number that two numbers both go into evenly.',
        example='Multiples of 4 are 4, 8, 12. Multiples of 6 are 6, 12. The first match is 12.',
        starter_question='What is the LCM of 3 and 4?',
        expected_answer='12',
        hint_1='List the multiples of 3 and 4.',
        hint_2='3, 6, 9, 12 and 4, 8, 12 both reach 12.',
        worked_explanation='The first shared multiple of 3 and 4 is 12, so the LCM is 12.',
    ),
    'multiplication': TutorMathTopicLesson(
        topic_key='multiplication',
        label='multiplication',
        explanation='Multiplication means equal groups.',
        example='3 x 4 means 3 groups of 4, which makes 12.',
        starter_question='What is 3 x 2?',
        expected_answer='6',
        hint_1='Think of 3 groups of 2.',
        hint_2='2 + 2 + 2 = 6.',
        worked_explanation='3 x 2 = 6.',
    ),
    'division': TutorMathTopicLesson(
        topic_key='division',
        label='division',
        explanation='Division means sharing or splitting into equal groups.',
        example='12 / 3 means sharing 12 into 3 equal groups, so each group gets 4.',
        starter_question='What is 10 / 2?',
        expected_answer='5',
        hint_1='Ask: 2 times what number makes 10?',
        hint_2='2 x 5 = 10.',
        worked_explanation='10 / 2 = 5.',
    ),
    'addition': TutorMathTopicLesson(
        topic_key='addition',
        label='addition',
        explanation='Addition means putting amounts together.',
        example='5 + 3 means 5 things and 3 more things, making 8.',
        starter_question='What is 6 + 4?',
        expected_answer='10',
        hint_1='Start at 6 and count 4 more.',
        hint_2='7, 8, 9, 10.',
        worked_explanation='6 + 4 = 10.',
    ),
    'subtraction': TutorMathTopicLesson(
        topic_key='subtraction',
        label='subtraction',
        explanation='Subtraction means taking away or finding what is left.',
        example='9 - 4 means start with 9 and take away 4, leaving 5.',
        starter_question='What is 8 - 3?',
        expected_answer='5',
        hint_1='Start with 8 and take away 3.',
        hint_2='8, then 7, 6, 5.',
        worked_explanation='8 - 3 = 5.',
    ),
    'decimal': TutorMathTopicLesson(
        topic_key='decimal',
        label='decimals',
        explanation='A decimal shows parts of a whole using place value.',
        example='0.5 means five tenths, which is the same as one half.',
        starter_question='What is 0.3 + 0.2?',
        expected_answer='0.5',
        hint_1='Add the tenths: 3 tenths plus 2 tenths.',
        hint_2='3 + 2 = 5 tenths.',
        worked_explanation='0.3 + 0.2 = 0.5.',
    ),
    'geometry': TutorMathTopicLesson(
        topic_key='geometry',
        label='geometry',
        explanation='Geometry is about shapes and their parts.',
        example='A rectangle has 4 sides and 4 square corners.',
        starter_question='How many sides does a triangle have?',
        expected_answer='3',
        hint_1='Think of the word tri, like tricycle.',
        hint_2='A triangle has three sides.',
        worked_explanation='A triangle has 3 sides.',
    ),
    'area': TutorMathTopicLesson(
        topic_key='area',
        label='area',
        explanation='Area tells how much space is inside a flat shape.',
        example='A rectangle that is 3 units long and 2 units wide has area 3 x 2.',
        starter_question='What is the area of a 3 by 2 rectangle?',
        expected_answer='6',
        hint_1='For a rectangle, multiply length times width.',
        hint_2='3 x 2 = 6.',
        worked_explanation='The area is 3 x 2 = 6 square units.',
    ),
    'perimeter': TutorMathTopicLesson(
        topic_key='perimeter',
        label='perimeter',
        explanation='Perimeter is the distance around the outside of a shape.',
        example='A square with side length 3 has perimeter 3 + 3 + 3 + 3.',
        starter_question='What is the perimeter of a square with side length 4?',
        expected_answer='16',
        hint_1='A square has 4 equal sides.',
        hint_2='4 + 4 + 4 + 4 = 16.',
        worked_explanation='The perimeter is 16 units.',
    ),
    'word_problem': TutorMathTopicLesson(
        topic_key='word_problem',
        label='word problems',
        explanation='A word problem tells a math situation using a short story.',
        example='If 3 bags have 2 apples each, we use 3 x 2 to find the total apples.',
        starter_question='There are 3 boxes with 2 balls in each box. How many balls are there?',
        expected_answer='6',
        hint_1='Each box has the same number of balls.',
        hint_2='Use 3 x 2.',
        worked_explanation='3 x 2 = 6, so there are 6 balls.',
    ),
    'ratio': TutorMathTopicLesson(
        topic_key='ratio',
        label='ratios',
        explanation='A ratio compares two amounts.',
        example='If there are 2 red blocks and 3 blue blocks, the ratio of red to blue is 2:3.',
        starter_question='What is the ratio of 2 red blocks to 5 blue blocks?',
        expected_answer='2:5',
        hint_1='Put red first because the question asks red to blue.',
        hint_2='There are 2 red and 5 blue.',
        worked_explanation='The ratio of red to blue is 2:5.',
    ),
    'percent': TutorMathTopicLesson(
        topic_key='percent',
        label='percent',
        explanation='Percent means out of 100.',
        example='50% means 50 out of 100, which is one half.',
        starter_question='What percent means 25 out of 100?',
        expected_answer='25%',
        hint_1='Percent means out of 100.',
        hint_2='25 out of 100 is 25%.',
        worked_explanation='25 out of 100 is 25%.',
    ),
    'measurement': TutorMathTopicLesson(
        topic_key='measurement',
        label='measurement',
        explanation='Measurement tells the size, length, weight, or amount of something.',
        example='If one pencil is 6 inches long, two pencils end to end are 12 inches.',
        starter_question='If one ribbon is 5 inches long, how long are 2 ribbons?',
        expected_answer='10',
        hint_1='Two ribbons means 2 groups of 5 inches.',
        hint_2='5 + 5 = 10.',
        worked_explanation='2 x 5 = 10, so the ribbons are 10 inches long.',
    ),
    'time': TutorMathTopicLesson(
        topic_key='time',
        label='elapsed time',
        explanation='Elapsed time means how much time passes.',
        example='From 2:00 to 2:30, 30 minutes pass.',
        starter_question='How many minutes pass from 1:00 to 1:20?',
        expected_answer='20',
        hint_1='Count from 1:00 to 1:20.',
        hint_2='That is 20 minutes.',
        worked_explanation='20 minutes pass from 1:00 to 1:20.',
    ),
    'money': TutorMathTopicLesson(
        topic_key='money',
        label='money',
        explanation='Money math helps us count, add, or subtract amounts of money.',
        example='Two quarters make 50 cents.',
        starter_question='How many cents are 3 dimes?',
        expected_answer='30',
        hint_1='One dime is 10 cents.',
        hint_2='10 + 10 + 10 = 30.',
        worked_explanation='3 dimes are 30 cents.',
    ),
    'factor': TutorMathTopicLesson(
        topic_key='factor',
        label='factors and multiples',
        explanation='Factors multiply together to make a number. Multiples are skip-counting results.',
        example='3 and 4 are factors of 12 because 3 x 4 = 12.',
        starter_question='Is 3 a factor of 12?',
        expected_answer='yes',
        hint_1='Ask if 12 can be divided evenly by 3.',
        hint_2='3 x 4 = 12.',
        worked_explanation='Yes. 3 is a factor of 12 because 3 x 4 = 12.',
    ),
    'place_value': TutorMathTopicLesson(
        topic_key='place_value',
        label='place value',
        explanation='Place value tells what a digit is worth based on where it is.',
        example='In 347, the 4 is in the tens place, so it means 40.',
        starter_question='In 582, what is the value of the 8?',
        expected_answer='80',
        hint_1='The 8 is in the tens place.',
        hint_2='8 tens is 80.',
        worked_explanation='The value of the 8 is 80.',
    ),
    'negative_number': TutorMathTopicLesson(
        topic_key='negative_number',
        label='negative numbers',
        explanation='Negative numbers are less than zero.',
        example='On a number line, -2 is two steps left of 0.',
        starter_question='Which is greater: -1 or -3?',
        expected_answer='-1',
        hint_1='Numbers farther right on the number line are greater.',
        hint_2='-1 is closer to zero than -3.',
        worked_explanation='-1 is greater than -3.',
    ),
    'expression': TutorMathTopicLesson(
        topic_key='expression',
        label='expressions and equations',
        explanation='An expression is a math phrase. An equation says two expressions are equal.',
        example='3 + 4 is an expression. 3 + 4 = 7 is an equation.',
        starter_question='What is the value of 5 + 2?',
        expected_answer='7',
        hint_1='Add 5 and 2.',
        hint_2='5 + 2 = 7.',
        worked_explanation='The value of 5 + 2 is 7.',
    ),
    'data': TutorMathTopicLesson(
        topic_key='data',
        label='data and graphs',
        explanation='Data is information we collect. Graphs help us see and compare data.',
        example='If a bar graph shows 4 apples and 6 oranges, oranges have the taller bar.',
        starter_question='A graph shows 4 apples and 6 oranges. Which has more?',
        expected_answer='oranges',
        hint_1='Compare 4 and 6.',
        hint_2='6 is more than 4.',
        worked_explanation='Oranges have more because 6 is greater than 4.',
    ),
}


def topic_lesson(topic_key: str) -> TutorMathTopicLesson | None:
    return MATH_TOPIC_LESSONS.get(str(topic_key or '').strip())


def all_topic_lessons() -> tuple[TutorMathTopicLesson, ...]:
    return tuple(MATH_TOPIC_LESSONS.values())


def build_topic_lesson_intro(lesson: TutorMathTopicLesson) -> str:
    return (
        f"Great - let's learn {lesson.label}.\n\n"
        f"{lesson.explanation}\n\n"
        f"Example: {lesson.example}\n\n"
        "Now try one:\n\n"
        f"{lesson.starter_question}"
    )


def apply_topic_lesson_state(
    state: TutoringState,
    student_message: str,
    lesson: TutorMathTopicLesson,
) -> TutoringState:
    question_id = f'topic-lesson-{lesson.topic_key}'
    recent_ids = _next_recent_topic_lesson_ids(state.recent_tutor_practice_question_ids, question_id)
    next_state = state.model_copy(update={
        'current_subject': 'Math',
        'active_problem': lesson.starter_question,
        'current_step': lesson.starter_question,
        'current_question': lesson.starter_question,
        'expected_answer': lesson.expected_answer,
        'student_answer': student_message,
        'correctness_status': '',
        'skill': lesson.topic_key,
        'step_number': 1,
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
        'next_similar_question': '',
        'tutor_practice_question_id': question_id,
        'tutor_practice_grade': 0,
        'tutor_practice_topic': lesson.label,
        'tutor_practice_hint_1': lesson.hint_1,
        'tutor_practice_hint_2': lesson.hint_2,
        'tutor_practice_explanation': lesson.worked_explanation,
        'recent_tutor_practice_question_ids': recent_ids,
        'final_answer': '',
        'problem_status': 'tutor_practice',
        'mode': 'tutor_practice_question',
        'status': 'waiting_for_student',
        'memory_note': f'Student started Math topic lesson: {lesson.label}.',
    })
    return transition_to_task(
        state,
        next_state,
        lesson.starter_question,
        subject='Math',
        topic=lesson.label,
        source='topic_lesson',
        previous='abandon',
    )


def _next_recent_topic_lesson_ids(previous_ids: list[str] | tuple[str, ...] | None, question_id: str) -> list[str]:
    ids = [str(item) for item in (previous_ids or []) if str(item).strip()]
    ids = [item for item in ids if item != question_id]
    ids.append(question_id)
    return ids[-12:]
