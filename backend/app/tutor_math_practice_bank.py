from dataclasses import dataclass
from functools import lru_cache
import random
import re

from .curriculum import LAUNCH_GRADES


@dataclass(frozen=True)
class TutorMathPracticeQuestion:
    id: str
    grade: int
    topic: str
    skill: str
    question: str
    expected_answer: str
    accepted_answers: tuple[str, ...]
    hint_1: str
    hint_2: str
    worked_explanation: str
    difficulty: str = 'quick'


GRADE_3_TUTOR_MATH: tuple[dict, ...] = (
    {
        'topic': 'multiplication facts',
        'skill': 'multiplication facts',
        'question': 'What is 2 x 7?',
        'expected_answer': '14',
        'hint_1': 'Think of 2 groups of 7.',
        'hint_2': '7 + 7 = 14.',
        'worked_explanation': '2 x 7 = 14.',
    },
    {
        'topic': 'multiplication facts',
        'skill': 'multiplication facts',
        'question': 'What is 10 x 3?',
        'expected_answer': '30',
        'hint_1': 'Think of 10 groups of 3.',
        'hint_2': '10 x 3 is the same as 3 tens.',
        'worked_explanation': '10 x 3 = 30.',
    },
    {
        'topic': 'division facts',
        'skill': 'division facts',
        'question': 'What is 36 / 6?',
        'expected_answer': '6',
        'hint_1': 'Ask yourself: 6 times what number makes 36?',
        'hint_2': '6 x 6 = 36.',
        'worked_explanation': '36 / 6 = 6 because 6 x 6 = 36.',
    },
    {
        'topic': 'division facts',
        'skill': 'division facts',
        'question': 'What is 45 / 9?',
        'expected_answer': '5',
        'hint_1': 'Ask yourself: 9 times what number makes 45?',
        'hint_2': '9 x 5 = 45.',
        'worked_explanation': '45 / 9 = 5 because 9 x 5 = 45.',
    },
    {
        'topic': 'fractions as parts of a whole',
        'skill': 'fraction comparison',
        'question': 'Which is larger: 3/4 or 1/4?',
        'expected_answer': '3/4',
        'hint_1': 'The denominators are the same, so compare the top numbers.',
        'hint_2': '3 parts is more than 1 part.',
        'worked_explanation': '3/4 is larger than 1/4 because 3 fourths is more than 1 fourth.',
    },
    {
        'topic': 'fractions as parts of a whole',
        'skill': 'fraction comparison',
        'question': 'Which is larger: 2/3 or 1/3?',
        'expected_answer': '2/3',
        'hint_1': 'Both fractions have thirds, so compare the numerators.',
        'hint_2': '2 thirds is more than 1 third.',
        'worked_explanation': '2/3 is larger than 1/3 because 2 parts is more than 1 part.',
    },
    {
        'topic': 'measurement word problems',
        'skill': 'division word problems',
        'question': 'There are 28 pencils. If 4 pencils go in each cup, how many cups are needed?',
        'expected_answer': '7',
        'hint_1': 'This is asking how many groups of 4 are in 28.',
        'hint_2': '4 x 7 = 28.',
        'worked_explanation': '28 / 4 = 7, so 7 cups are needed.',
    },
    {
        'topic': 'measurement word problems',
        'skill': 'division word problems',
        'question': 'There are 30 stickers. If 5 stickers go on each page, how many pages are needed?',
        'expected_answer': '6',
        'hint_1': 'This is asking how many groups of 5 are in 30.',
        'hint_2': '5 x 6 = 30.',
        'worked_explanation': '30 / 5 = 6, so 6 pages are needed.',
    },
    {
        'topic': 'multiplication facts',
        'skill': 'multiplication facts',
        'question': 'What is 11 x 2?',
        'expected_answer': '22',
        'hint_1': 'Think of 2 groups of 11.',
        'hint_2': '11 + 11 = 22.',
        'worked_explanation': '11 x 2 = 22.',
    },
    {
        'topic': 'multiplication facts',
        'skill': 'multiplication facts',
        'question': 'What is 2 x 9?',
        'expected_answer': '18',
        'hint_1': 'Think of 2 groups of 9.',
        'hint_2': '9 + 9 = 18.',
        'worked_explanation': '2 x 9 = 18.',
    },
    {
        'topic': 'multiplication facts',
        'skill': 'multiplication facts',
        'question': 'What is 10 x 8?',
        'expected_answer': '80',
        'hint_1': 'Multiplying by 10 adds a zero to 8.',
        'hint_2': '8 tens is 80.',
        'worked_explanation': '10 x 8 = 80.',
    },
    {
        'topic': 'division facts',
        'skill': 'division facts',
        'question': 'What is 18 / 2?',
        'expected_answer': '9',
        'hint_1': 'Ask yourself: 2 times what number makes 18?',
        'hint_2': '2 x 9 = 18.',
        'worked_explanation': '18 / 2 = 9 because 2 x 9 = 18.',
    },
    {
        'topic': 'division facts',
        'skill': 'division facts',
        'question': 'What is 80 / 10?',
        'expected_answer': '8',
        'hint_1': 'Ask yourself: 10 times what number makes 80?',
        'hint_2': '10 x 8 = 80.',
        'worked_explanation': '80 / 10 = 8 because 10 x 8 = 80.',
    },
    {
        'topic': 'fractions as parts of a whole',
        'skill': 'fraction comparison',
        'question': 'Which is larger: 4/5 or 2/5?',
        'expected_answer': '4/5',
        'hint_1': 'The denominators are the same, so compare the top numbers.',
        'hint_2': '4 fifths is more than 2 fifths.',
        'worked_explanation': '4/5 is larger than 2/5 because 4 is greater than 2.',
    },
    {
        'topic': 'fractions as parts of a whole',
        'skill': 'fraction comparison',
        'question': 'Which is larger: 1/6 or 5/6?',
        'expected_answer': '5/6',
        'hint_1': 'The denominators are the same, so compare the numerators.',
        'hint_2': '5 sixths is more than 1 sixth.',
        'worked_explanation': '5/6 is larger than 1/6 because 5 is greater than 1.',
    },
    {
        'topic': 'fractions as parts of a whole',
        'skill': 'unit fractions',
        'question': 'How many fourths make one whole?',
        'expected_answer': '4',
        'hint_1': 'A whole split into fourths has 4 equal pieces.',
        'hint_2': '4/4 is one whole.',
        'worked_explanation': 'Four fourths make one whole.',
    },
    {
        'topic': 'measurement word problems',
        'skill': 'division word problems',
        'question': 'There are 16 markers. If 2 markers go in each box, how many boxes are needed?',
        'expected_answer': '8',
        'hint_1': 'This asks how many groups of 2 are in 16.',
        'hint_2': '2 x 8 = 16.',
        'worked_explanation': '16 / 2 = 8, so 8 boxes are needed.',
    },
    {
        'topic': 'measurement word problems',
        'skill': 'division word problems',
        'question': 'There are 22 crayons. If 2 crayons go in each pack, how many packs are needed?',
        'expected_answer': '11',
        'hint_1': 'This asks how many groups of 2 are in 22.',
        'hint_2': '2 x 11 = 22.',
        'worked_explanation': '22 / 2 = 11, so 11 packs are needed.',
    },
    {
        'topic': 'multi-step addition and subtraction',
        'skill': 'addition and subtraction',
        'question': 'What is 35 + 10 - 5?',
        'expected_answer': '40',
        'hint_1': 'Do the addition first.',
        'hint_2': '35 + 10 = 45, then subtract 5.',
        'worked_explanation': '35 + 10 = 45, and 45 - 5 = 40.',
    },
    {
        'topic': 'multi-step addition and subtraction',
        'skill': 'addition and subtraction',
        'question': 'What is 48 - 8 + 6?',
        'expected_answer': '46',
        'hint_1': 'Work from left to right.',
        'hint_2': '48 - 8 = 40, then add 6.',
        'worked_explanation': '48 - 8 = 40, and 40 + 6 = 46.',
    },
)


