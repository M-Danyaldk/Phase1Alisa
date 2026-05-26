from typing import Dict, List

SUPPORTED_GRADES = list(range(3, 13))
LAUNCH_SUBJECTS = ['Math', 'ELA', 'Writing']
FUTURE_SUBJECTS = ['Science', 'Social Studies']

CURRICULUM: Dict[str, Dict[int, List[str]]] = {
    'Math': {
        3: ['multiplication and division foundations', 'fractions as parts of a whole', 'area and perimeter', 'measurement word problems', 'multi-step addition and subtraction'],
        4: ['multi-digit multiplication', 'long division foundations', 'equivalent fractions and decimals', 'factors and multiples', 'measurement and geometry'],
        5: ['fraction and decimal operations', 'volume', 'coordinate plane basics', 'multi-step word problems', 'place value with decimals'],
        6: ['ratios and rates', 'expressions and one-step equations', 'statistics and data displays', 'negative numbers', 'fraction and decimal fluency'],
        7: ['proportional relationships', 'rational number operations', 'linear expressions and equations', 'probability', 'scale drawings and geometry'],
        8: ['linear equations and functions', 'systems of equations introduction', 'transformations', 'integer exponents', 'Pythagorean theorem'],
        9: ['Algebra I foundations', 'linear and quadratic function introduction', 'systems and inequalities', 'data modeling', 'polynomial operations basics'],
        10: ['geometry proofs', 'congruence and similarity', 'right triangle trigonometry introduction', 'circles', 'coordinate geometry'],
        11: ['Algebra II functions', 'polynomial and rational functions', 'exponential and logarithmic functions', 'sequences and series', 'statistics and probability'],
        12: ['precalculus readiness', 'advanced function analysis', 'trigonometric functions', 'probability and statistics', 'college algebra readiness'],
    },
    'ELA': {
        3: ['reading comprehension', 'main idea and key details', 'vocabulary in context', 'story elements', 'paragraph response'],
        4: ['inference', 'theme', 'text structure', 'academic vocabulary', 'evidence-based answers'],
        5: ['compare texts', 'informational reading', 'figurative language', 'summarizing', 'text evidence'],
        6: ['literary analysis introduction', 'argument reading', 'nonfiction structure', 'vocabulary in context', 'central idea'],
        7: ['theme analysis', 'claims and evidence', 'rhetoric introduction', 'informational text analysis', 'author point of view'],
        8: ['deeper inference', 'argument analysis', 'source comparison', 'central idea development', 'tone and word choice'],
        9: ['literary analysis', 'informational text analysis', 'rhetoric', 'textual evidence', 'academic vocabulary'],
        10: ['complex literature', 'argument evaluation', 'theme development', 'author choices', 'comparative analysis'],
        11: ['American literature style analysis', 'rhetorical analysis', 'argument and evidence', 'research reading', 'historical context'],
        12: ['college and career reading', 'complex text synthesis', 'advanced rhetoric', 'literary interpretation', 'independent analysis'],
    },
    'Writing': {
        3: ['complete sentences', 'paragraph basics', 'narrative writing', 'opinion writing', 'informative writing'],
        4: ['paragraph organization', 'transitions', 'detail development', 'grammar basics', 'revision for clarity'],
        5: ['multi-paragraph writing', 'evidence use', 'introductions and conclusions', 'sentence variety', 'revision planning'],
        6: ['essay structure', 'claims and evidence', 'organization', 'grammar and conventions', 'sentence variety'],
        7: ['argument writing', 'explanatory writing', 'narrative development', 'citation introduction', 'revision and editing'],
        8: ['formal essay structure', 'analysis writing', 'evidence integration', 'coherence', 'revision and editing'],
        9: ['thesis writing', 'literary analysis essays', 'argument essays', 'grammar and style', 'coherence'],
        10: ['analytical writing', 'argument structure', 'evidence integration', 'style and tone', 'clear transitions'],
        11: ['research writing', 'rhetorical writing', 'advanced argument', 'synthesis', 'source integration'],
        12: ['college-ready writing', 'research and synthesis', 'literary analysis', 'personal writing', 'academic writing'],
    },
}

HANDWRITING_RUBRIC = ['legibility', 'spacing', 'neatness', 'letter formation', 'overall readability']


def is_supported_grade(grade: int) -> bool:
    return grade in SUPPORTED_GRADES


def subject_topics(subject: str, grade: int) -> list[str]:
    return CURRICULUM.get(subject, {}).get(grade, [])


def adjacent_progression(subject: str, enrolled_grade: int) -> str:
    topics = subject_topics(subject, enrolled_grade)
    return ', '.join(topics[:3]) if topics else 'foundational skills'


def curriculum_payload() -> dict:
    return {
        'supported_grades': SUPPORTED_GRADES,
        'grades': SUPPORTED_GRADES,
        'launch_subjects': LAUNCH_SUBJECTS,
        'future_subjects': FUTURE_SUBJECTS,
        'subjects': CURRICULUM,
        'subject_metadata': {
            'Math': {'label': 'Math', 'status': 'launch'},
            'ELA': {'label': 'English Language Arts', 'status': 'launch'},
            'Writing': {'label': 'Writing', 'status': 'launch'},
            'Science': {'label': 'Science', 'status': 'post_launch'},
            'Social Studies': {'label': 'Social Studies', 'status': 'post_launch'},
        },
    }
