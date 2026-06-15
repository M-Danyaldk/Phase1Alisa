from backend.scripts.check_tutoring_ladder import main as tutoring_ladder_main
from backend.scripts.check_tutor_flow_architecture import main as tutor_architecture_main

import asyncio


def main() -> None:
    print('Running tutoring ladder check...')
    tutoring_ladder_main()
    print('')
    print('Running tutor architecture check...')
    asyncio.run(tutor_architecture_main())
    print('')
    print('All tutor flow checks passed.')


if __name__ == '__main__':
    main()