GRADE_4_TUTOR_MATH: tuple[dict, ...] = (
    {
        'topic': 'multi-digit multiplication',
        'skill': 'multi-digit multiplication',
        'question': 'What is 14 x 5?',
        'expected_answer': '70',
        'hint_1': 'Break 14 into 10 and 4.',
        'hint_2': '10 x 5 = 50 and 4 x 5 = 20.',
        'worked_explanation': '14 x 5 = 50 + 20 = 70.',
    },
    {
        'topic': 'multi-digit multiplication',
        'skill': 'multi-digit multiplication',
        'question': 'What is 23 x 3?',
        'expected_answer': '69',
        'hint_1': 'Break 23 into 20 and 3.',
        'hint_2': '20 x 3 = 60 and 3 x 3 = 9.',
        'worked_explanation': '23 x 3 = 60 + 9 = 69.',
    },
    {
        'topic': 'long division foundations',
        'skill': 'division facts',
        'question': 'What is 84 / 7?',
        'expected_answer': '12',
        'hint_1': 'Ask: 7 times what number makes 84?',
        'hint_2': '7 x 12 = 84.',
        'worked_explanation': '84 / 7 = 12 because 7 x 12 = 84.',
    },
    {
        'topic': 'long division foundations',
        'skill': 'division facts',
        'question': 'What is 96 / 8?',
        'expected_answer': '12',
        'hint_1': 'Ask: 8 times what number makes 96?',
        'hint_2': '8 x 12 = 96.',
        'worked_explanation': '96 / 8 = 12 because 8 x 12 = 96.',
    },
    {
        'topic': 'equivalent fractions and decimals',
        'skill': 'fraction comparison',
        'question': 'Which is larger: 5/6 or 4/6?',
        'expected_answer': '5/6',
        'hint_1': 'The denominators are the same, so compare the top numbers.',
        'hint_2': '5 sixths is more than 4 sixths.',
        'worked_explanation': '5/6 is larger than 4/6 because 5 is greater than 4.',
    },
    {
        'topic': 'equivalent fractions and decimals',
        'skill': 'equivalent fractions',
        'question': 'What fraction is equivalent to 1/2: 2/4 or 1/4?',
        'expected_answer': '2/4',
        'hint_1': 'Equivalent fractions name the same amount.',
        'hint_2': 'If you split each half into 2 equal parts, 1/2 becomes 2/4.',
        'worked_explanation': '2/4 is equivalent to 1/2.',
    },
    {
        'topic': 'measurement and geometry',
        'skill': 'perimeter',
        'question': 'A rectangle is 8 units long and 3 units wide. What is its perimeter?',
        'expected_answer': '22',
        'hint_1': 'Perimeter means add all the side lengths.',
        'hint_2': 'Use 8 + 3 + 8 + 3.',
        'worked_explanation': '8 + 3 + 8 + 3 = 22, so the perimeter is 22 units.',
    },
    {
        'topic': 'measurement and geometry',
        'skill': 'area',
        'question': 'A rectangle is 9 units long and 4 units wide. What is its area?',
        'expected_answer': '36',
        'hint_1': 'Area of a rectangle is length times width.',
        'hint_2': 'Use 9 x 4.',
        'worked_explanation': '9 x 4 = 36, so the area is 36 square units.',
    },
    {
        'topic': 'multi-digit multiplication',
        'skill': 'multi-digit multiplication',
        'question': 'What is 11 x 6?',
        'expected_answer': '66',
        'hint_1': 'Break 11 into 10 and 1.',
        'hint_2': '10 x 6 = 60 and 1 x 6 = 6.',
        'worked_explanation': '11 x 6 = 60 + 6 = 66.',
    },
    {
        'topic': 'multi-digit multiplication',
        'skill': 'multi-digit multiplication',
        'question': 'What is 13 x 5?',
        'expected_answer': '65',
        'hint_1': 'Break 13 into 10 and 3.',
        'hint_2': '10 x 5 = 50 and 3 x 5 = 15.',
        'worked_explanation': '13 x 5 = 50 + 15 = 65.',
    },
    {
        'topic': 'multi-digit multiplication',
        'skill': 'multi-digit multiplication',
        'question': 'What is 20 x 4?',
        'expected_answer': '80',
        'hint_1': 'Think of 2 tens times 4.',
        'hint_2': '2 x 4 = 8, then use tens.',
        'worked_explanation': '20 x 4 = 80.',
    },
    {
        'topic': 'long division foundations',
        'skill': 'division facts',
        'question': 'What is 66 / 6?',
        'expected_answer': '11',
        'hint_1': 'Ask: 6 times what number makes 66?',
        'hint_2': '6 x 11 = 66.',
        'worked_explanation': '66 / 6 = 11 because 6 x 11 = 66.',
    },
    {
        'topic': 'long division foundations',
        'skill': 'division facts',
        'question': 'What is 65 / 5?',
        'expected_answer': '13',
        'hint_1': 'Ask: 5 times what number makes 65?',
        'hint_2': '5 x 13 = 65.',
        'worked_explanation': '65 / 5 = 13 because 5 x 13 = 65.',
    },
    {
        'topic': 'equivalent fractions and decimals',
        'skill': 'equivalent fractions',
        'question': 'What fraction is equivalent to 2/3: 4/6 or 3/6?',
        'expected_answer': '4/6',
        'hint_1': 'Equivalent fractions name the same amount.',
        'hint_2': 'Multiply the top and bottom of 2/3 by 2.',
        'worked_explanation': '2/3 = 4/6.',
    },
    {
        'topic': 'equivalent fractions and decimals',
        'skill': 'fraction comparison',
        'question': 'Which is larger: 7/8 or 5/8?',
        'expected_answer': '7/8',
        'hint_1': 'The denominators are the same, so compare the numerators.',
        'hint_2': '7 eighths is more than 5 eighths.',
        'worked_explanation': '7/8 is larger than 5/8 because 7 is greater than 5.',
    },
    {
        'topic': 'factors and multiples',
        'skill': 'factors',
        'question': 'How many groups of 6 are in 54?',
        'expected_answer': '9',
        'hint_1': 'This asks for 54 divided by 6.',
        'hint_2': '6 x 9 = 54.',
        'worked_explanation': '54 / 6 = 9, so there are 9 groups of 6.',
    },
    {
        'topic': 'factors and multiples',
        'skill': 'multiples',
        'question': 'What is the next multiple of 7 after 28?',
        'expected_answer': '35',
        'hint_1': 'Multiples of 7 go up by 7.',
        'hint_2': '28 + 7 = 35.',
        'worked_explanation': 'The next multiple of 7 after 28 is 35.',
    },
    {
        'topic': 'measurement and geometry',
        'skill': 'perimeter',
        'question': 'A square has side length 6 units. What is its perimeter?',
        'expected_answer': '24',
        'hint_1': 'A square has 4 equal sides.',
        'hint_2': 'Use 6 + 6 + 6 + 6.',
        'worked_explanation': '6 x 4 = 24, so the perimeter is 24 units.',
    },
    {
        'topic': 'measurement and geometry',
        'skill': 'area',
        'question': 'A rectangle is 7 units long and 5 units wide. What is its area?',
        'expected_answer': '35',
        'hint_1': 'Area of a rectangle is length times width.',
        'hint_2': 'Use 7 x 5.',
        'worked_explanation': '7 x 5 = 35, so the area is 35 square units.',
    },
    {
        'topic': 'measurement and geometry',
        'skill': 'elapsed time',
        'question': 'A game starts at 2:00 and ends at 2:45. How many minutes long is it?',
        'expected_answer': '45',
        'hint_1': 'Count the minutes from 2:00 to 2:45.',
        'hint_2': 'From :00 to :45 is 45 minutes.',
        'worked_explanation': 'The game is 45 minutes long.',
    },
)


