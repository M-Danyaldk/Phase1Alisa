# Client Change Phase Testing README

Use this file during QA after each implementation phase. Each phase should be tested before it is marked complete in `docs/CLIENT_CHANGE_IMPLEMENTATION_CHECKLIST.md`.

Do not mark a phase complete only because the code builds. Mark it complete after the required screens, API behavior, and screenshots are verified.

## Testing Rules

- Test with at least one parent account that has one child.
- Test with at least one parent account that has two children.
- Test first-child trial behavior and second-child paid-only behavior.
- Test both local and deployed environments when the phase affects production behavior.
- Do not expose passwords, child PINs, API keys, Stripe secrets, cron secrets, or service-role keys in screenshots.
- Blur or crop private emails if screenshots are sent outside the internal team.

## Phase 1 - Billing Gate And Trial Rules

Required proof:

- Screenshot: first eligible child can access learning during the 7-day trial.
- Screenshot: second child under same parent is locked if unpaid.
- Screenshot: locked child is guided to billing instead of full learning features.
- Screenshot: annual "one month free" language is shown only as annual discount, not as another trial.
- Backend proof: child access status shows only one trial child per parent email/account.

Pass condition:

- Parent cannot use full features for an unpaid child unless that child has the one allowed trial or an active paid subscription.

## Phase 2 - Child Subscription Selection And Checkout

Required proof:

- Screenshot: after adding a child, parent sees plan selection.
- Screenshot: Text Monthly shows `$129/month`.
- Screenshot: Text Annual shows `$1,419/year` and one-month-free annual discount.
- Screenshot: parent can select plans for multiple children before checkout.
- Screenshot: family discount appears when 2+ children are selected.
- Screenshot: Stripe checkout opens with the expected selected children/plans.
- Screenshot: active child cannot be paid again for the same active period.

Pass condition:

- Parent has a clear path from child setup to payment, and duplicate payment for the same child is blocked.

## Phase 3 - Pause, Resume, And Subscription State

Required proof:

- Screenshot: active child shows current paid period.
- Screenshot: pause copy says access pauses after the current paid period ends.
- Screenshot: after pause request, state shows pending pause/cancel-at-period-end.
- Screenshot: resume action is available when pause is pending or paused.
- Backend proof: current period end and subscription status match Stripe.

Pass condition:

- Parent understands access remains active until the paid period ends, and the UI matches backend/Stripe state.

## Phase 4 - Child Profile Selection And Locked PII

Required proof:

- Screenshot: switching child on dashboard updates all child-specific content.
- Screenshot: switching child on reports updates report content.
- Screenshot: switching child on billing updates billing/subscription content.
- Screenshot: edit profile screen shows correct selected child.
- Screenshot: name is locked after profile creation.
- Screenshot: date of birth is locked after profile creation.
- Screenshot: grade can still be edited.
- Screenshot: subjects can still be edited.
- Screenshot: deactivation/new-profile path is available for incorrect PII.

Pass condition:

- Child-specific UI never shows stale or wrong-child data, and fixed PII cannot be edited after setup.

## Phase 5 - Consent And Credential Notifications

Required proof:

- Screenshot: consent appears during initial onboarding/signup fine print.
- Screenshot: no post-setup pending-consent step blocks normal profile use.
- Email proof: credential-created email received by parent.
- Email proof: credential-updated email received by parent.
- Email proof: credential email does not include username or PIN.
- Backend proof: email event/log created for credential-created and credential-updated.
- Email proof: signup welcome still sends.
- Email proof: trial-start parent email still sends.

Pass condition:

- Consent is collected up front, and credential emails notify safely without exposing credentials.

## Phase 6 - Parent And Student UI Cleanup

Required proof:

- Screenshot: Future Modules is hidden from parent settings/sidebar.
- Screenshot: Previous Chats is hidden from the main student interface.
- Screenshot: Deactivate is small/secondary or hidden.
- Screenshot: if deactivation remains available, confirmation appears before action.
- Screenshot: wrong student login shows friendly copy: `That username or PIN didn't work. Talk to your parent if you have trouble logging in.`

