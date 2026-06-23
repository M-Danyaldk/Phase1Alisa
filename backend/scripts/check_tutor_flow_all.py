from backend.scripts.check_tutoring_ladder import main as tutoring_ladder_main
from backend.scripts.check_tutor_flow_architecture import main as tutor_architecture_main
from backend.scripts.check_tutor_edge_matrix import main as tutor_edge_matrix_main
from backend.scripts.check_tutor_intent_routing import main as tutor_intent_routing_main
from backend.scripts.check_tutor_task_lifecycle import main as tutor_task_lifecycle_main
from backend.scripts.check_tutor_attempt_policy import main as tutor_attempt_policy_main
from backend.scripts.check_tutor_answer_attempt_feedback import main as tutor_answer_attempt_feedback_main
from backend.scripts.check_tutor_conceptual_math import main as tutor_conceptual_math_main
from backend.scripts.check_tutor_flow_alignment import main as tutor_flow_alignment_main
from backend.scripts.check_tutor_followup_transition import main as tutor_followup_transition_main
from backend.scripts.check_tutor_opening_mixed_math import main as tutor_opening_mixed_math_main
from backend.scripts.check_tutor_word_problem_schema import main as tutor_word_problem_schema_main
from backend.scripts.check_tutor_emotional_support import main as tutor_emotional_support_main
from backend.scripts.check_tutor_math_response_guard import main as tutor_math_response_guard_main
from backend.scripts.check_tutor_math_e2e import main as tutor_math_e2e_main
from backend.scripts.check_tutor_voice_parity import main as tutor_voice_parity_main
from backend.scripts.check_tutor_full_regression_matrix import main as tutor_full_regression_matrix_main
from backend.scripts.check_tutor_generated_invariants import main as tutor_generated_invariants_main
from backend.scripts.check_tutor_interpretation_schema import main as tutor_interpretation_schema_main
from backend.scripts.check_tutor_semantic_interpreter import main as tutor_semantic_interpreter_main
from backend.scripts.check_tutor_semantic_policy import main as tutor_semantic_policy_main
from backend.scripts.check_tutor_production_readiness import main as tutor_production_readiness_main
from backend.scripts.check_tutor_topic_lessons import main as tutor_topic_lessons_main
from backend.scripts.check_tutor_topic_e2e_matrix import main as tutor_topic_e2e_matrix_main
from backend.scripts.check_tutor_subject_baseline import main as tutor_subject_baseline_main
from backend.scripts.check_tutor_progressive_hints import main as tutor_progressive_hints_main

import asyncio


def main() -> None:
    print('Running tutor subject baseline check...')
    tutor_subject_baseline_main()
    print('')
    print('Running tutoring ladder check...')
    tutoring_ladder_main()
    print('')
    print('Running tutor architecture check...')
    asyncio.run(tutor_architecture_main())
    print('')
    print('Running tutor edge matrix check...')
    asyncio.run(tutor_edge_matrix_main())
    print('')
    print('Running tutor intent routing check...')
    asyncio.run(tutor_intent_routing_main())
    print('')
    print('Running tutor task lifecycle check...')
    tutor_task_lifecycle_main()
    print('')
    print('Running tutor attempt policy check...')
    tutor_attempt_policy_main()
    print('')
    print('Running tutor answer-attempt feedback check...')
    tutor_answer_attempt_feedback_main()
    print('')
    print('Running tutor conceptual Math check...')
    asyncio.run(tutor_conceptual_math_main())
    print('')
    print('Running tutor opening mixed Math check...')
    asyncio.run(tutor_opening_mixed_math_main())
    print('')
    print('Running tutor flow-alignment check...')
    tutor_flow_alignment_main()
    print('')
    print('Running tutor follow-up transition check...')
    tutor_followup_transition_main()
    print('')
    print('Running tutor progressive-hint check...')
    tutor_progressive_hints_main()
    print('')
    print('Running tutor word-problem schema check...')
    tutor_word_problem_schema_main()
    print('')
    print('Running tutor interpretation schema check...')
    tutor_interpretation_schema_main()
    print('')
    print('Running tutor semantic-interpreter check...')
    asyncio.run(tutor_semantic_interpreter_main())
    print('')
    print('Running tutor semantic-policy check...')
    tutor_semantic_policy_main()
    print('')
    print('Running tutor topic-lesson check...')
    asyncio.run(tutor_topic_lessons_main())
    print('')
    print('Running tutor emotional-support check...')
    tutor_emotional_support_main()
    print('')
    print('Running tutor Math response-guard check...')
    tutor_math_response_guard_main()
    print('')
    print('Running tutor Math endpoint E2E check...')
    tutor_math_e2e_main()
    print('')
    print('Running tutor topic endpoint matrix check...')
    tutor_topic_e2e_matrix_main()
    print('')
    print('Running tutor voice-parity check...')
    tutor_voice_parity_main()
    print('')
    print('Running tutor full regression matrix check...')
    tutor_full_regression_matrix_main()
    print('')
    print('Running tutor generated-invariant check...')
    tutor_generated_invariants_main()
    print('')
    print('Running tutor production-readiness check...')
    tutor_production_readiness_main()
    print('')
    print('All tutor flow checks passed.')


if __name__ == '__main__':
    main()
