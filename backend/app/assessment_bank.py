from dataclasses import dataclass
from functools import lru_cache

from .curriculum import LAUNCH_GRADES, LAUNCH_SUBJECTS


@dataclass(frozen=True)
class AssessmentQuestion:
    id: str
    subject: str
    grade: int
    version: int
    position: int
    skill: str
    question: str
    validation_type: str
    expected_answer: str
    accepted_answers: tuple[str, ...]
    rubric: tuple[str, ...]
    next_topic_if_incorrect: str
    child_correct_feedback: str
    child_incorrect_feedback: str


@dataclass(frozen=True)
class AssessmentVersion:
    subject: str
    grade: int
    version: int
    questions: tuple[AssessmentQuestion, ...]


NUMBER_WORDS = {
    0: 'zero',
    1: 'one',
    2: 'two',
    3: 'three',
    4: 'four',
    5: 'five',
    6: 'six',
    7: 'seven',
    8: 'eight',
    9: 'nine',
    10: 'ten',
    11: 'eleven',
    12: 'twelve',
    13: 'thirteen',
    14: 'fourteen',
    15: 'fifteen',
    16: 'sixteen',
    17: 'seventeen',
    18: 'eighteen',
    19: 'nineteen',
    20: 'twenty',
    21: 'twenty-one',
    22: 'twenty-two',
    23: 'twenty-three',
    24: 'twenty-four',
    25: 'twenty-five',
    26: 'twenty-six',
    27: 'twenty-seven',
    28: 'twenty-eight',
    29: 'twenty-nine',
    30: 'thirty',
    31: 'thirty-one',
    32: 'thirty-two',
    33: 'thirty-three',
    34: 'thirty-four',
    35: 'thirty-five',
    36: 'thirty-six',
    37: 'thirty-seven',
    38: 'thirty-eight',
    39: 'thirty-nine',
    40: 'forty',
    42: 'forty-two',
    45: 'forty-five',
    48: 'forty-eight',
    50: 'fifty',
    54: 'fifty-four',
    56: 'fifty-six',
    60: 'sixty',
    63: 'sixty-three',
    64: 'sixty-four',
    72: 'seventy-two',
    81: 'eighty-one',
    90: 'ninety',
    96: 'ninety-six',
    100: 'one hundred',
    102: 'one hundred two',
    108: 'one hundred eight',
    120: 'one hundred twenty',
    144: 'one hundred forty-four',
}


