# Client Change Implementation Checklist

Use this file as the master implementation tracker. Mark each item complete only after code is implemented and basic local checks pass.

## Phase 1 - Billing Gate And Trial Rules

- [x] Keep one 7-day free trial per parent email/account.
- [x] Limit the free trial to one child only.
- [x] Allow first eligible trial child to access learning features for 7 days.
- [x] Lock second/additional children unless they have an active paid subscription.
- [x] Guide parent to billing when selected child has no trial or paid access.
- [x] Prevent full learning/dashboard feature access when billing/trial rules are not satisfied.
- [x] Confirm "one month free" is shown only as annual plan discount, not as a second trial.

## Phase 2 - Child Subscription Selection And Checkout

- [x] After adding a child, immediately prompt for subscription options.
- [x] Show Text monthly plan: `$129/month`.
- [x] Show Text annual plan: `$1,419/year`, with one month free annual discount.
- [x] Support selecting plans for multiple children before checkout.
- [x] Create one checkout flow for all selected children if Stripe/current backend supports it.
- [x] Clearly display 5% family discount when 2+ children are included.
- [x] Prevent duplicate checkout/payment for a child with active access in the current subscription period.
- [x] Clearly show which children are active, trialing, paused, or unpaid.
- [x] Correct current period/expiration date display.

## Phase 3 - Pause, Resume, And Subscription State

- [x] Change pause behavior/copy so paid access pauses after current paid period ends.
- [x] Do not imply paid access stops immediately unless that is the actual behavior.
- [x] Show pending pause/cancel-at-period-end state clearly.
- [x] Prevent re-payment for the same child while the existing subscription period is active.
- [ ] Verify active subscription indicators after Stripe webhook sync.

## Phase 4 - Child Profile Selection And Locked PII

- [ ] Verify child selector updates content across dashboard.
- [ ] Verify child selector updates reports.
- [ ] Verify child selector updates billing.
- [x] Verify child selector updates child profile editing.
- [x] Fix incorrect student information showing during view/edit.
- [x] Lock student name after initial setup.
- [x] Lock student date of birth after initial setup.
- [x] Allow grade edits after setup.
- [x] Allow subject edits after setup.
- [x] Require deactivation + new profile for incorrect name/date of birth.
- [x] Do not provide admin/support override for locked PII.

## Phase 5 - Consent And Credential Notifications

- [x] Move parent consent collection to initial onboarding/signup fine print.
- [x] Remove post-setup consent requirements/steps.
- [x] Send parent email notification when student credentials are created.
- [x] Send parent email notification when student credentials are updated.
- [x] Do not include username or PIN in credential notification email.
- [x] Direct parent to dashboard to view/reset credentials.
- [x] Verify immediate signup welcome email still sends.
- [x] Verify immediate trial-start parent email still sends.

## Phase 6 - Parent And Student UI Cleanup

- [x] Remove or hide Future Modules from parent settings/sidebar.
- [x] Remove or hide Previous Chats from main student interface.
- [x] Make Deactivate less prominent or hidden.
- [x] Keep deactivation protected by confirmation if still available.
- [x] Update child login error copy to: `That username or PIN didn't work. Talk to your parent if you have trouble logging in.`

## Phase 6B - Manage Child Profiles Redesign

- [x] Redesign child profile list with child status and subscription/access summary.
- [x] Add selected child details panel.
- [x] Show locked identity fields clearly in details panel.
- [x] Show username/PIN management without exposing PIN.
- [x] Add child-specific Subscribe Now shortcut.
- [x] Add Pay for All Children shortcut.
- [x] Keep deactivation low prominence and confirmation-protected.

## Phase 7 - Session, Homework, And Assessment Fixes

- [x] Investigate active-use session expiration issue.
- [x] Prevent sessions from expiring while user is actively working.
- [x] Test/fix parent homework/photo upload.
- [x] Test/fix student homework/photo upload.
- [x] Disable Evaluate Assessment button after assessment completion.
- [x] Ensure retaking assessment shows new or changed questions.
- [x] Update assessment feedback to avoid praising incorrect answers.
- [x] Use neutral language for incorrect/weak responses, such as `Glad you completed it.`

## Phase 8 - Voice And Tutor Flow

- [x] Voice chat asks only one question at a time.
- [x] Tutor prompt avoids multiple open-ended questions at once.
- [x] Tutor starts from assessment results when available.
- [x] Tutor starts from assigned/uploaded homework when relevant.
- [x] Improve AI guidance so Ms. Alisia leads the activity.
- [x] Select a female, natural, less robotic voice from existing provider.
- [x] Implement automatic 5-second voice recording stop.
- [x] After auto-stop, prompt child warmly if they are still present.

## Phase 9 - Email Cron And Stripe Email Follow-Through

- [x] Immediate signup welcome email code queues and sends through Resend without blocking signup.
- [x] Immediate trial-start parent email code queues and sends through Resend without blocking trial start.
- [x] Fast cron endpoint exists: `/api/internal/email/process-due-fast`.
- [x] Credential-created email code queues and sends without exposing username or PIN.
- [x] Credential-updated email code queues and sends without exposing username or PIN.
- [x] Stripe `invoice.paid` webhook code queues and immediately attempts payment success email.
- [ ] Deploy immediate signup welcome email change.
- [ ] Deploy immediate trial-start parent email change.
- [ ] Update cron-job.org to use fast endpoint.
- [ ] Verify cron sends pending emails without timeout in production.
- [ ] Verify credential-created email sends in production.
- [ ] Verify credential-updated email sends in production.
- [ ] Verify Stripe `invoice.paid` creates/sends payment success email with current Stripe keys/webhook.

## Urgent Weekly Progress Email Fix

- [x] Replace plain weekly progress email with branded HTML email.
- [x] Add MsAlisia branded header and logo support.
- [x] Add safe logo fallback so email clients do not show a broken image if remote logo loading fails.
- [x] Display child first name prominently.
- [x] Render Math, Reading, and Writing as clean subject sections.
- [x] Remove raw semicolon/database-style subject highlights.
- [x] Send friendly engagement nudge when a child has zero sessions instead of `Session count: 0`.
- [x] Add one clear call-to-action button.
- [x] Point weekly report CTA to `/login?redirect=/reports` instead of the public landing page.
- [x] Frontend login honors safe parent redirects and opens Reports after login.
- [x] Add professional MsAlisia closing.
- [x] Add weekly-report sender support for `Francesca@msalisia.com`.
- [x] Locally verify weekly email sender setting resolves to `Francesca@msalisia.com`.
- [x] Locally verify weekly report CTA contains `login?redirect=%2Freports`.
- [ ] Verify `Francesca@msalisia.com` is approved/verified in Resend before production sending.
- [ ] Set/verify production `EMAIL_LOGO_URL` in Railway.
- [ ] Send a fresh deployed weekly email test and confirm logo/CTA behavior in Gmail.

## Phase 10 - Final Acceptance QA

- [ ] Run full parent signup flow.
- [ ] Run first-child free trial flow.
- [ ] Run second-child paid-only flow.
- [ ] Run multi-child checkout flow.
- [ ] Run active subscription and duplicate payment prevention tests.
- [ ] Run profile lock/edit tests.
- [ ] Run child login tests.
- [ ] Run homework upload tests.
- [ ] Run assessment retake tests.
- [ ] Run voice tests.
- [ ] Run email/cron tests.
- [ ] Collect final screenshots and logs for client proof.