GRADE_5_TUTOR_MATH: tuple[dict, ...] = (
    {
        'topic': 'fraction and decimal operations',
        'skill': 'fraction addition',
        'question': 'What is 1/3 + 1/3?',
        'expected_answer': '2/3',
        'hint_1': 'The denominators are the same, so add the numerators.',
        'hint_2': '1 third plus 1 third is 2 thirds.',
        'worked_explanation': '1/3 + 1/3 = 2/3.',
    },
    {
        'topic': 'fraction and decimal operations',
        'skill': 'fraction subtraction',
        'question': 'What is 5/8 - 2/8?',
        'expected_answer': '3/8',
        'hint_1': 'The denominators are the same, so subtract the numerators.',
        'hint_2': '5 - 2 = 3, and the denominator stays 8.',
        'worked_explanation': '5/8 - 2/8 = 3/8.',
    },
    {
        'topic': 'fraction and decimal operations',
        'skill': 'decimal multiplication',
        'question': 'What is 6 x 1.5?',
        'expected_answer': '9',
        'hint_1': 'Think of 1.5 as 1 and 1/2.',
        'hint_2': '6 x 1 = 6 and 6 x 0.5 = 3.',
        'worked_explanation': '6 x 1.5 = 9.',
    },
    {
        'topic': 'fraction and decimal operations',
        'skill': 'decimal multiplication',
        'question': 'What is 4 x 2.5?',
        'expected_answer': '10',
        'hint_1': 'Think of 2.5 as 2 and 1/2.',
        'hint_2': '4 x 2 = 8 and 4 x 0.5 = 2.',
        'worked_explanation': '4 x 2.5 = 10.',
    },
    {
        'topic': 'volume',
        'skill': 'volume',
        'question': 'A box is 4 units long, 3 units wide, and 5 units tall. What is its volume?',
        'expected_answer': '60',
        'hint_1': 'Volume of a rectangular box is length x width x height.',
        'hint_2': 'Use 4 x 3 x 5.',
        'worked_explanation': '4 x 3 x 5 = 60, so the volume is 60 cubic units.',
    },
    {
        'topic': 'volume',
        'skill': 'volume',
        'question': 'A box is 6 units long, 2 units wide, and 4 units tall. What is its volume?',
        'expected_answer': '48',
        'hint_1': 'Volume is length x width x height.',
        'hint_2': 'Use 6 x 2 x 4.',
        'worked_explanation': '6 x 2 x 4 = 48, so the volume is 48 cubic units.',
    },
    {
        'topic': 'multi-step word problems',
        'skill': 'multi-step arithmetic',
        'question': 'Mia has 18 cards. She gets 7 more, then gives away 5. How many cards does she have now?',
        'expected_answer': '20',
        'hint_1': 'First add the cards she gets.',
        'hint_2': '18 + 7 = 25, then 25 - 5.',
        'worked_explanation': '18 + 7 = 25, and 25 - 5 = 20.',
    },
    {
        'topic': 'place value with decimals',
        'skill': 'decimal comparison',
        'question': 'Which is larger: 0.7 or 0.65?',
        'expected_answer': '0.7',
        'hint_1': 'Write 0.7 as 0.70 to compare hundredths.',
        'hint_2': '70 hundredths is more than 65 hundredths.',
        'worked_explanation': '0.7 is larger because 0.70 > 0.65.',
    },
    {
        'topic': 'fraction and decimal operations',
        'skill': 'fraction addition',
        'question': 'What is 2/7 + 3/7?',
        'expected_answer': '5/7',
        'hint_1': 'The denominators are the same, so add the numerators.',
        'hint_2': '2 + 3 = 5, and the denominator stays 7.',
        'worked_explanation': '2/7 + 3/7 = 5/7.',
    },
    {
        'topic': 'fraction and decimal operations',
        'skill': 'fraction subtraction',
        'question': 'What is 7/9 - 4/9?',
        'expected_answer': '3/9',
        'accepted_answers': ('3/9', '1/3'),
        'hint_1': 'The denominators are the same, so subtract the numerators.',
        'hint_2': '7 - 4 = 3, and the denominator stays 9.',
        'worked_explanation': '7/9 - 4/9 = 3/9, which simplifies to 1/3.',
    },
    {
        'topic': 'fraction and decimal operations',
        'skill': 'fraction addition',
        'question': 'What is 1/4 + 1/2?',
        'expected_answer': '3/4',
        'hint_1': 'Rename 1/2 as 2/4.',
        'hint_2': '1/4 + 2/4 = 3/4.',
        'worked_explanation': '1/4 + 1/2 = 1/4 + 2/4 = 3/4.',
    },
    {
        'topic': 'fraction and decimal operations',
        'skill': 'decimal multiplication',
        'question': 'What is 8 x 0.5?',
        'expected_answer': '4',
        'hint_1': 'Multiplying by 0.5 means finding half.',
        'hint_2': 'Half of 8 is 4.',
        'worked_explanation': '8 x 0.5 = 4.',
    },
    {
        'topic': 'fraction and decimal operations',
        'skill': 'decimal multiplication',
        'question': 'What is 3 x 1.2?',
        'expected_answer': '3.6',
        'hint_1': 'Think of 1.2 as 12 tenths.',
        'hint_2': '3 x 12 tenths = 36 tenths.',
        'worked_explanation': '3 x 1.2 = 3.6.',
    },
    {
        'topic': 'volume',
        'skill': 'volume',
        'question': 'A box is 5 units long, 2 units wide, and 3 units tall. What is its volume?',
        'expected_answer': '30',
        'hint_1': 'Volume is length x width x height.',
        'hint_2': 'Use 5 x 2 x 3.',
        'worked_explanation': '5 x 2 x 3 = 30, so the volume is 30 cubic units.',
    },
    {
        'topic': 'volume',
        'skill': 'volume',
        'question': 'A box is 7 units long, 2 units wide, and 5 units tall. What is its volume?',
        'expected_answer': '70',
        'hint_1': 'Volume is length x width x height.',
        'hint_2': 'Use 7 x 2 x 5.',
        'worked_explanation': '7 x 2 x 5 = 70, so the volume is 70 cubic units.',
    },
    {
        'topic': 'multi-step word problems',
        'skill': 'multi-step arithmetic',
        'question': 'Leo has 24 marbles. He buys 6 more, then shares 10 with a friend. How many marbles does he have left?',
        'expected_answer': '20',
        'hint_1': 'First add the marbles he buys.',
        'hint_2': '24 + 6 = 30, then 30 - 10.',
        'worked_explanation': '24 + 6 = 30, and 30 - 10 = 20.',
    },
    {
        'topic': 'multi-step word problems',
        'skill': 'multi-step arithmetic',
        'question': 'A class has 4 boxes with 6 pencils each. Then 5 pencils are used. How many pencils are left?',
        'expected_answer': '19',
        'hint_1': 'First find the total pencils in the boxes.',
        'hint_2': '4 x 6 = 24, then subtract 5.',
        'worked_explanation': '4 x 6 = 24, and 24 - 5 = 19.',
    },
    {
        'topic': 'place value with decimals',
        'skill': 'decimal comparison',
        'question': 'Which is larger: 0.48 or 0.5?',
        'expected_answer': '0.5',
        'hint_1': 'Write 0.5 as 0.50 to compare hundredths.',
        'hint_2': '50 hundredths is more than 48 hundredths.',
        'worked_explanation': '0.5 is larger because 0.50 > 0.48.',
    },
    {
        'topic': 'place value with decimals',
        'skill': 'decimal addition',
        'question': 'What is 1.2 + 0.3?',
        'expected_answer': '1.5',
        'hint_1': 'Add the tenths.',
        'hint_2': '2 tenths plus 3 tenths is 5 tenths.',
        'worked_explanation': '1.2 + 0.3 = 1.5.',
    },
    {
        'topic': 'place value with decimals',
        'skill': 'decimal subtraction',
        'question': 'What is 4.5 - 1.2?',
        'expected_answer': '3.3',
        'hint_1': 'Line up the decimal points.',
        'hint_2': '45 tenths - 12 tenths = 33 tenths.',
        'worked_explanation': '4.5 - 1.2 = 3.3.',
    },
)