GRADE_MATH_CONFIG = {
    3: {
        'facts': [(4, 6), (7, 3), (5, 8), (9, 2), (6, 6), (8, 4), (3, 9), (7, 5), (4, 9), (6, 7),
                  (8, 3), (5, 7), (9, 4), (6, 8), (7, 6), (3, 8), (4, 7), (9, 5), (8, 6), (7, 8)],
        'fractions': [('2/4', '1/3', '2/4'), ('3/6', '1/4', '3/6'), ('1/2', '2/5', '1/2'), ('3/8', '1/4', '3/8'),
                      ('4/6', '1/2', '4/6'), ('2/3', '3/5', '2/3'), ('5/8', '1/2', '5/8'), ('3/4', '2/3', '3/4'),
                      ('2/5', '1/5', '2/5'), ('5/6', '3/4', '5/6'), ('4/8', '3/8', '4/8'), ('6/10', '1/2', '6/10'),
                      ('7/8', '3/4', '7/8'), ('2/6', '1/6', '2/6'), ('3/5', '1/2', '3/5'), ('4/5', '2/3', '4/5'),
                      ('5/10', '4/10', '5/10'), ('3/6', '2/6', '3/6'), ('6/8', '5/8', '6/8'), ('7/10', '3/5', '7/10')],
        'word': [(24, 4, 'stickers', 'bags'), (30, 5, 'pencils', 'cups'), (36, 6, 'cards', 'groups'), (28, 7, 'shells', 'jars'),
                 (32, 8, 'markers', 'boxes'), (27, 3, 'books', 'shelves'), (40, 5, 'crayons', 'packs'), (42, 6, 'beads', 'strings'),
                 (45, 9, 'erasers', 'trays'), (48, 8, 'coins', 'piles'), (21, 3, 'apples', 'plates'), (35, 5, 'tickets', 'rows'),
                 (54, 6, 'stickers', 'pages'), (56, 7, 'tiles', 'patterns'), (63, 9, 'blocks', 'towers'), (64, 8, 'flowers', 'vases'),
                 (72, 9, 'buttons', 'shirts'), (60, 6, 'photos', 'albums'), (81, 9, 'stars', 'charts'), (90, 10, 'paper clips', 'cups')],
    },
    4: {
        'facts': [(12, 4), (15, 3), (18, 5), (22, 4), (24, 3), (16, 6), (25, 4), (19, 5), (28, 3), (21, 6),
                  (32, 3), (14, 7), (26, 4), (17, 6), (23, 5), (34, 3), (27, 4), (31, 3), (29, 4), (18, 6)],
        'fractions': [('3/4', '2/3', '3/4'), ('5/6', '4/5', '5/6'), ('7/8', '3/4', '7/8'), ('2/3', '5/8', '2/3'),
                      ('4/5', '3/4', '4/5'), ('5/8', '1/2', '5/8'), ('6/10', '1/2', '6/10'), ('7/12', '1/2', '7/12'),
                      ('3/5', '4/10', '3/5'), ('5/9', '4/9', '5/9'), ('8/10', '3/4', '8/10'), ('11/12', '5/6', '11/12'),
                      ('4/6', '3/6', '4/6'), ('9/10', '4/5', '9/10'), ('6/8', '2/3', '6/8'), ('7/9', '2/3', '7/9'),
                      ('5/7', '4/7', '5/7'), ('3/8', '2/8', '3/8'), ('10/12', '3/4', '10/12'), ('4/9', '1/3', '4/9')],
        'word': [(48, 8, 'pages', 'days'), (36, 6, 'pencils', 'cups'), (56, 7, 'stickers', 'friends'), (72, 9, 'photos', 'albums'),
                 (45, 5, 'cookies', 'plates'), (64, 8, 'tiles', 'rows'), (84, 7, 'markers', 'boxes'), (96, 12, 'cards', 'packs'),
                 (54, 6, 'beads', 'bracelets'), (63, 9, 'books', 'shelves'), (80, 10, 'flowers', 'vases'), (90, 9, 'tickets', 'rows'),
                 (108, 12, 'coins', 'jars'), (120, 10, 'stickers', 'pages'), (144, 12, 'blocks', 'towers'), (75, 5, 'shells', 'bags'),
                 (88, 8, 'crayons', 'cups'), (99, 9, 'buttons', 'shirts'), (132, 11, 'paper clips', 'boxes'), (100, 10, 'stars', 'charts')],
    },
    5: {
        'facts': [(12, 1.5), (8, 2.5), (6, 3.5), (4, 4.5), (10, 2.2), (15, 1.2), (20, 1.5), (30, 1.1), (7, 2.4), (9, 3.2),
                  (16, 1.25), (24, 1.5), (18, 2.5), (14, 3.5), (11, 4.5), (13, 2.2), (17, 1.5), (19, 1.2), (21, 2.5), (25, 1.6)],
        'fractions': [('1/2 + 1/4', '3/4'), ('2/5 + 1/5', '3/5'), ('3/8 + 1/8', '4/8'), ('1/3 + 1/6', '1/2'),
                      ('2/6 + 3/6', '5/6'), ('1/4 + 2/4', '3/4'), ('3/10 + 2/10', '5/10'), ('2/3 + 1/3', '1'),
                      ('4/12 + 2/12', '6/12'), ('5/8 - 1/8', '4/8'), ('7/10 - 2/10', '5/10'), ('3/5 - 1/5', '2/5'),
                      ('5/6 - 2/6', '3/6'), ('6/8 - 3/8', '3/8'), ('9/12 - 3/12', '6/12'), ('1/5 + 3/5', '4/5'),
                      ('2/7 + 4/7', '6/7'), ('5/9 - 2/9', '3/9'), ('7/8 - 4/8', '3/8'), ('4/6 + 1/6', '5/6')],
        'word': [(3, 4, 5), (4, 5, 6), (5, 6, 7), (6, 7, 8), (7, 3, 5), (8, 4, 6), (9, 5, 7), (10, 6, 8),
                 (11, 3, 6), (12, 4, 7), (13, 5, 8), (14, 6, 9), (15, 4, 6), (16, 5, 7), (17, 6, 8), (18, 7, 9),
                 (19, 3, 7), (20, 4, 8), (21, 5, 9), (22, 6, 10)],
    },
    6: {
        'facts': [(3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10), (10, 11), (11, 12), (12, 13),
                  (13, 14), (14, 15), (15, 16), (16, 17), (17, 18), (18, 19), (19, 20), (20, 21), (21, 22), (22, 23)],
        'fractions': [('-3 + 8', '5'), ('-5 + 12', '7'), ('-4 + 9', '5'), ('-7 + 10', '3'), ('-6 + 15', '9'),
                      ('-9 + 14', '5'), ('-8 + 11', '3'), ('-12 + 20', '8'), ('-10 + 16', '6'), ('-15 + 18', '3'),
                      ('-11 + 19', '8'), ('-13 + 17', '4'), ('-14 + 21', '7'), ('-16 + 22', '6'), ('-18 + 25', '7'),
                      ('-20 + 30', '10'), ('-22 + 31', '9'), ('-24 + 32', '8'), ('-25 + 35', '10'), ('-27 + 36', '9')],
        'word': [(2, 3, 18), (3, 4, 24), (4, 5, 40), (5, 6, 45), (6, 7, 42), (7, 8, 56), (8, 9, 72), (9, 10, 90),
                 (10, 11, 110), (11, 12, 132), (12, 13, 156), (13, 14, 182), (14, 15, 210), (15, 16, 240), (16, 17, 272),
                 (17, 18, 306), (18, 19, 342), (19, 20, 380), (20, 21, 420), (21, 22, 462)],
    },
}


