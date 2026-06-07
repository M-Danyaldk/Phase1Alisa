# Full Live QA Report - MsAlisia Client Fixes

Date: 2026-06-07  
Repo commit tested locally: `dad50ca Update email logo URL`  
Live QA update commit context: `a97f99b Add full live QA report`  
Branch: `main` / `origin/main`

## Executive Summary

Local build and static implementation QA passed for the main client fixes. Live API QA was also completed with a provided QA parent/student account.

Live Stripe test-mode checkout session creation passed for single-child monthly, single-child annual, four-child monthly, and four-child annual checkout. Student login, dashboard access, fresh session title cleanup, assessment saving, achievement unlock, parent report grade/practice-focus display, and public route reachability also passed.

Two important issues remain: weekly email preview/recommended next steps can still contain raw markdown/prompt-style text, and full dashboard-provider verification for Railway/Supabase/Stripe/Resend still requires private dashboard access.

## Environment Tested

- Local backend compile: `PASS`
- Local frontend production build: `PASS`
- GitHub latest `origin/main`: `dad50ca752869c5fcbb8507490cd9083b0101352`
- Public site reachability:
  - `https://www.msalisia.com/`: `200 OK`
  - `https://www.msalisia.com/login`: `200 OK`
  - `https://www.msalisia.com/student?family=qa-check`: `200 OK`
  - `https://www.msalisia.com/logo.jpeg?v=20260606`: `200 OK`
- Deployment freshness:
  - Public frontend bundle: `/assets/index-Dwfe0m7i.js`
  - Local latest build bundle: `/assets/index-CovSO7yB.js`
  - Status: `Partially confirmed`; deployed bundle contains the expected fixed UI strings, but dashboard deploy metadata is still needed for exact commit proof.
- Production API base tested: `https://msalisia-platform-production.up.railway.app`
- QA account shape:
  - Parent login: `PASS`
  - Active children found: 4
  - Temporary checkout children created for test: 4
  - Temporary checkout children deactivated after test: 4

## Completed / Passed Items