GRADE_6_TUTOR_MATH: tuple[dict, ...] = (
    {
        'topic': 'negative numbers',
        'skill': 'integer operations',
        'question': 'What is -4 + 11?',
        'expected_answer': '7',
        'hint_1': 'Start at -4 and move 11 steps to the right.',
        'hint_2': 'Moving 4 steps gets to 0, then 7 more steps gets to 7.',
        'worked_explanation': '-4 + 11 = 7.',
    },
    {
        'topic': 'negative numbers',
        'skill': 'integer operations',
        'question': 'What is -9 + 5?',
        'expected_answer': '-4',
        'hint_1': 'Start at -9 and move 5 steps to the right.',
        'hint_2': 'Moving 5 steps right from -9 lands on -4.',
        'worked_explanation': '-9 + 5 = -4.',
    },
    {
        'topic': 'expressions and one-step equations',
        'skill': 'one-step equations',
        'question': 'Solve for x: x + 6 = 14. What is x?',
        'expected_answer': '8',
        'hint_1': 'Undo +6 by subtracting 6 from 14.',
        'hint_2': '14 - 6 = 8.',
        'worked_explanation': 'x + 6 = 14, so x = 14 - 6 = 8.',
    },
    {
        'topic': 'expressions and one-step equations',
        'skill': 'one-step equations',
        'question': 'Solve for x: x - 5 = 9. What is x?',
        'expected_answer': '14',
        'hint_1': 'Undo -5 by adding 5 to 9.',
        'hint_2': '9 + 5 = 14.',
        'worked_explanation': 'x - 5 = 9, so x = 9 + 5 = 14.',
    },
    {
        'topic': 'ratios and rates',
        'skill': 'ratios',
        'question': 'The ratio of cats to dogs is 2:3. If there are 10 cats, how many dogs are there?',
        'expected_answer': '15',
        'hint_1': '2 parts became 10, so each part is 5.',
        'hint_2': 'Dogs have 3 parts, and each part is 5.',
        'worked_explanation': '10 / 2 = 5, and 3 x 5 = 15 dogs.',
    },
    {
        'topic': 'ratios and rates',
        'skill': 'ratios',
        'question': 'The ratio of red beads to blue beads is 4:5. If there are 20 red beads, how many blue beads are there?',
        'expected_answer': '25',
        'hint_1': '4 parts became 20, so each part is 5.',
        'hint_2': 'Blue beads have 5 parts, and each part is 5.',
        'worked_explanation': '20 / 4 = 5, and 5 x 5 = 25 blue beads.',
    },
    {
        'topic': 'fraction and decimal fluency',
        'skill': 'fraction multiplication',
        'question': 'What is 4 x 9/5?',
        'expected_answer': '36/5',
        'accepted_answers': ('36/5', '7 1/5', '7.2'),
        'hint_1': 'Multiply the whole number by the numerator first.',
        'hint_2': '4 x 9 = 36, then keep the denominator 5.',
        'worked_explanation': '4 x 9/5 = 36/5.',
    },
    {
        'topic': 'fraction and decimal fluency',
        'skill': 'fraction multiplication',
        'question': 'What is 3 x 5/4?',
        'expected_answer': '15/4',
        'accepted_answers': ('15/4', '3 3/4', '3.75'),
        'hint_1': 'Multiply the whole number by the numerator first.',
        'hint_2': '3 x 5 = 15, then keep the denominator 4.',
        'worked_explanation': '3 x 5/4 = 15/4.',
    },
    {
        'topic': 'negative numbers',
        'skill': 'integer operations',
        'question': 'What is -6 + 13?',
        'expected_answer': '7',
        'hint_1': 'Start at -6 and move 13 steps to the right.',
        'hint_2': 'Moving 6 steps gets to 0, then 7 more steps gets to 7.',
        'worked_explanation': '-6 + 13 = 7.',
    },
    {
        'topic': 'negative numbers',
        'skill': 'integer operations',
        'question': 'What is -12 + 8?',
        'expected_answer': '-4',
        'hint_1': 'Start at -12 and move 8 steps to the right.',
        'hint_2': 'Moving 8 steps right from -12 lands on -4.',
        'worked_explanation': '-12 + 8 = -4.',
    },
    {
        'topic': 'negative numbers',
        'skill': 'integer operations',
        'question': 'What is 5 - 9?',
        'expected_answer': '-4',
        'hint_1': 'Subtracting 9 from 5 moves left past zero.',
        'hint_2': '5 - 5 = 0, then 4 more left is -4.',
        'worked_explanation': '5 - 9 = -4.',
    },
    {
        'topic': 'expressions and one-step equations',
        'skill': 'one-step equations',
        'question': 'Solve for x: x + 9 = 20. What is x?',
        'expected_answer': '11',
        'hint_1': 'Undo +9 by subtracting 9 from 20.',
        'hint_2': '20 - 9 = 11.',
        'worked_explanation': 'x + 9 = 20, so x = 20 - 9 = 11.',
    },
    {
        'topic': 'expressions and one-step equations',
        'skill': 'one-step equations',
        'question': 'Solve for x: x - 7 = 6. What is x?',
        'expected_answer': '13',
        'hint_1': 'Undo -7 by adding 7 to 6.',
        'hint_2': '6 + 7 = 13.',
        'worked_explanation': 'x - 7 = 6, so x = 6 + 7 = 13.',
    },
    {
        'topic': 'expressions and one-step equations',
        'skill': 'evaluating expressions',
        'question': 'What is 3a + 2 when a = 4?',
        'expected_answer': '14',
        'hint_1': 'Replace a with 4.',
        'hint_2': '3 x 4 + 2 = 12 + 2.',
        'worked_explanation': '3a + 2 with a = 4 is 3 x 4 + 2 = 14.',
    },
    {
        'topic': 'ratios and rates',
        'skill': 'ratios',
        'question': 'The ratio of apples to oranges is 3:2. If there are 12 apples, how many oranges are there?',
        'expected_answer': '8',
        'hint_1': '3 parts became 12, so each part is 4.',
        'hint_2': 'Oranges have 2 parts, and each part is 4.',
        'worked_explanation': '12 / 3 = 4, and 2 x 4 = 8 oranges.',
    },
    {
        'topic': 'ratios and rates',
        'skill': 'ratios',
        'question': 'The ratio of pens to pencils is 5:4. If there are 15 pens, how many pencils are there?',
        'expected_answer': '12',
        'hint_1': '5 parts became 15, so each part is 3.',
        'hint_2': 'Pencils have 4 parts, and each part is 3.',
        'worked_explanation': '15 / 5 = 3, and 4 x 3 = 12 pencils.',
    },
    {
        'topic': 'ratios and rates',
        'skill': 'unit rates',
        'question': 'A bike travels 18 miles in 3 hours. How many miles per hour is that?',
        'expected_answer': '6',
        'hint_1': 'Miles per hour means miles divided by hours.',
        'hint_2': 'Use 18 / 3.',
        'worked_explanation': '18 / 3 = 6, so the speed is 6 miles per hour.',
    },
    {
        'topic': 'fraction and decimal fluency',
        'skill': 'fraction multiplication',
        'question': 'What is 5 x 2/3?',
        'expected_answer': '10/3',
        'accepted_answers': ('10/3', '3 1/3'),
        'hint_1': 'Multiply the whole number by the numerator.',
        'hint_2': '5 x 2 = 10, then keep the denominator 3.',
        'worked_explanation': '5 x 2/3 = 10/3.',
    },
    {
        'topic': 'fraction and decimal fluency',
        'skill': 'decimal conversion',
        'question': 'Write 1/4 as a decimal.',
        'expected_answer': '0.25',
        'accepted_answers': ('0.25', '1/4'),
        'hint_1': 'One fourth means one divided by four.',
        'hint_2': 'A quarter of 1 dollar is 25 cents.',
        'worked_explanation': '1/4 = 0.25.',
    },
    {
        'topic': 'statistics and data displays',
        'skill': 'mean',
        'question': 'What is the mean of 4, 6, and 8?',
        'expected_answer': '6',
        'hint_1': 'Mean means add the numbers and divide by how many numbers there are.',
        'hint_2': '4 + 6 + 8 = 18, and there are 3 numbers.',
        'worked_explanation': '18 / 3 = 6, so the mean is 6.',
    },
)