ELA_BANK = {
    3: {
        'vocab': [('sprinted', 'ran fast'), ('tiny', 'very small'), ('shouted', 'said loudly'), ('brave', 'not afraid'),
                  ('silent', 'quiet'), ('gathered', 'collected'), ('glad', 'happy'), ('tossed', 'threw'),
                  ('nearby', 'close'), ('careful', 'safe and thoughtful'), ('quickly', 'fast'), ('enormous', 'very big'),
                  ('damp', 'slightly wet'), ('clever', 'smart'), ('startled', 'surprised'), ('finish', 'complete'),
                  ('gentle', 'kind and soft'), ('bright', 'shiny'), ('repair', 'fix'), ('choose', 'pick')],
        'grammar': [('she dont like apples', "She doesn't like apples."), ('he run to school', 'He runs to school.'),
                    ('they was late', 'They were late.'), ('i like my book', 'I like my book.'),
                    ('we goed home', 'We went home.'), ('the dog are brown', 'The dog is brown.'),
                    ('mia have a pencil', 'Mia has a pencil.'), ('tom dont see it', "Tom doesn't see it."),
                    ('can i play', 'Can I play?'), ('the cat sleep', 'The cat sleeps.'),
                    ('we is ready', 'We are ready.'), ('she have lunch', 'She has lunch.'),
                    ('i am happy', 'I am happy.'), ('they go yesterday', 'They went yesterday.'),
                    ('he dont know', "He doesn't know."), ('the birds is loud', 'The birds are loud.'),
                    ('where is sam', 'Where is Sam?'), ('i saw a dog', 'I saw a dog.'),
                    ('she run fast', 'She runs fast.'), ('we was outside', 'We were outside.')],
    },
    4: {
        'vocab': [('leaped', 'jumped'), ('rapid', 'fast'), ('ancient', 'very old'), ('exclaimed', 'said suddenly'),
                  ('observe', 'watch carefully'), ('assist', 'help'), ('rare', 'unusual'), ('calm', 'peaceful'),
                  ('predict', 'make a smart guess'), ('select', 'choose'), ('compare', 'tell how things are alike or different'),
                  ('evidence', 'proof from the text'), ('fragile', 'easy to break'), ('generous', 'giving'), ('curious', 'wanting to know'),
                  ('ordinary', 'normal'), ('protect', 'keep safe'), ('arrive', 'come'), ('depart', 'leave'), ('notice', 'see')],
        'grammar': [('she dont want to go', "She doesn't want to go."), ('they was playing', 'They were playing.'),
                    ('he have two books', 'He has two books.'), ('i readed it', 'I read it.'),
                    ('we seen the bird', 'We saw the bird.'), ('the teams is ready', 'The teams are ready.'),
                    ('mia and i was late', 'Mia and I were late.'), ('it dont make sense', "It doesn't make sense."),
                    ('where are my pencil', 'Where is my pencil?'), ('the story have a lesson', 'The story has a lesson.'),
                    ('they goes outside', 'They go outside.'), ('he dont agree', "He doesn't agree."),
                    ('i goed to class', 'I went to class.'), ('the boxes is heavy', 'The boxes are heavy.'),
                    ('she write neatly', 'She writes neatly.'), ('we was careful', 'We were careful.'),
                    ('did you seen it', 'Did you see it?'), ('he runned home', 'He ran home.'),
                    ('the children was quiet', 'The children were quiet.'), ('i has a question', 'I have a question.')],
    },
    5: {
        'vocab': [('reluctant', 'not wanting to'), ('analyze', 'study carefully'), ('confident', 'sure'), ('scarce', 'hard to find'),
                  ('fortunate', 'lucky'), ('contrast', 'tell how things are different'), ('summarize', 'tell the main points'),
                  ('support', 'give proof'), ('significant', 'important'), ('expand', 'make bigger'), ('accurate', 'correct'),
                  ('create', 'make'), ('respond', 'answer'), ('investigate', 'look into'), ('complex', 'not simple'),
                  ('conclude', 'decide from evidence'), ('frequent', 'often'), ('impact', 'effect'), ('method', 'way'), ('benefit', 'helpful result')],
        'grammar': [('the students was excited', 'The students were excited.'), ('she dont understand', "She doesn't understand."),
                    ('he have finished', 'He has finished.'), ('we seen the movie', 'We saw the movie.'),
                    ('they has a plan', 'They have a plan.'), ('the books is on the shelf', 'The books are on the shelf.'),
                    ('i goed to practice', 'I went to practice.'), ('does they know', 'Do they know?'),
                    ('the answer dont fit', "The answer doesn't fit."), ('mia and leo was ready', 'Mia and Leo were ready.'),
                    ('she write a paragraph', 'She writes a paragraph.'), ('we was surprised', 'We were surprised.'),
                    ('he dont remember', "He doesn't remember."), ('the facts supports the idea', 'The facts support the idea.'),
                    ('i has two reasons', 'I have two reasons.'), ('they goes first', 'They go first.'),
                    ('the lesson have examples', 'The lesson has examples.'), ('did she went home', 'Did she go home?'),
                    ('the clouds was dark', 'The clouds were dark.'), ('he runned quickly', 'He ran quickly.')],
    },
    6: {
        'vocab': [('interpret', 'explain the meaning'), ('perspective', 'point of view'), ('relevant', 'connected and useful'),
                  ('evaluate', 'judge carefully'), ('infer', 'figure out from clues'), ('claim', 'main argument'),
                  ('theme', 'lesson or message'), ('central idea', 'main point'), ('cite', 'quote or mention evidence'),
                  ('precise', 'exact'), ('revise', 'change to improve'), ('credible', 'trustworthy'), ('tone', 'author attitude'),
                  ('structure', 'how text is organized'), ('transition', 'word that connects ideas'), ('objective', 'not based on feelings'),
                  ('analyze', 'study parts carefully'), ('evidence', 'proof from text'), ('context', 'surrounding information'),
                  ('consequence', 'result')],
        'grammar': [('the evidence support the claim', 'The evidence supports the claim.'), ('they was discussing the theme', 'They were discussing the theme.'),
                    ('she dont cite evidence', "She doesn't cite evidence."), ('he have a strong reason', 'He has a strong reason.'),
                    ('the sources is credible', 'The sources are credible.'), ('we seen the pattern', 'We saw the pattern.'),
                    ('did they went outside', 'Did they go outside?'), ('the author dont explain it', "The author doesn't explain it."),
                    ('i has a conclusion', 'I have a conclusion.'), ('the paragraphs was organized', 'The paragraphs were organized.'),
                    ('she write with detail', 'She writes with detail.'), ('the examples supports the topic', 'The examples support the topic.'),
                    ('he dont compare the texts', "He doesn't compare the texts."), ('the claims is different', 'The claims are different.'),
                    ('we was careful readers', 'We were careful readers.'), ('they has evidence', 'They have evidence.'),
                    ('the sentence dont flow', "The sentence doesn't flow."), ('i goed back to revise', 'I went back to revise.'),
                    ('the details was relevant', 'The details were relevant.'), ('does the reasons match', 'Do the reasons match?')],
    },
}


