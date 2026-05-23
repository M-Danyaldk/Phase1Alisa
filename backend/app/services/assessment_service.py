import json
import re
from ..models import AssessmentRequest, AssessmentResult
from ..prompts import assessment_prompt
from ..services.llm.router import LLMRouter
from ..services.app_data_service import AppDataService
from ..services.learning_profile_service import LearningProfileService


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', text, re.S)
        if match:
            return json.loads(match.group(0))
        raise


def _list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []

async def evaluate_assessment(payload: AssessmentRequest) -> AssessmentResult:
    router = LLMRouter()
    prompt = assessment_prompt(payload.student, payload.subject, payload.grade, payload.questions, payload.answers)
    result = await router.generate(system=prompt, user='Evaluate this assessment and return only JSON.', purpose='assessment')
    try:
        parsed = _extract_json(result.text)
    except Exception:
        parsed = {
            'estimated_level': f'Grade {payload.grade} - needs review',
            'score_label': 'Needs manual review',
            'strengths': ['Student submitted assessment responses'],
            'learning_gaps': ['The response could not be parsed as JSON. Check model output.'],
            'recommended_progression': ['Start with one short guided review session'],
            'recommended_next_topics': [],
            'parent_summary': 'Ms Alisia received the assessment. A detailed evaluation can be generated after model output is corrected.'
        }
    assessment = AssessmentResult(
        subject=payload.subject,
        enrolled_grade=payload.grade,
        estimated_level=parsed.get('estimated_level', f'Grade {payload.grade} - needs review'),
        score_label=parsed.get('score_label', 'Evaluated'),
        strengths=_list(parsed.get('strengths'))[:5],
        learning_gaps=_list(parsed.get('learning_gaps'))[:5],
        recommended_progression=_list(parsed.get('recommended_progression'))[:5],
        recommended_next_topics=_list(parsed.get('recommended_next_topics'))[:5],
        parent_summary=parsed.get('parent_summary', ''),
        provider=result.provider,
        model=result.model
    )
    assessment_payload = {
        'child_id': payload.child_id,
        'student_name': payload.student.name,
        'subject': payload.subject,
        'enrolled_grade': payload.grade,
        'estimated_level': assessment.estimated_level,
        'score_label': assessment.score_label,
        'strengths': assessment.strengths,
        'learning_gaps': assessment.learning_gaps,
        'recommended_progression': assessment.recommended_progression,
        'recommended_next_topics': assessment.recommended_next_topics,
        'parent_summary': assessment.parent_summary,
        'provider': assessment.provider,
        'model': assessment.model,
    }
    await AppDataService().save_assessment(assessment_payload)
    await LearningProfileService().upsert_from_assessment(assessment_payload)
    return assessment