TUTOR_MATH_BANK_BY_GRADE: dict[int, tuple[dict, ...]] = {
    3: GRADE_3_TUTOR_MATH,
    4: GRADE_4_TUTOR_MATH,
    5: GRADE_5_TUTOR_MATH,
    6: GRADE_6_TUTOR_MATH,
}


def all_tutor_math_questions() -> tuple[TutorMathPracticeQuestion, ...]:
    return _build_tutor_math_bank()


def tutor_math_questions_for_grade(grade: int) -> tuple[TutorMathPracticeQuestion, ...]:
    return tuple(question for question in _build_tutor_math_bank() if question.grade == grade)


def tutor_math_question_for_id(question_id: str) -> TutorMathPracticeQuestion | None:
    clean_id = str(question_id or '').strip()
    if not clean_id:
        return None
    for question in _build_tutor_math_bank():
        if question.id == clean_id:
            return question
    return None


def select_tutor_math_question(
    grade: int,
    topic: str = '',
    recent_question_ids: tuple[str, ...] | list[str] | None = None,
    seed: int | str | None = None,
) -> TutorMathPracticeQuestion:
    safe_grade = _safe_tutor_grade(grade)
    grade_questions = tutor_math_questions_for_grade(safe_grade)
    if not grade_questions:
        raise ValueError(f'No tutor Math questions available for grade={safe_grade}')

    candidates = _filter_questions_by_topic(grade_questions, topic)
    if not candidates:
        candidates = grade_questions

    recent_ids = {str(question_id) for question_id in (recent_question_ids or ()) if str(question_id).strip()}
    fresh_candidates = tuple(question for question in candidates if question.id not in recent_ids)
    if fresh_candidates:
        candidates = fresh_candidates

    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    return rng.choice(candidates)