WRITING_TOPICS = {
    3: [('a favorite game', 'games are fun'), ('a helpful friend', 'friends help each other'), ('a sunny day', 'sunny days feel nice'),
        ('a good book', 'reading is helpful'), ('a school rule', 'rules keep people safe'), ('a pet', 'pets need care'),
        ('a lunch you like', 'food can be special'), ('a place to play', 'play helps kids'), ('a classroom job', 'jobs teach responsibility'),
        ('a rainy day', 'rain changes plans'), ('a family tradition', 'traditions matter'), ('a kind action', 'kindness helps'),
        ('a new skill', 'practice helps'), ('a favorite animal', 'animals are interesting'), ('a morning routine', 'routines help'),
        ('a science fact', 'facts teach us'), ('a sport', 'teams work together'), ('a quiet place', 'quiet helps focus'),
        ('a birthday memory', 'memories can be special'), ('a garden', 'plants need care')],
    4: [('a place you like', 'details help readers picture it'), ('why practice matters', 'practice builds skill'), ('a helpful invention', 'inventions solve problems'),
        ('a character who changes', 'characters can learn'), ('a favorite tradition', 'traditions connect people'), ('how to be organized', 'organization saves time'),
        ('a time you solved a problem', 'problem solving takes steps'), ('why reading helps', 'reading builds knowledge'), ('a strong classroom rule', 'rules support learning'),
        ('a favorite season', 'seasons have different details'), ('a person you admire', 'examples show why'), ('how to care for a pet', 'care has steps'),
        ('a memorable trip', 'details make writing stronger'), ('why teamwork matters', 'teamwork helps groups'), ('a hobby', 'hobbies take practice'),
        ('a food you enjoy', 'sensory details help'), ('a school subject', 'reasons support opinions'), ('how to stay focused', 'focus helps learning'),
        ('a goal for the year', 'goals need steps'), ('a community helper', 'helpers support people')],
    5: [('why evidence matters', 'evidence supports ideas'), ('a challenge you overcame', 'challenges teach lessons'),
        ('a favorite story theme', 'themes show messages'), ('how technology helps students', 'technology has benefits'),
        ('why exercise is useful', 'exercise supports health'), ('a historical person', 'specific facts help'),
        ('how to prepare for a test', 'preparation has steps'), ('why kindness matters', 'kindness affects others'),
        ('a place worth visiting', 'details persuade readers'), ('a book recommendation', 'reasons support opinions'),
        ('how to solve a disagreement', 'solutions need respect'), ('why chores can help', 'chores teach responsibility'),
        ('a science topic', 'examples explain concepts'), ('a personal goal', 'plans support success'),
        ('why teamwork matters', 'roles help teams'), ('a memorable lesson', 'reflection shows learning'),
        ('how to save money', 'choices affect goals'), ('a favorite activity', 'details build interest'),
        ('why sleep matters', 'rest supports learning'), ('a community problem', 'solutions can help')],
    6: [('a claim about homework', 'claims need evidence'), ('how a character develops', 'details show change'),
        ('why reliable sources matter', 'credibility affects trust'), ('a problem and solution', 'solutions need reasons'),
        ('how setting affects a story', 'setting shapes events'), ('a healthy habit', 'habits affect outcomes'),
        ('why revision improves writing', 'revision clarifies ideas'), ('a comparison of two activities', 'comparison needs criteria'),
        ('how leaders help groups', 'leadership includes choices'), ('a theme from a story', 'themes need text evidence'),
        ('why goals matter', 'goals guide actions'), ('a community improvement', 'evidence supports proposals'),
        ('how technology changes communication', 'effects can be positive or negative'), ('a personal strength', 'examples make claims believable'),
        ('why fairness matters', 'fairness affects trust'), ('a scientific process', 'steps explain how it works'),
        ('how conflict can be solved', 'solutions require evidence'), ('a historical event', 'causes and effects matter'),
        ('why organization matters', 'structure helps readers'), ('a future career', 'reasons explain interest')],
}


