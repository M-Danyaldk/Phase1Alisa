import { useEffect, useState } from 'react';
import { Clock, CreditCard, Users } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { createCheckoutSession, createCustomerPortalSession, listBillingPlans, listChildAccess, updateChildAccess } from '../lib/api/billing';
import { BillingPlan, BillingPlanKey, ChildAccess, ChildAccessStatus } from '../types/billing';

export function BillingView({ accessToken = '' }: { accessToken?: string }) {
  const [records, setRecords] = useState<ChildAccess[]>([]);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingChildId, setSavingChildId] = useState('');
  const [checkoutKey, setCheckoutKey] = useState('');
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function load() {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      const [childRecords, billingPlans] = await Promise.all([
        listChildAccess(accessToken),
        listBillingPlans(),
      ]);
      setRecords(childRecords);
      setPlans(billingPlans);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'Could not load child billing access.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [accessToken]);

  async function changeStatus(childId: string, status: ChildAccessStatus) {
    setSavingChildId(childId);
    setError('');
    setMessage('');
    try {
      const updated = await updateChildAccess(accessToken, childId, status);
      setRecords(records.map(record => record.child_id === childId ? updated : record));
      setMessage(`${updated.child_name} is now marked ${labelForStatus(updated.access_status)}.`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not update child access.');
    } finally {
      setSavingChildId('');
    }
  }

  async function beginCheckout(childId: string, planKey: BillingPlanKey) {
    setCheckoutKey(`${childId}:${planKey}`);
    setError('');
    setMessage('');
    try {
      window.location.href = await createCheckoutSession(accessToken, childId, planKey);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not start Stripe checkout.');
      setCheckoutKey('');
    }
  }

  async function openPortal() {
    setPortalLoading(true);
    setError('');
    setMessage('');
    try {
      window.location.href = await createCustomerPortalSession(accessToken);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not open Stripe billing portal.');
      setPortalLoading(false);
    }
  }

  const activeCount = records.filter(record => record.access_status === 'active' || record.access_status === 'trial').length;

  return <div className="page-stack">
    <SectionHeader eyebrow="Billing and access" title="Subscription access by child" desc="Each child has a separate access record, so one parent account can manage multiple children without mixing subscriptions or learning data." />

    {message && <p className="success-note">{message}</p>}
    {error && <p className="error-note">{error}</p>}

    <div className="card-grid three">
      <InfoCard icon={<Users />} title="Children Covered" desc={`${activeCount} of ${records.length} child profile(s) currently have trial or active access.`} />
      <InfoCard icon={<CreditCard />} title="Stripe Status" desc="Checkout is connected through the backend. Stripe webhooks will activate access in the next billing step." />
      <InfoCard icon={<Clock />} title="Trial Rule" desc="Each parent email can use one 7-day free trial." />
    </div>

    <div className="pricing-card">
      <h3>MsAlisia Plans</h3>
      <p>Chat starts at $129/month. Chat + Audio starts at $159/month. Annual plans include 1 month free.</p>
      <button className="secondary-button compact" onClick={openPortal} disabled={portalLoading || !records.length}>{portalLoading ? 'Opening...' : 'Manage Payment Method'}</button>
    </div>

    <div className="billing-list">
      {loading && <p className="muted-copy">Loading child access...</p>}
      {!loading && !records.length && <p className="muted-copy">No child profiles found. Add a child profile first.</p>}
      {records.map(record => <div className="billing-child-card" key={record.child_id}>
        <div>
          <span className={`access-status ${record.access_status}`}>{labelForStatus(record.access_status)}</span>
          <h3>{record.child_name}</h3>
          <p>{record.grade_level} - {record.plan_name}</p>
          <p>{periodText(record)}</p>
        </div>
        <div className="billing-actions">
          <button className="secondary-button compact" onClick={() => changeStatus(record.child_id, 'trial')} disabled={savingChildId === record.child_id}>Start Trial</button>
          <button className="secondary-button compact danger" onClick={() => changeStatus(record.child_id, 'inactive')} disabled={savingChildId === record.child_id}>Pause Access</button>
        </div>
        <div className="billing-actions">
          {plans.map(plan => {
            const key = `${record.child_id}:${plan.plan_key}`;
            return <button
              className="secondary-button compact"
              key={plan.plan_key}
              onClick={() => beginCheckout(record.child_id, plan.plan_key)}
              disabled={!plan.stripe_price_configured || checkoutKey === key}
              title={plan.stripe_price_configured ? plan.display_name : `${plan.stripe_price_env} is not configured`}
            >
              {checkoutKey === key ? 'Opening...' : planButtonText(plan)}
            </button>;
          })}
        </div>
      </div>)}
    </div>

    <div className="report-card">
      <h3>How this connects subscriptions to children</h3>
      <p>Each Stripe Checkout session includes the selected child profile ID. In the next billing step, Stripe webhooks should update the matching child access row after payment succeeds.</p>
      <ul>
        <li>Parent owns the payment account.</li>
        <li>Child access decides which child can use paid learning features.</li>
        <li>Reports, assessments, and chats still stay separated by child profile.</li>
      </ul>
    </div>
  </div>;
}

function labelForStatus(status: ChildAccessStatus): string {
  if (status === 'active') return 'Active';
  if (status === 'trial') return 'Trial';
  if (status === 'past_due') return 'Past Due';
  return 'Paused';
}

function periodText(record: ChildAccess): string {
  if (record.trial_ends_at) return `Trial ends ${new Date(record.trial_ends_at).toLocaleDateString()}`;
  if (record.current_period_ends_at) return `Current period ends ${new Date(record.current_period_ends_at).toLocaleDateString()}`;
  return 'No active billing period.';
}

function planButtonText(plan: BillingPlan): string {
  const discount = plan.annual_discount_label ? ` - ${plan.annual_discount_label}` : '';
  return `${plan.display_name} ${plan.price_label}${discount}`;
}
