from typing import Dict, List

CURRICULUM: Dict[str, Dict[int, List[str]]] = {
    'Math': {
        3: ['multiplication facts', 'division basics', 'fractions as parts', 'area and perimeter', 'word problems'],
        4: ['multi-digit multiplication', 'long division basics', 'equivalent fractions', 'decimals introduction', 'geometry basics'],
        5: ['fraction operations', 'decimal operations', 'volume', 'multi-step word problems', 'coordinate planes'],
        6: ['ratios', 'unit rates', 'expressions', 'one-step equations', 'statistics basics']
    },
    'ELA': {
        3: ['main idea', 'context clues', 'grammar basics', 'character traits', 'paragraph comprehension'],
        4: ['theme', 'inference', 'vocabulary in context', 'text structure', 'evidence from text'],
        5: ['summarizing', 'point of view', 'figurative language', 'compare and contrast', 'informational text'],
        6: ['central idea', 'argument and evidence', 'author purpose', 'complex vocabulary', 'literary analysis basics']
    },
    'Writing': {
        3: ['complete sentences', 'capitalization and punctuation', 'simple paragraph', 'clear topic sentence'],
        4: ['paragraph organization', 'supporting details', 'transitions', 'grammar revision'],
        5: ['multi-paragraph writing', 'evidence and explanation', 'sentence variety', 'revision clarity'],
        6: ['structured essay', 'claim and evidence', 'organization', 'style and tone']
    }
}

HANDWRITING_RUBRIC = ['legibility', 'spacing', 'neatness', 'letter formation', 'overall readability']

def subject_topics(subject: str, grade: int) -> list[str]:
    return CURRICULUM.get(subject, {}).get(grade, [])

def adjacent_progression(subject: str, enrolled_grade: int) -> str:
    topics = subject_topics(subject, enrolled_grade)
    return ', '.join(topics[:3]) if topics else 'foundational skills'