def all_assessment_versions() -> tuple[AssessmentVersion, ...]:
    return _build_assessment_bank()


def versions_for(subject: str, grade: int) -> tuple[AssessmentVersion, ...]:
    return tuple(version for version in _build_assessment_bank() if version.subject == subject and version.grade == grade)


def version_for(subject: str, grade: int, version_number: int) -> AssessmentVersion:
    for version in versions_for(subject, grade):
        if version.version == version_number:
            return version
    raise ValueError(f'No assessment version for subject={subject} grade={grade} version={version_number}')


def question_for_id(question_id: str) -> AssessmentQuestion | None:
    clean_id = str(question_id or '').strip()
    if not clean_id:
        return None
    for version in _build_assessment_bank():
        for question in version.questions:
            if question.id == clean_id:
                return question
    return None


@lru_cache(maxsize=1)
def _build_assessment_bank() -> tuple[AssessmentVersion, ...]:
    versions: list[AssessmentVersion] = []
    for grade in LAUNCH_GRADES:
        versions.extend(_math_versions(grade))
        versions.extend(_ela_versions(grade))
        versions.extend(_writing_versions(grade))
    return tuple(versions)


def _math_versions(grade: int) -> list[AssessmentVersion]:
    config = GRADE_MATH_CONFIG[grade]
    versions = []
    for index in range(20):
        version = index + 1
        questions = (
            _math_computation_question(grade, version, config['facts'][index]),
            _math_reasoning_question(grade, version, config['fractions'][index]),
            _math_word_problem_question(grade, version, config['word'][index]),
        )
        versions.append(AssessmentVersion(subject='Math', grade=grade, version=version, questions=questions))
    return versions


