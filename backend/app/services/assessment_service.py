import json
import re
from ..models import AssessmentRequest, AssessmentResult
from ..prompts import assessment_prompt
from ..services.llm.router import LLMRouter
from ..services.app_data_service import AppDataService


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', text, re.S)
        if match:
            return json.loads(match.group(0))
        raise

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
            'parent_summary': 'Ms Alisia received the assessment. A detailed evaluation can be generated after model output is corrected.'
        }
    assessment = AssessmentResult(
        subject=payload.subject,
        enrolled_grade=payload.grade,
        estimated_level=parsed.get('estimated_level', f'Grade {payload.grade} - needs review'),
        score_label=parsed.get('score_label', 'Evaluated'),
        strengths=list(parsed.get('strengths', []))[:5],
        learning_gaps=list(parsed.get('learning_gaps', []))[:5],
        recommended_progression=list(parsed.get('recommended_progression', []))[:5],
        parent_summary=parsed.get('parent_summary', ''),
        provider=result.provider,
        model=result.model
    )
    await AppDataService().save_assessment({
        'child_id': payload.child_id,
        'student_name': payload.student.name,
        'subject': payload.subject,
        'enrolled_grade': payload.grade,
        'estimated_level': assessment.estimated_level,
        'score_label': assessment.score_label,
        'strengths': assessment.strengths,
        'learning_gaps': assessment.learning_gaps,
        'recommended_progression': assessment.recommended_progression,
        'parent_summary': assessment.parent_summary,
        'provider': assessment.provider,
        'model': assessment.model,
    })
    return assessment