| Area | Result | Evidence |
|---|---:|---|
| Backend compile | Pass | `python -m compileall app` completed successfully. |
| Frontend build | Pass | `npm run build` completed successfully. |
| GitHub push state | Pass | `origin/main` points to `dad50ca`. |
| Public site reachable | Pass | Main, login, student route, and cache-busted logo URL return `200 OK`. |
| Production API health | Pass | `/health` returned `status: ok`, primary LLM `claude`, fallback `groq`. |
| Parent login live | Pass | QA parent login succeeded. |
| Billing status live | Pass | Billing status loaded; family discount status returned `eligible`, coupon configured `true`, discount `5%`. |
| Logo URL update | Pass | `.env.example` contains `EMAIL_LOGO_URL=https://www.msalisia.com/logo.jpeg?v=20260606`; public URL returns `200 OK`. |
| Bulk checkout grouping | Pass | Four monthly children group into one Stripe line item with `quantity: 4`; mixed plans create separate line items. |
| Stripe plans live | Pass | Four plans loaded; text monthly `$129/month`, text annual `$1,419/year`, voice monthly, and voice annual all have Stripe prices configured. |
| Active duplicate checkout prevention live | Pass | Active child checkout returned `This child already has an active paid subscription for the current billing period.` |
| Single-child monthly checkout live | Pass | Temporary inactive QA child produced Stripe test checkout session on `checkout.stripe.com`. |
| Single-child annual checkout live | Pass | Temporary inactive QA child produced Stripe test checkout session on `checkout.stripe.com`. |
| Four-child monthly checkout live | Pass | Four temporary inactive QA children produced Stripe test checkout session on `checkout.stripe.com`. |
| Four-child annual checkout live | Pass | Four temporary inactive QA children produced Stripe test checkout session on `checkout.stripe.com`. |
| Checkout failure handling | Pass by source verification | Backend wraps Stripe checkout creation with `503` user-safe error; frontend renders `checkoutError`. |
| Parent login first click | Pass by source verification | Login form uses real `onSubmit` form flow and submit button. |
| Classroom link clean login | Pass by source verification | Student route with `family=` clears stored student session before rendering login. |
| Friendly student login error | Pass by source verification | Exact copy exists in backend and frontend. |
| Friendly student login error live | Pass | Invalid student login returned the exact child-friendly helper message. |
| Valid student login live | Pass | Provided student credentials logged in and `/student/me` returned access allowed. |
| Student home child-friendly heading | Pass by source verification | Home renders `Hi, [First Name]!` and `Ready to learn today?`. |
| Removed student labels | Pass by source verification | No source matches for visible `STUDENT DASHBOARD`, `SELECTED STUDENT`, `Back to Dashboard`, or `Try a New Check-in`. |
| `practice-ela` visible text | Pass by source verification | `practice-ela` appears only as internal route/view key; visible label is `Practice Reading`. |
| Assessment scroll to results | Pass by source verification | Assessment result ref calls `scrollIntoView`. |
| Assessment Back to Home | Pass by source verification | Assessment, result panel, practice chat, and homework student screens show `Back to Home`. |
| Continue Learning routing | Pass by source verification | Assessment result passes subject/focus to Math, Reading, or Writing practice route. |
| Chat input starts empty | Pass by source verification | Learning input initializes to `''` and resets on new/opened sessions. |
| Student context panel hidden | Pass by source verification | `LearningContextPanel` is rendered only when not in student session mode. |
| Proactive tutor opener | Pass by source verification | Math, Reading, and Writing greetings include a first activity/question. |
| Voice auto-stop timing | Pass by source verification | `VOICE_AUTO_STOP_MS = 2000`. |
| Raw/broken session topic cleanup | Pass for tested values | `9)` becomes `multiplication facts`; `I need help understanding this.` becomes `reading vocabulary`; generated title is `Reading Practice - reading vocabulary`. |
| Fresh raw session cleanup live | Pass | Fresh student chat with topic `9)` and message `I need help understanding this.` resolved to `multiplication facts`; thread title became `Math Practice - multiplication facts`; dashboard activity detail became `Continue practicing multiplication facts with a short session.` |
| Report child deep link | Pass by source verification | Weekly email metadata includes `child_id`; frontend reads `child_id` from direct or redirect query. |
| Grade/practice focus split | Pass live | Parent report shows `Grade 5 - practice focus: ...`, with enrolled grade `Grade 5` and working level separated. |
| Achievement unlock logic | Pass live | After a live Math assessment, `First Assessment` changed to `earned`; `First Learning Session` was already `earned`. |
| Assessment saving live | Pass | Live Math assessment returned result and recommended next topic. |
| Cron protection | Pass | Calling cron endpoint without secret returned `403 Internal endpoint access denied`, as expected. |

## Failed Items

| Area | Result | Evidence / Risk |
|---|---:|---|
| Latest public deployment confirmation | Fail / Needs redeploy check | Public frontend bundle hash differs from local latest build bundle. The public app may not yet be running `dad50ca`. |
| Local backend `.env` email-logo alignment | Fail locally | Local `backend/.env` reports `EMAIL_LOGO_URL=MISSING`; `.env.example` is correct. Railway must be checked separately. |
| Local parent-facing sender alignment | Fail locally | Local `backend/.env` reports `RESEND_FROM_EMAIL=enrol@msalisia.com`; `.env.example` is correct with `francesca@msalisia.com`. Railway must be checked separately. |
| Local voice provider readiness | Fail locally | Local `backend/.env` has `OPENAI_API_KEY=MISSING` and `DEEPGRAM_API_KEY=MISSING`, so local live voice processing cannot be validated. |
| Prompt-like topic text hardening | Potential fail | Direct resolver probe returned `Or would you like to practice writing sentences?` as a topic. Dashboard actions are clean, but topic resolver should reject `would you like` prompt fragments too. |
| Weekly email preview raw prompt text | Fail live | Live weekly preview `recommended_next_steps` included raw markdown/prompt-style text: `** Is it a specific multiplication problem, or something else in math?` |
| Historical raw session title remains visible | Fail for existing data only | Older stored session title `Give me one example.` still appears in report/dashboard history. Fresh sessions are now cleaned, but historical records are not backfilled. |

## Blocked Items

These require account/dashboard access or real test users and could not be fully executed from the local workspace alone.