def _ela_versions(grade: int) -> list[AssessmentVersion]:
    bank = ELA_BANK[grade]
    versions = []
    for index in range(20):
        version = index + 1
        vocab_word, vocab_meaning = bank['vocab'][index]
        grammar_source, grammar_answer = bank['grammar'][index]
        questions = (
            _question(
                subject='ELA',
                grade=grade,
                version=version,
                position=1,
                skill='vocabulary in context',
                question=f'Read this sentence: The student {vocab_word} during the activity. What does "{vocab_word}" mean?',
                validation_type='keyword_text',
                expected_answer=vocab_meaning,
                accepted_answers=_text_acceptance(vocab_meaning),
                rubric=('Answer gives the meaning in the sentence context.', 'Minor wording differences are acceptable.'),
                next_topic='vocabulary in context',
            ),
            _question(
                subject='ELA',
                grade=grade,
                version=version,
                position=2,
                skill='main idea and evidence',
                question=_reading_prompt(grade, version),
                validation_type='keyword_text',
                expected_answer=_reading_expected(grade, version),
                accepted_answers=_text_acceptance(_reading_expected(grade, version)),
                rubric=('Answer names the main idea or inference.', 'Answer includes one useful detail from the passage.'),
                next_topic='reading comprehension',
            ),
            _question(
                subject='ELA',
                grade=grade,
                version=version,
                position=3,
                skill='grammar and conventions',
                question=f'Fix this sentence: {grammar_source}',
                validation_type='exact_text',
                expected_answer=grammar_answer,
                accepted_answers=(grammar_answer, grammar_answer.rstrip('.?')),
                rubric=('Correct capitalization, grammar, and ending punctuation.',),
                next_topic='grammar and conventions',
            ),
        )
        versions.append(AssessmentVersion(subject='ELA', grade=grade, version=version, questions=questions))
    return versions


def _writing_versions(grade: int) -> list[AssessmentVersion]:
    versions = []
    for index, (topic, reason) in enumerate(WRITING_TOPICS[grade]):
        version = index + 1
        questions = (
            _question(
                subject='Writing',
                grade=grade,
                version=version,
                position=1,
                skill='complete sentence',
                question=f'Write one clear sentence about {topic}.',
                validation_type='writing_rubric',
                expected_answer='One complete sentence that stays on topic.',
                accepted_answers=(),
                rubric=('Writes one complete sentence.', 'Uses a capital letter and ending punctuation.', 'Stays on the topic.'),
                next_topic='complete sentences',
            ),
            _question(
                subject='Writing',
                grade=grade,
                version=version,
                position=2,
                skill='explanatory writing',
                question=f'Write 3 sentences that explain why {reason}.',
                validation_type='writing_rubric',
                expected_answer='Three connected explanatory sentences with a clear reason and details.',
                accepted_answers=(),
                rubric=('Includes three sentences.', 'Explains a reason clearly.', 'Adds at least one supporting detail.'),
                next_topic='explanatory writing',
            ),
            _question(
                subject='Writing',
                grade=grade,
                version=version,
                position=3,
                skill='revision for detail',
                question=f'How can you make this sentence stronger: {_revision_sentence(grade, version)}?',
                validation_type='writing_rubric',
                expected_answer='A stronger sentence with more specific detail or vivid word choice.',
                accepted_answers=(),
                rubric=('Keeps the original meaning.', 'Adds specific detail or stronger word choice.', 'Writes a complete sentence.'),
                next_topic='revision for detail',
            ),
        )
        versions.append(AssessmentVersion(subject='Writing', grade=grade, version=version, questions=questions))
    return versions