def _safe_tutor_grade(grade: int) -> int:
    try:
        requested = int(grade)
    except (TypeError, ValueError):
        requested = min(LAUNCH_GRADES)
    if requested in LAUNCH_GRADES:
        return requested
    return min(LAUNCH_GRADES, key=lambda launch_grade: abs(launch_grade - requested))


def _filter_questions_by_topic(
    questions: tuple[TutorMathPracticeQuestion, ...],
    topic: str,
) -> tuple[TutorMathPracticeQuestion, ...]:
    query_tokens = _topic_tokens(topic)
    if not query_tokens:
        return questions
    scored: list[tuple[int, TutorMathPracticeQuestion]] = []
    for question in questions:
        searchable_tokens = _topic_tokens(f'{question.topic} {question.skill}')
        score = len(query_tokens.intersection(searchable_tokens))
        if score > 0:
            scored.append((score, question))
    if not scored:
        return ()
    best_score = max(score for score, _question in scored)
    return tuple(question for score, question in scored if score == best_score)


def _topic_tokens(text: str) -> set[str]:
    stop_words = {
        'and',
        'as',
        'basics',
        'foundations',
        'of',
        'the',
        'to',
        'with',
    }
    return {
        token
        for token in re.findall(r'[a-z0-9]+', str(text or '').lower())
        if token and token not in stop_words
    }


@lru_cache(maxsize=1)
def _build_tutor_math_bank() -> tuple[TutorMathPracticeQuestion, ...]:
    questions: list[TutorMathPracticeQuestion] = []
    for grade in LAUNCH_GRADES:
        for index, item in enumerate(TUTOR_MATH_BANK_BY_GRADE[grade], start=1):
            expected_answer = str(item['expected_answer'])
            accepted_answers = tuple(str(answer) for answer in item.get('accepted_answers', (expected_answer,)))
            questions.append(TutorMathPracticeQuestion(
                id=f'tutor-math-g{grade}-q{index:02d}',
                grade=grade,
                topic=str(item['topic']),
                skill=str(item['skill']),
                question=str(item['question']),
                expected_answer=expected_answer,
                accepted_answers=accepted_answers,
                hint_1=str(item['hint_1']),
                hint_2=str(item['hint_2']),
                worked_explanation=str(item['worked_explanation']),
                difficulty=str(item.get('difficulty', 'quick')),
            ))
    return tuple(questions)