| Area | Status | Needed Access |
|---|---:|---|
| Railway env verification by name | Blocked | Railway dashboard or Railway CLI authenticated to the project. |
| Confirm latest commit deployed | Blocked | Deployment dashboard/logs or deploy metadata endpoint. |
| Inspect Stripe checkout line items inside Stripe dashboard | Blocked | Stripe dashboard access. API confirmed checkout sessions were created, but dashboard inspection is still needed for line-item/coupon proof screenshots. |
| Family discount coupon behavior in Stripe dashboard | Blocked | Stripe coupon config and checkout session inspection. API confirms family discount eligible/configured. |
| 7-day free trial production behavior for a new email | Blocked | Fresh production test parent email and Supabase access. Current QA account has already used trial history. |
| Voice end-to-end test | Blocked | Valid student login, voice-enabled plan, and voice API keys. |
| Email delivery tests | Blocked | Resend access and production/test recipient. |
| Cron endpoint authenticated test | Blocked | `INTERNAL_CRON_SECRET`; unauthenticated rejection was verified. |
| Stripe webhook `200 OK` and payment success email | Blocked | Stripe webhook test event access and Railway logs. |
| Supabase proof screenshots/queries | Blocked | Supabase dashboard or service-role access policy approval. |
| Required screenshots/recordings | Blocked | Authenticated test accounts and browser recording workflow. |

## Needs Live Confirmation

- Public deployment metadata should be checked in the hosting dashboard; public bundle contains expected strings but exact commit proof still needs deploy metadata.
- Railway should contain:
  - `RESEND_FROM_EMAIL=francesca@msalisia.com`
  - `WEEKLY_PROGRESS_FROM_EMAIL=francesca@msalisia.com`
  - `EMAIL_LOGO_URL=https://www.msalisia.com/logo.jpeg?v=20260606`
  - `APP_PUBLIC_URL=https://www.msalisia.com`
  - Stripe, Supabase, Resend, OpenAI/voice, and Deepgram keys as needed.
- Stripe checkout should be tested in test mode before any live-payment confirmation.
- Resend must confirm sender/domain approval for `francesca@msalisia.com`.
- Supabase data should be checked for trial history, child access, session activity, assessment results, achievements, email events, and billing subscription records.

## Screenshots / Recordings Collected

No screenshots or recordings were collected in this workspace run. Public route status checks, API responses, Stripe test checkout-session creation results, and source/build verification were collected via terminal output only.

Live QA evidence collected:

- Parent login succeeded.
- Student invalid login returned exact helper copy.
- Student valid login succeeded.
- Billing plans and family discount status loaded.
- Active child duplicate checkout was blocked.
- Single monthly, single annual, four-child monthly, and four-child annual Stripe test checkout sessions were created.
- Temporary checkout QA children were deactivated after testing.
- Fresh raw-topic chat session saved clean title/topic/activity.
- Live Math assessment saved and unlocked First Assessment achievement.
- Parent report showed enrolled Grade 5 and practice focus separately.
- Weekly preview still exposed raw markdown/prompt-style text.

Required evidence still to collect:

- Billing plan and multi-child checkout screenshots.
- Stripe checkout page screenshots for monthly and annual single/multi-child flows.
- Student login, student home, practice session, assessment result, homework, and reports screenshots.
- Branded weekly progress and student credential email screenshots.
- Short recordings for parent signup, first-child trial, second-child paid-only path, child login, assessment, voice, and checkout.
- Railway, Stripe, Supabase, and Resend proof screenshots with secrets hidden.

## Recommended Fixes Before Client Approval

1. Fix weekly email/report recommendation cleanup so raw markdown/prompt fragments cannot appear in `recommended_next_steps`.
2. Backfill or mask historical raw session titles such as `Give me one example.` in dashboard/report history.
3. Verify Railway env values for `EMAIL_LOGO_URL`, `RESEND_FROM_EMAIL`, `APP_PUBLIC_URL`, OpenAI, and Deepgram.
4. Inspect created Stripe test checkout sessions in Stripe dashboard for line items, coupon/discount application, and invoice/webhook behavior.
5. Run a browser-based screenshot/recording pass before final client approval.