def _math_computation_question(grade: int, version: int, values: tuple) -> AssessmentQuestion:
    if grade == 5:
        left, right = values
        answer = _format_decimal(left * right)
        question = f'What is {left} x {right}?'
        skill = 'decimal multiplication'
    elif grade == 6:
        left, right = values
        total = left + right
        answer = str(right)
        question = f'Solve for x: x + {left} = {total}. What is x?'
        skill = 'one-step equations'
    else:
        left, right = values
        answer = str(left * right)
        question = f'What is {left} x {right}?'
        skill = 'multiplication facts' if grade == 3 else 'multi-digit multiplication'
    return _question(
        subject='Math',
        grade=grade,
        version=version,
        position=1,
        skill=skill,
        question=question,
        validation_type='numeric',
        expected_answer=answer,
        accepted_answers=_numeric_acceptance(answer),
        rubric=(),
        next_topic=skill,
    )


def _math_reasoning_question(grade: int, version: int, values: tuple[str, str] | tuple[str, str, str]) -> AssessmentQuestion:
    if grade == 5:
        expression, answer = values
        question = f'What is {expression}?'
        skill = 'fraction operations'
    elif grade == 6:
        expression, answer = values
        question = f'What is {expression}?'
        skill = 'integer operations'
    else:
        left, right, answer = values
        question = f'Which is larger: {left} or {right}? Explain briefly.'
        skill = 'fraction comparison'
    return _question(
        subject='Math',
        grade=grade,
        version=version,
        position=2,
        skill=skill,
        question=question,
        validation_type='numeric_or_fraction',
        expected_answer=answer,
        accepted_answers=_numeric_acceptance(answer),
        rubric=(),
        next_topic=skill,
    )


