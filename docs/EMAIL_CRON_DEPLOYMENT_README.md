# MsAlisia Email + Cron Deployment Checklist

Use this checklist after deploying the latest backend code. It covers immediate emails and the fast cron endpoint for generating, retrying, and sending scheduled emails.

## 1. Deploy Backend

Deploy the latest code to Railway first.

The new backend route will not exist until this deployment is live:

```text
POST /api/internal/email/process-due-fast
```

## 2. Confirm Railway Environment Variables

In the Railway backend service, confirm these variables exist:

```text
RESEND_API_KEY
RESEND_FROM_EMAIL
WAITLIST_NOTIFY_EMAIL
APP_PUBLIC_URL
INTERNAL_CRON_SECRET
```

Do not add these to frontend/Vercel.

## 3. Supabase Migrations

Run any pending Supabase migrations before final QA.

Current important migrations from this work:

```text
supabase/migrations/require_child_access_for_learning.sql
supabase/migrations/harden_billing_discount_boolean_defaults.sql
```

No new migration is required for the immediate email/fast cron change.

## 4. Manual Test: Fast Cron Endpoint

After Railway deploy finishes, run this in PowerShell:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://msalisia-platform-production.up.railway.app/api/internal/email/process-due-fast" `
  -Headers @{ "x-internal-cron-secret" = "PASTE_INTERNAL_CRON_SECRET_HERE" }
```

Expected response:

```text
processed : 0 or more
sent      : 0 or more
failed    : 0
skipped   : 0
```

If you get `403`, the cron secret/header is wrong.

If you get `404`, the backend deploy is not live yet or the URL is wrong.

If you get `405`, the request method is not POST.

## 5. cron-job.org Setup

Edit or create the cron job:

Title:

```text
MsAlisia Email Processor
```

URL:

```text
https://msalisia-platform-production.up.railway.app/api/internal/email/process-due-fast
```

Schedule:

```text
Every 15 minutes
```

Advanced settings:

```text
Request method: POST
Request body: empty
Timeout: 30 seconds
HTTP authentication: off
```

Custom header:

```text
x-internal-cron-secret: PASTE_INTERNAL_CRON_SECRET_HERE
```

Click **Test Run**.

Successful Railway log should show:

```text
POST /api/internal/email/process-due-fast HTTP/1.1" 200 OK
```

## 6. Full Processor

The old endpoint still exists:

```text
POST /api/internal/email/process-due
```

Use it manually when you want to process a larger batch of due email events.

The fast endpoint is still preferred for cron-job.org because it uses a smaller delivery batch.

## 7. What Sends Immediately Now

After this deploy:

```text
Signup welcome email
Trial started parent email
```

These are queued and immediately attempted through Resend.

If Resend fails, signup/trial still continues, and the issue is logged.

## 8. What Still Needs Cron

These scheduled/fallback emails are generated and delivered by the cron job:

```text
trial day 5 reminder
trial ends tomorrow reminder (Day 6)
trial expired day 8 email
weekly progress emails
annual renewal reminder
pending email retries
```

New trials have their Day 5, Day 6, and Day 8 reminders queued immediately. The fast processor also generates missing recovery events, up to five missing weekly reports per run, and annual reminders before sending its batch. Failed deliveries are retried up to three total attempts.

## 9. Stripe Payment Success Email

Payment success email depends on Stripe webhook first.

Required Stripe webhook event:

```text
invoice.paid
```

If no `payment_success` row appears in `email_events`, check Stripe webhook delivery and Railway logs.

The fast cron can send a `payment_success` email only after the event exists.

## 10. Supabase Verification Queries

Check recent email events:

```sql
select
  trigger_type,
  recipient_email,
  status,
  sent_at,
  created_at,
  updated_at
from public.email_events
order by updated_at desc
limit 30;
```

Check delivery logs:

```sql
select
  recipient_email,
  trigger_type,
  provider,
  provider_message_id,
  status,
  error_message,
  created_at
from public.email_delivery_logs
order by created_at desc
limit 30;
```

Check payment success events:

```sql
select
  id,
  trigger_type,
  recipient_email,
  status,
  metadata,
  scheduled_send_at,
  sent_at,
  created_at,
  updated_at
from public.email_events
where trigger_type = 'payment_success'
order by created_at desc
limit 20;
```

## 11. Security Note

If the `INTERNAL_CRON_SECRET` was pasted into chat, screenshots, logs, or shared docs, rotate it in Railway after setup.

After rotating it, update the cron-job.org header value with the new secret.
