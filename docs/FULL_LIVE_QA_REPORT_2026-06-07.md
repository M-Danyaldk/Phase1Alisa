# Full Live QA Report - MsAlisia Client Fixes

Date: 2026-06-07  
Repo commit tested locally: `dad50ca Update email logo URL`  
Branch: `main` / `origin/main`

## Executive Summary

Local build and static implementation QA passed for the main client fixes: checkout session grouping/error handling, student login reset, student home cleanup, assessment navigation, tutoring session cleanup, and email/report deep-link code paths.

Full live acceptance QA is not complete because private production access is required for Railway, Supabase, Stripe, Resend, and real test accounts. The public site is reachable, but the deployed frontend bundle does not match the latest local production build hash, so the latest commit cannot be confirmed as deployed from public checks alone.

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
  - Status: `Needs Live Confirmation`

## Completed / Passed Items

| Area | Result | Evidence |
|---|---:|---|
| Backend compile | Pass | `python -m compileall app` completed successfully. |
| Frontend build | Pass | `npm run build` completed successfully. |
| GitHub push state | Pass | `origin/main` points to `dad50ca`. |
| Public site reachable | Pass | Main, login, student route, and cache-busted logo URL return `200 OK`. |
| Logo URL update | Pass | `.env.example` contains `EMAIL_LOGO_URL=https://www.msalisia.com/logo.jpeg?v=20260606`; public URL returns `200 OK`. |
| Bulk checkout grouping | Pass | Four monthly children group into one Stripe line item with `quantity: 4`; mixed plans create separate line items. |
| Checkout failure handling | Pass by source verification | Backend wraps Stripe checkout creation with `503` user-safe error; frontend renders `checkoutError`. |
| Parent login first click | Pass by source verification | Login form uses real `onSubmit` form flow and submit button. |
| Classroom link clean login | Pass by source verification | Student route with `family=` clears stored student session before rendering login. |
| Friendly student login error | Pass by source verification | Exact copy exists in backend and frontend. |
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
| Report child deep link | Pass by source verification | Weekly email metadata includes `child_id`; frontend reads `child_id` from direct or redirect query. |
| Grade/practice focus split | Pass by source verification | Code preserves enrolled grade and separately labels assessed practice focus. |
| Achievement unlock logic | Pass by source verification | Dashboard service counts assessments and learning sessions/activity across relevant tables. |

## Failed Items

| Area | Result | Evidence / Risk |
|---|---:|---|
| Latest public deployment confirmation | Fail / Needs redeploy check | Public frontend bundle hash differs from local latest build bundle. The public app may not yet be running `dad50ca`. |
| Local backend `.env` email-logo alignment | Fail locally | Local `backend/.env` reports `EMAIL_LOGO_URL=MISSING`; `.env.example` is correct. Railway must be checked separately. |
| Local parent-facing sender alignment | Fail locally | Local `backend/.env` reports `RESEND_FROM_EMAIL=enrol@msalisia.com`; `.env.example` is correct with `francesca@msalisia.com`. Railway must be checked separately. |
| Local voice provider readiness | Fail locally | Local `backend/.env` has `OPENAI_API_KEY=MISSING` and `DEEPGRAM_API_KEY=MISSING`, so local live voice processing cannot be validated. |
| Prompt-like topic text hardening | Potential fail | Direct resolver probe returned `Or would you like to practice writing sentences?` as a topic. Dashboard actions are clean, but topic resolver should reject `would you like` prompt fragments too. |

## Blocked Items

These require account/dashboard access or real test users and could not be fully executed from the local workspace alone.

| Area | Status | Needed Access |
|---|---:|---|
| Railway env verification by name | Blocked | Railway dashboard or Railway CLI authenticated to the project. |
| Confirm latest commit deployed | Blocked | Deployment dashboard/logs or deploy metadata endpoint. |
| Stripe single-child monthly checkout redirect | Blocked | Test parent account and Stripe test/live dashboard access. |
| Stripe single-child annual checkout redirect | Blocked | Test parent account and Stripe test/live dashboard access. |
| Stripe 4-child monthly checkout redirect | Blocked | Test parent with four unpaid children and Stripe access. |
| Stripe 4-child annual checkout redirect | Blocked | Test parent with four unpaid children and Stripe access. |
| Family discount coupon behavior in Stripe | Blocked | Stripe coupon config and checkout session inspection. |
| 7-day free trial production behavior | Blocked | Production test parent/children and Supabase access. |
| Active/trial child duplicate payment prevention live check | Blocked | Production test parent and Stripe/Supabase access. |
| Student login with real credentials | Blocked | Valid family classroom link, username, and PIN. |
| Full student practice session live QA | Blocked | Valid student login and active trial/paid access. |
| Voice end-to-end test | Blocked | Valid student login, voice-enabled plan, and voice API keys. |
| Email delivery tests | Blocked | Resend access and production/test recipient. |
| Cron endpoint test | Blocked | `INTERNAL_CRON_SECRET` and deployed backend URL. |
| Stripe webhook `200 OK` and payment success email | Blocked | Stripe webhook test event access and Railway logs. |
| Supabase proof screenshots/queries | Blocked | Supabase dashboard or service-role access policy approval. |
| Required screenshots/recordings | Blocked | Authenticated test accounts and browser recording workflow. |

## Needs Live Confirmation

- Public deployment must be redeployed or verified so `dad50ca` is live.
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

No screenshots or recordings were collected in this workspace run. Public route status checks and source/build verification were collected via terminal output only.

Required evidence still to collect:

- Billing plan and multi-child checkout screenshots.
- Stripe checkout page screenshots for monthly and annual single/multi-child flows.
- Student login, student home, practice session, assessment result, homework, and reports screenshots.
- Branded weekly progress and student credential email screenshots.
- Short recordings for parent signup, first-child trial, second-child paid-only path, child login, assessment, voice, and checkout.
- Railway, Stripe, Supabase, and Resend proof screenshots with secrets hidden.

## Recommended Fixes Before Client Approval

1. Redeploy production and verify the public frontend bundle corresponds to the latest GitHub commit.
2. Set/verify Railway env values for `EMAIL_LOGO_URL`, `RESEND_FROM_EMAIL`, `APP_PUBLIC_URL`, OpenAI, and Deepgram.
3. Harden topic cleanup to reject prompt fragments containing phrases like `would you like` before any topic/title storage.
4. Run Stripe checkout in test mode for single-child and 4-child monthly/annual flows.
5. Run a full authenticated regression pass with screenshots/recordings before sending final client approval.
