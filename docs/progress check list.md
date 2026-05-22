# Progress Check List

## Admin Dashboard Setup

### Done

- [x] Frontend has a dedicated admin route at `/admin`.
- [x] Frontend renders a protected admin access screen through `AdminView`.
- [x] Admin access code is stored in browser `sessionStorage` after entry.
- [x] Frontend sends the authenticated user token to the backend using the `Authorization: Bearer` header.
- [x] Backend has an admin API endpoint at `/api/admin/overview`.
- [x] Backend validates the admin access code before returning admin data.
- [x] Admin overview can return recent students, recent assessments, and recent LLM events.
- [x] Old admin access token environment variables were removed.
- [x] Supabase `profiles` table supports a `role` column with `admin` as an allowed value.
- [x] Backend admin routes use authenticated bearer tokens instead of a shared admin code.
- [x] Backend checks admin role and required permissions for `/api/admin/*` routes.
- [x] Admin audit log table and app settings table migration added.
- [x] Frontend admin console uses logged-in admin session.
- [x] First super admin seed script added.

### Pending

- [x] Replace shared admin access code with role-based admin login.
- [x] Use the normal login flow to identify admin users by `profiles.role = 'admin'`.
- [x] Redirect admin users to `/admin/dashboard` after login.
- [x] Protect `/api/admin/*` endpoints using authenticated bearer tokens.
- [x] Add backend checks for admin role on every admin API request.
- [x] Add permissions for admin actions, such as:
  - `manage_users`
  - `manage_subscriptions`
  - `manage_courses`
  - `view_analytics`
  - `refund_payments`
  - `manage_admins`
- [x] Add an admin account creation flow.
- [x] Seed the first super admin through code or create it manually in the database.
- [x] Add audit logging for admin actions.
- [ ] Add shorter admin session expiry in Supabase production auth settings.
- [ ] Add a complete 2FA challenge/setup flow for admin accounts.
- [x] Add rate limiting and lockout rules for admin login attempts.
- [x] Add a proper admin dashboard route structure, such as:
  - `/admin/dashboard`
  - `/admin/users`
  - `/admin/subscriptions`
  - `/admin/reports`
  - `/admin/settings`
- [x] Add admin APIs for subscriptions, users, reports, content, and settings.
- [ ] Add automated tests for admin access success and forbidden access.

### Current Security Status

- [x] Backend does enforce the current admin access code.
- [x] Admin access is tied to a real admin user account.
- [x] Admin access is tied to database roles and permissions.
- [x] Admin actions are recorded in audit logs for implemented mutation routes.
- [x] The old access-code approach has been removed from frontend/backend configuration.

### Recommended Final Design

- [x] Use one shared login page.
- [x] Store user roles and permissions in the database.
- [x] Redirect admins to a separate admin dashboard after login.
- [x] Keep admin frontend routes separate from parent/student routes.
- [x] Keep admin backend routes under `/api/admin/*`.
- [x] Enforce all admin authorization on the backend.
- [x] Do not rely on hidden admin URLs for security.

## Notes

The current project now has a role-based admin system with protected backend routes. Remaining production hardening work is mainly Supabase session policy configuration, a full admin 2FA setup/challenge flow, and automated tests.