Pass condition:

- Parent/student UI is launch-clean and avoids prominent risky actions or distracting old chat surfaces.

## Phase 6B - Manage Child Profiles Redesign

Required proof:

- Screenshot: child list shows each child with profile status and subscription/access summary.
- Screenshot: selected child details panel updates when a different child is selected.
- Screenshot: name and date of birth are clearly locked.
- Screenshot: username is visible but PIN is masked or reset-only.
- Screenshot: child needing payment has Subscribe Now shortcut.
- Screenshot: multi-child payment shortcut is available.
- Screenshot: Deactivate is hidden from the main Manage Child Profiles cards/details, or if surfaced elsewhere, remains low prominence and confirmation-protected.

Pass condition:

- Parent can clearly understand each child's profile, access, and billing state without exposing sensitive credentials or making risky actions too prominent.

## Phase 7 - Session, Homework, And Assessment Fixes

Required proof:

- Screen recording: active session does not expire while the user is working.
- Screenshot: parent homework/photo upload is available.
- Screenshot: student homework/photo upload is available.
- Screenshot: after upload analysis, follow-up input appears when needed.
- Screenshot: Evaluate Assessment button is disabled after completion.
- Screenshot: retaking assessment shows new or changed questions.
- Screenshot: incorrect assessment answer does not receive overpraise.
- Screenshot: incorrect/weak answer uses supportive neutral language.

Pass condition:

- Homework and assessment flows continue smoothly and stay child-safe.

## Phase 8 - Voice And Tutor Flow

Required proof:

- Screen recording: voice asks one question at a time.
- Screen recording: voice does not ask multiple open-ended questions at once.
- Screen recording: selected voice sounds female, natural, and child-appropriate.
- Screen recording: recording auto-stops around 5 seconds.
- Screenshot or recording: after auto-stop, child receives a warm still-present prompt.
- Tutor proof: tutor starts from assessment results when available.
- Tutor proof: tutor starts from homework when relevant.

Pass condition:

- Ms. Alisia leads the child gently, one step at a time, with a natural voice and controlled recording behavior.

## Phase 9 - Email Cron And Stripe Email Follow-Through

Required proof:

- Screenshot: Railway has required email env keys present by name only.
- Screenshot: Railway has `EMAIL_LOGO_URL` set to a public HTTPS logo URL, or confirm the branded fallback mark is acceptable.
- Screenshot: cron-job.org points to `/api/internal/email/process-due-fast`.
- Screenshot: cron-job.org request method is POST.
- Screenshot: cron-job.org has `x-internal-cron-secret` header configured without exposing the value.
- Screenshot: cron test run returns `200 OK`.
- Screenshot: cron history shows successful scheduled runs.
- Backend proof: pending due emails are processed without timeout. A `processed: 0` response is acceptable when no due email events are pending.
- Email proof: weekly progress email shows branded HTML design with no broken logo image.
- Email proof: weekly progress CTA opens `/login?redirect=/reports` and lands on Reports after login.
- Email proof: payment success email sends after Stripe webhook.
- Email proof: credential-created and credential-updated emails send.

Pass condition:

- Immediate emails send during core flows, and cron reliably processes scheduled/backlog emails.

## Phase 10 - Final Acceptance QA

Required proof:

- Full parent signup recording.
- First-child trial recording.
- Second-child paid-only recording.
- Multi-child checkout recording.
- Active subscription and duplicate-payment prevention recording.
- Profile locked-PII recording.
- Child login recording.
- Homework parent/student upload recording.
- Assessment completion/retake recording.
- Voice recording test.
- Email and cron proof screenshots.
- Stripe webhook success screenshot.
- Supabase verification query screenshots for key tables.

Pass condition:

- All client-critical flows work in deployed environment and have screenshot/recording proof ready for review.
