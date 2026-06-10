import importlib
import asyncio
import inspect
import py_compile
from pathlib import Path


CHECK_MODULES = [
    'backend.scripts.check_assessment_bank',
    'backend.scripts.check_assessment_rotation',
    'backend.scripts.check_assessment_validation',
    'backend.scripts.check_assessment_question_results',
    'backend.scripts.check_assessment_score_feedback',
    'backend.scripts.check_tutoring_ladder',
]

COMPILE_TARGETS = [
    'backend/app/models.py',
    'backend/app/main.py',
    'backend/app/assessment_bank.py',
    'backend/app/assessment_selector.py',
    'backend/app/assessment_validation.py',
    'backend/app/assessment_result_items.py',
    'backend/app/database.py',
    'backend/app/services/app_data_service.py',
    'backend/app/services/assessment_service.py',
    'backend/app/services/tutor_answer_checker.py',
    'backend/scripts/check_assessment_bank.py',
    'backend/scripts/check_assessment_rotation.py',
    'backend/scripts/check_assessment_validation.py',
    'backend/scripts/check_assessment_question_results.py',
    'backend/scripts/check_assessment_score_feedback.py',
    'backend/scripts/check_tutoring_ladder.py',
]


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    print('Assessment QA suite starting.')

    for target in COMPILE_TARGETS:
        py_compile.compile(str(root / target), doraise=True)
    print(f'- Compile check passed for {len(COMPILE_TARGETS)} Python files.')

    for module_name in CHECK_MODULES:
        module = importlib.import_module(module_name)
        result = module.main()
        if inspect.isawaitable(result):
            asyncio.run(result)

    app_module = importlib.import_module('backend.app.main')
    if not getattr(app_module, 'app', None):
        raise SystemExit('FastAPI app import failed.')
    print('- Backend app import passed.')

    print('Assessment QA suite passed.')


if __name__ == '__main__':
    main()
