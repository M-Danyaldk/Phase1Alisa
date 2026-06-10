from collections import Counter
from dataclasses import dataclass
from hashlib import sha256

from .assessment_bank import AssessmentVersion, version_for, versions_for


@dataclass(frozen=True)
class AssessmentSelection:
    assessment_version: AssessmentVersion
    version_number: int
    question_ids: tuple[str, ...]
    previous_versions: tuple[int, ...]
    reason: str


def select_next_assessment_version(
    subject: str,
    grade: int,
    previous_versions: list[int] | tuple[int, ...] | None = None,
    child_id: str = '',
) -> AssessmentSelection:
    available_versions = versions_for(subject, grade)
    if not available_versions:
        raise ValueError(f'No assessment versions available for subject={subject} grade={grade}')

    available_numbers = [version.version for version in available_versions]
    available_set = set(available_numbers)
    clean_previous = tuple(version for version in (previous_versions or []) if version in available_set)
    last_version = clean_previous[0] if clean_previous else None
    ordered_numbers = _stable_order(available_numbers, subject, grade, child_id)
    used = set(clean_previous)

    unused = [number for number in ordered_numbers if number not in used and number != last_version]
    if unused:
        selected_number = unused[0]
        reason = 'first_attempt' if not clean_previous else 'unused_version'
        return _selection(subject, grade, selected_number, clean_previous, reason)

    if len(available_numbers) == 1:
        return _selection(subject, grade, available_numbers[0], clean_previous, 'only_available_version')

    usage_counts = Counter(clean_previous)
    least_used_count = min(usage_counts.get(number, 0) for number in available_numbers)
    least_used = [
        number for number in ordered_numbers
        if usage_counts.get(number, 0) == least_used_count and number != last_version
    ]
    if not least_used:
        least_used = [number for number in ordered_numbers if number != last_version]
    selected_number = least_used[0]
    return _selection(subject, grade, selected_number, clean_previous, 'least_recent_safe_rotation')


def previous_versions_from_assessments(
    rows: list[dict],
    subject: str,
    grade: int | None = None,
) -> tuple[int, ...]:
    versions: list[int] = []
    for row in rows:
        if row.get('subject') != subject:
            continue
        if grade is not None and _int_value(row.get('enrolled_grade')) not in (None, grade):
            continue
        version = _int_value(row.get('assessment_version'))
        if version is not None:
            versions.append(version)
    return tuple(versions)


def _selection(
    subject: str,
    grade: int,
    version_number: int,
    previous_versions: tuple[int, ...],
    reason: str,
) -> AssessmentSelection:
    assessment_version = version_for(subject, grade, version_number)
    return AssessmentSelection(
        assessment_version=assessment_version,
        version_number=version_number,
        question_ids=tuple(question.id for question in assessment_version.questions),
        previous_versions=previous_versions,
        reason=reason,
    )


def _stable_order(numbers: list[int], subject: str, grade: int, child_id: str) -> list[int]:
    ordered = sorted(numbers)
    if not child_id:
        return ordered
    seed = f'{child_id}|{subject}|{grade}'.encode('utf-8')
    offset = int(sha256(seed).hexdigest()[:8], 16) % len(ordered)
    return ordered[offset:] + ordered[:offset]


def _int_value(value: object) -> int | None:
    try:
        if value is None or value == '':
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