def _math_word_problem_question(grade: int, version: int, values: tuple) -> AssessmentQuestion:
    if grade == 5:
        length, width, height = values
        answer = str(length * width * height)
        question = f'A box is {length} units long, {width} units wide, and {height} units tall. What is its volume?'
        skill = 'volume word problems'
    elif grade == 6:
        first, second, groups = values
        total = (first + second) * groups
        answer = str(groups)
        question = f'The ratio of blue beads to red beads is {first}:{second}. There are {total} beads total. How many groups of {first + second} beads are there?'
        skill = 'ratios'
    else:
        total, group_size, item, group = values
        answer = str(total // group_size)
        if grade == 4 and version == 1:
            question = 'A book has 48 pages. Mia reads 8 pages each day. How many days will it take?'
        else:
            question = f'There are {total} {item}. If {group_size} {item} go in each {group}, how many {group} are needed?'
        skill = 'division word problems'
    return _question(
        subject='Math',
        grade=grade,
        version=version,
        position=3,
        skill=skill,
        question=question,
        validation_type='numeric',
        expected_answer=answer,
        accepted_answers=_numeric_acceptance(answer),
        rubric=(),
        next_topic=skill,
    )


def _question(
    subject: str,
    grade: int,
    version: int,
    position: int,
    skill: str,
    question: str,
    validation_type: str,
    expected_answer: str,
    accepted_answers: tuple[str, ...],
    rubric: tuple[str, ...],
    next_topic: str,
) -> AssessmentQuestion:
    prefix = subject.lower().replace('ela', 'reading')
    question_id = f'{prefix}-g{grade}-v{version:02d}-q{position}'
    return AssessmentQuestion(
        id=question_id,
        subject=subject,
        grade=grade,
        version=version,
        position=position,
        skill=skill,
        question=question,
        validation_type=validation_type,
        expected_answer=expected_answer,
        accepted_answers=accepted_answers,
        rubric=rubric,
        next_topic_if_incorrect=next_topic,
        child_correct_feedback=f'Great job. You handled this {skill} question correctly.',
        child_incorrect_feedback=f'Good try. We will practice {next_topic} together one step at a time.',
    )


def _numeric_acceptance(answer: str) -> tuple[str, ...]:
    values = {answer}
    normalized = answer.strip()
    if normalized.endswith('.0'):
        values.add(normalized[:-2])
    try:
        number = int(float(normalized))
        if float(normalized) == number:
            values.add(str(number))
            values.add(f'{number} days')
            if number in NUMBER_WORDS:
                values.add(NUMBER_WORDS[number])
                values.add(f'{NUMBER_WORDS[number]} days')
    except ValueError:
        pass
    if '/' in normalized:
        values.add(normalized.replace(' ', ''))
    return tuple(sorted(values))


def _text_acceptance(answer: str) -> tuple[str, ...]:
    parts = [answer]
    if ' and ' in answer:
        parts.extend(part.strip() for part in answer.split(' and ') if part.strip())
    if ' or ' in answer:
        parts.extend(part.strip() for part in answer.split(' or ') if part.strip())
    return tuple(dict.fromkeys(parts))


def _reading_prompt(grade: int, version: int) -> str:
    subjects = ['Mia', 'Leo', 'Ava', 'Noah', 'Sofia', 'Eli', 'Zara', 'Owen', 'Nina', 'Mateo',
                'Lina', 'Sam', 'Ivy', 'Omar', 'Rosa', 'Jamal', 'Tara', 'Ben', 'Maya', 'Luis']
    activities = ['watered the class plant', 'organized the books', 'helped a new student', 'checked the weather chart',
                  'shared art supplies', 'read the directions twice', 'packed the soccer balls', 'picked up litter',
                  'made a study plan', 'fixed the group poster', 'measured the table', 'sorted the recycling',
                  'wrote notes from the passage', 'asked a thoughtful question', 'compared two stories',
                  'found evidence in the text', 'revised the paragraph', 'explained the rule', 'saved money for a trip',
                  'practiced the piano']
    outcomes = ['the plant looked healthy', 'everyone found a book quickly', 'the student felt welcome',
                'the class knew rain was coming', 'the group finished the project', 'the work had fewer mistakes',
                'practice started on time', 'the playground looked cleaner', 'the homework felt easier',
                'the poster was easier to read', 'the team had the right size', 'the bins were neat',
                'the summary was clearer', 'the group understood better', 'the answer used good evidence',
                'the response was stronger', 'the writing sounded clearer', 'the class followed it',
                'the goal felt possible', 'the song improved']
    index = version - 1
    subject = subjects[index]
    activity = activities[index]
    outcome = outcomes[index]
    if grade <= 4:
        return f'Read this short passage: {subject} {activity}. After that, {outcome}. What is the main idea?'
    return f'Read this short passage: {subject} {activity}. After that, {outcome}. What can you infer about {subject}?'


def _reading_expected(grade: int, version: int) -> str:
    if grade <= 4:
        return 'The main idea is that one helpful action made things better.'
    return 'You can infer the student was responsible and used a helpful strategy.'


def _revision_sentence(grade: int, version: int) -> str:
    adjectives = ['nice', 'good', 'fun', 'big', 'small', 'interesting', 'helpful', 'cool', 'easy', 'hard',
                  'pretty', 'fast', 'slow', 'loud', 'quiet', 'bright', 'dark', 'happy', 'kind', 'important']
    nouns = ['game', 'lesson', 'book', 'dog', 'place', 'project', 'idea', 'trip', 'meal', 'story',
             'song', 'team', 'rule', 'room', 'garden', 'poster', 'answer', 'friend', 'goal', 'event']
    index = version - 1
    if grade <= 4:
        return f'The {nouns[index]} was {adjectives[index]}.'
    return f'The {nouns[index]} was {adjectives[index]}, and I liked it.'


def _format_decimal(value: float) -> str:
    text = f'{value:.2f}'.rstrip('0').rstrip('.')
    return text


EXPECTED_VERSION_COUNT = 20
EXPECTED_QUESTIONS_PER_VERSION = 3
EXPECTED_TOTAL_QUESTIONS = len(LAUNCH_GRADES) * len(LAUNCH_SUBJECTS) * EXPECTED_VERSION_COUNT * EXPECTED_QUESTIONS_PER_VERSION
