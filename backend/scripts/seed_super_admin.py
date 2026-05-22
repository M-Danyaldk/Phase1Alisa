import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.supabase_client import SupabaseClient, SupabaseClientError  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description='Create the first MsAlisia super admin.')
    parser.add_argument('--email', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()

    supabase = SupabaseClient()
    permissions = [
        'manage_users',
        'manage_subscriptions',
        'manage_courses',
        'view_analytics',
        'refund_payments',
        'manage_admins',
        'manage_settings',
    ]
    try:
        user = await supabase.create_auth_user(
            email=args.email.lower(),
            password=args.password,
            metadata={
                'full_name': args.name,
                'role': 'super_admin',
                'admin_permissions': permissions,
            },
        )
        await supabase.upsert('profiles', {
            'id': user['id'],
            'full_name': args.name,
            'email': args.email.lower(),
            'role': 'super_admin',
            'status': 'active',
            'admin_permissions': permissions,
            'admin_2fa_enabled': False,
            'updated_at': datetime.now(UTC).isoformat(),
        }, 'id')
    except SupabaseClientError as exc:
        raise SystemExit(f'Could not create super admin: {exc}') from exc
    print(f'Super admin created: {args.email.lower()}')


if __name__ == '__main__':
    asyncio.run(main())
