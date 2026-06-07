import json
import re
import logging
from fastapi import HTTPException
from ..models import AssessmentRequest, AssessmentResult
from ..prompts import assessment_prompt
from ..services.llm.router import LLMRouter
from ..services.app_data_service import AppDataService
from ..services.learning_profile_service import LearningProfileService
from ..services.supabase_client import SupabaseClientError

logger = logging.getLogger(__name__)


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

async def evaluate_assessment(payload: AssessmentRequest, parent_id: str | None = None) -> AssessmentResult:
    router = LLMRouter()
    prompt = assessment_prompt(payload.student, payload.subject, payload.grade, payload.questions, payload.answers)
    try:
        result = await router.generate(system=prompt, user='Evaluate this assessment and return only JSON.', purpose='assessment')
    except Exception as exc:
        logger.warning('Assessment LLM evaluation failed for child %s subject %s: %s', payload.child_id, payload.subject, exc)
        raise HTTPException(status_code=503, detail='Ms. Alisia could not finish this check-in right now. Please try again in a little while.') from exc
    try:
        parsed = _extract_json(result.text)
    except Exception:
        parsed = {
            'estimated_level': 'Needs review',
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
        estimated_level=parsed.get('estimated_level', 'Needs review'),
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
        'parent_id': parent_id,
        'child_id': payload.child_id,
        'student_name': payload.student.name,
        'subject': payload.subject,
        'assessment_type': 'subject_check',
        'enrolled_grade': payload.grade,
        'estimated_level': assessment.estimated_level,
        'score_label': assessment.score_label,
        'result_summary': assessment.parent_summary,
        'strengths': assessment.strengths,
        'growth_areas': assessment.learning_gaps,
        'learning_gaps': assessment.learning_gaps,
        'recommended_progression': assessment.recommended_progression,
        'recommended_next_topics': assessment.recommended_next_topics,
        'parent_summary': assessment.parent_summary,
        'provider': assessment.provider,
        'model': assessment.model,
    }
    try:
        saved_assessment = await AppDataService().save_assessment(assessment_payload)
    except SupabaseClientError as exc:
        logger.warning('Assessment save failed for child %s subject %s: %s', payload.child_id, payload.subject, exc)
        raise HTTPException(status_code=503, detail='Ms. Alisia could not save this check-in right now. Please try again soon.') from exc
    except Exception as exc:
        logger.warning('Assessment save failed for child %s subject %s: %s', payload.child_id, payload.subject, exc)
        raise HTTPException(status_code=503, detail='Ms. Alisia could not save this check-in right now. Please try again soon.') from exc
    profile_payload = {**assessment_payload, 'assessment_result_id': saved_assessment.get('id')}
    try:
        await LearningProfileService().upsert_from_assessment(profile_payload)
    except SupabaseClientError as exc:
        logger.warning('Learning profile update failed for child %s subject %s: %s', payload.child_id, payload.subject, exc)
        raise HTTPException(status_code=503, detail='Ms. Alisia saved the check-in but could not update the learning path yet. Please try again soon.') from exc
    except Exception as exc:
        logger.warning('Learning profile update failed for child %s subject %s: %s', payload.child_id, payload.subject, exc)
        raise HTTPException(status_code=503, detail='Ms. Alisia saved the check-in but could not update the learning path yet. Please try again soon.') from exc
    return assessment
