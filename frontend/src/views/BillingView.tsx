import { useEffect, useState } from 'react';
import { CreditCard, Users } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { createBulkCheckoutSession, createCheckoutSession, createCustomerPortalSession, getBillingStatus, resumeChildAccess, updateChildAccess } from '../lib/api/billing';
import { BillingPlan, BillingPlanKey, ChildAccess, ChildAccessStatus, CheckoutChildPlan, CouponRedemption, FamilyDiscountStatus } from '../types/billing';

const PENDING_CHECKOUT_KEY = 'msalisia_pending_checkout_child';

type PendingCheckout = {
  childId: string;
  childName: string;
};

export function BillingView({ accessToken = '' }: { accessToken?: string }) {
  const [records, setRecords] = useState<ChildAccess[]>([]);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [familyDiscount, setFamilyDiscount] = useState<FamilyDiscountStatus | null>(null);
  const [couponRedemptions, setCouponRedemptions] = useState<CouponRedemption[]>([]);
  const [paidCheckoutRequired, setPaidCheckoutRequired] = useState(false);
  const [couponCode, setCouponCode] = useState('');
  const [selectedPlans, setSelectedPlans] = useState<Record<string, BillingPlanKey>>({});
  const [loading, setLoading] = useState(false);
  const [savingChildId, setSavingChildId] = useState('');
  const [savingAccessAction, setSavingAccessAction] = useState<'pause' | 'resume' | ''>('');
  const [checkoutKey, setCheckoutKey] = useState('');
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [completedCheckout, setCompletedCheckout] = useState<PendingCheckout | null>(null);

  async function load() {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      const status = await getBillingStatus(accessToken);
      setRecords(status.children);
      setPlans(status.plans);
      setFamilyDiscount(status.family_discount || null);
      setCouponRedemptions(status.coupon_redemptions || []);
      setPaidCheckoutRequired(status.paid_checkout_required);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'Could not load child billing access.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [accessToken]);

  useEffect(() => {
    if (!window.location.pathname.includes('/billing/success')) return;
    const pending = readPendingCheckout();
    if (pending) {
      setCompletedCheckout(pending);
      sessionStorage.removeItem(PENDING_CHECKOUT_KEY);
    }
  }, []);

  async function pauseAccess(childId: string) {
    setSavingChildId(childId);
    setSavingAccessAction('pause');
    setError('');
    setMessage('');
    try {
      const updated = await updateChildAccess(accessToken, childId, 'inactive');
      setRecords(records.map(record => record.child_id === childId ? updated : record));
      setMessage(updated.cancel_at_period_end
        ? `${updated.child_name}'s access will pause after the current paid period ends.`
        : `${updated.child_name} is now marked ${labelForStatus(updated)}.`);
      await load();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not update child access.');
    } finally {
      setSavingChildId('');
      setSavingAccessAction('');
    }
  }

  async function resumeAccess(childId: string) {
    setSavingChildId(childId);
    setSavingAccessAction('resume');
    setError('');
    setMessage('');
    try {
      const updated = await resumeChildAccess(accessToken, childId);
      setRecords(records.map(record => record.child_id === childId ? updated : record));
      setMessage(`${updated.child_name}'s classroom access has resumed.`);
      await load();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not resume child access.');
    } finally {
      setSavingChildId('');
      setSavingAccessAction('');
    }
  }

  async function beginCheckout(childId: string, planKey: BillingPlanKey) {
    setCheckoutKey(`${childId}:${planKey}`);
    setError('');
    setMessage('');
    try {
      const child = records.find(record => record.child_id === childId);
      sessionStorage.setItem(PENDING_CHECKOUT_KEY, JSON.stringify({
        childId,
        childName: child?.child_name || 'this child',
      }));
      window.location.href = await createCheckoutSession(accessToken, childId, planKey, couponCode);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not start Stripe checkout.');
      setCheckoutKey('');
    }
  }

  async function beginBulkCheckout() {
    const selected = checkoutSelections(records, selectedPlans);
    if (!selected.length) {
      setError('Choose at least one child and plan before checkout.');
      return;
    }
    setCheckoutKey('bulk');
    setError('');
    setMessage('');
    try {
      sessionStorage.setItem(PENDING_CHECKOUT_KEY, JSON.stringify({
        childId: selected[0].child_id,
        childName: selected.length === 1 ? childName(records, selected[0].child_id) : `${selected.length} children`,
      }));
      window.location.href = await createBulkCheckoutSession(accessToken, selected, couponCode);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not start Stripe checkout.');
      setCheckoutKey('');
    }
  }

  function toggleSelectedPlan(childId: string, checked: boolean) {
    setSelectedPlans(current => {
      const next = { ...current };
      if (checked) {
        next[childId] = next[childId] || defaultPlanKey(plans);
      } else {
        delete next[childId];
      }
      return next;
    });
  }

  function choosePlan(childId: string, planKey: BillingPlanKey) {
    setSelectedPlans(current => ({ ...current, [childId]: planKey }));
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
  const checkoutSelectionCount = checkoutSelections(records, selectedPlans).length;
  const nextCheckoutChild = completedCheckout ? nextChildForCheckout(records, completedCheckout.childId) : null;
  const checkoutProcessing = completedCheckout && !records.find(record => record.child_id === completedCheckout.childId && record.access_status === 'active');

  return <div className="page-stack">
    <SectionHeader eyebrow="Billing and access" title="Subscription access by child" desc="Each child has a separate access record, so one parent account can manage multiple children without mixing subscriptions or learning data." />

    {message && <p className="success-note">{message}</p>}
    {error && <p className="error-note">{error}</p>}

    <div className="card-grid three">
      <InfoCard icon={<Users />} title="Children Covered" desc={`${activeCount} of ${records.length} child profile(s) currently have trial or active access.`} />
      <InfoCard icon={<CreditCard />} title="Secure Payment" desc="Your payment is processed securely through Stripe. Subscription changes take effect immediately after payment is confirmed." />
    </div>

    <div className="pricing-card">
      <h3>MsAlisia Plans</h3>
      <p>Chat starts at $129/month. Chat + Audio starts at $159/month. Annual plans include 1 month free.</p>
      <div className="annual-pricing-context-grid">
        {plans.filter(plan => plan.billing_interval === 'annual').map(plan => <div className="annual-pricing-context" key={plan.plan_key}>
          <strong>{plan.display_name}</strong>
          <span>{annualPlanContext(plan)}</span>
        </div>)}
      </div>
      {familyDiscount && <div className="billing-discount-panel">
        <strong>Family Discount</strong>
        <p>{familyDiscount.message}</p>
        <span>{familyDiscount.discount_percent}% off with 2+ active child subscriptions. Discounts are not retroactive and annual plans remain non-refundable.</span>
        {!familyDiscount.stripe_coupon_configured && familyDiscount.checkout_eligible && <span>Family coupon is not configured in Stripe yet, so checkout will allow a promotion code instead.</span>}
      </div>}
      {paidCheckoutRequired && <p className="billing-checkout-note">This email has already used a free trial. Please choose a plan to continue.</p>}
      {!paidCheckoutRequired && <p className="billing-checkout-note">Every new family receives a 7-day trial automatically when the first child enters the classroom.</p>}
      <label className="coupon-field">
        <span>Coupon code</span>
        <input value={couponCode} onChange={(event) => setCouponCode(event.target.value)} placeholder="Optional" />
      </label>
      <button className="secondary-button compact" onClick={openPortal} disabled={portalLoading || !records.length}>{portalLoading ? 'Opening...' : 'Manage Payment Method'}</button>
    </div>

    <section className="report-card">
      <div className="section-row">
        <div>
          <h3>Subscribe children</h3>
          <p className="muted-copy">Select one or more children, choose a plan for each, then continue to one secure Stripe checkout.</p>
        </div>
        <button className="primary-button" onClick={beginBulkCheckout} disabled={!checkoutSelectionCount || checkoutKey === 'bulk'}>
          {checkoutKey === 'bulk' ? 'Opening Checkout...' : `Checkout ${checkoutSelectionCount || ''}`.trim()}
        </button>
      </div>
      {records.length >= 2 && <p className="billing-checkout-note">Family discount: 5% off applies when 2 or more child subscriptions are active or included in this checkout.</p>}
      <div className="billing-list compact-list">
        {records.map(record => {
          const paid = hasCurrentPaidAccess(record);
          const selected = Boolean(selectedPlans[record.child_id]);
          return <div className={`billing-child-card subscribe-child-row${paid ? ' subscribed' : ''}`} key={`select-${record.child_id}`}>
            <label className="billing-selection-row">
              <input
                type="checkbox"
                checked={selected}
                disabled={paid}
                onChange={(event) => toggleSelectedPlan(record.child_id, event.target.checked)}
              />
              <span className="billing-selection-copy">
                <strong>{record.child_name}</strong>
                <small>{paid ? `Already subscribed. ${periodText(record)}` : labelForStatus(record)}</small>
              </span>
            </label>
            {paid
              ? <span className="subscription-covered-note">Covered for this billing period</span>
              : <select
                value={selectedPlans[record.child_id] || defaultPlanKey(plans)}
                disabled={!selected}
                onChange={(event) => choosePlan(record.child_id, event.target.value as BillingPlanKey)}
              >
                {plans.map(plan => <option key={plan.plan_key} value={plan.plan_key}>{planButtonText(plan)}</option>)}
              </select>}
          </div>;
        })}
      </div>
    </section>

    {completedCheckout && <section className="report-card">
      {checkoutProcessing
        ? <>
          <h3>We&apos;re confirming the payment now.</h3>
          <p className="muted-copy">This usually takes a moment. If the child still shows as paused, refresh the page after Stripe finishes syncing.</p>
        </>
        : nextCheckoutChild
          ? <>
            <h3>Payment confirmed for {completedCheckout.childName}.</h3>
            <p className="muted-copy">You can now subscribe {nextCheckoutChild.child_name} without starting over.</p>
            <div className="billing-actions">
              {plans.map(plan => {
                const key = `${nextCheckoutChild.child_id}:${plan.plan_key}`;
                return <button
                  key={plan.plan_key}
                  className="secondary-button compact"
                  onClick={() => beginCheckout(nextCheckoutChild.child_id, plan.plan_key)}
                  disabled={!plan.stripe_price_configured || checkoutKey === key}
                  title={plan.stripe_price_configured ? plan.display_name : `${plan.stripe_price_env} is not configured`}
                >
                  {checkoutKey === key ? 'Opening...' : planButtonText(plan)}
                </button>;
              })}
            </div>
          </>
          : <>
            <h3>All children are covered.</h3>
            <p className="muted-copy">You&apos;re ready to continue.</p>
          </>}
    </section>}

    <div className="billing-list">
      {loading && <p className="muted-copy">Loading child access...</p>}
      {!loading && !records.length && <p className="muted-copy">No child profiles found. Add a child profile first.</p>}
      {records.map(record => <div className="billing-child-card" key={record.child_id}>
        <div>
          <span className={`access-status ${record.cancel_at_period_end ? 'past_due' : record.access_status}`}>{labelForStatus(record)}</span>
          <h3>{record.child_name}</h3>
          <p>{record.grade_level} - {record.plan_name}</p>
          <p>{periodText(record)}</p>
        </div>
        <div className="billing-actions">
          {record.access_status === 'inactive' || record.cancel_at_period_end
            ? <button className="secondary-button compact" onClick={() => resumeAccess(record.child_id)} disabled={savingChildId === record.child_id}>
              {savingChildId === record.child_id && savingAccessAction === 'resume' ? 'Resuming access...' : 'Resume Access'}
            </button>
            : <button className="secondary-button compact danger" onClick={() => pauseAccess(record.child_id)} disabled={savingChildId === record.child_id}>
              {savingChildId === record.child_id && savingAccessAction === 'pause' ? 'Pausing access...' : 'Pause Access'}
            </button>}
        </div>
        <div className="billing-actions billing-plan-actions">
          {hasCurrentPaidAccess(record)
            ? <div className="subscription-management-note">
              <strong>This child is already covered for the current billing period.</strong>
              <span>Use Manage Payment Method for plan, payment, or subscription changes.</span>
            </div>
            : plans.map(plan => {
              const key = `${record.child_id}:${plan.plan_key}`;
              return <div className="billing-plan-action" key={plan.plan_key}>
                <button
                  className="secondary-button compact"
                  onClick={() => beginCheckout(record.child_id, plan.plan_key)}
                  disabled={!plan.stripe_price_configured || checkoutKey === key}
                  title={plan.stripe_price_configured ? plan.display_name : `${plan.stripe_price_env} is not configured`}
                >
                  {checkoutKey === key ? 'Opening...' : planButtonText(plan)}
                </button>
              </div>;
            })}
        </div>
      </div>)}
    </div>

    {!!couponRedemptions.length && <div className="report-card">
      <h3>Recent coupon checks</h3>
      <ul>
        {couponRedemptions.slice(0, 3).map(coupon => <li key={coupon.id || `${coupon.coupon_code}-${coupon.created_at}`}>
          {coupon.coupon_code}: {coupon.validation_status}
        </li>)}
      </ul>
    </div>}
  </div>;
}

function labelForStatus(recordOrStatus: ChildAccess | ChildAccessStatus): string {
  const status = typeof recordOrStatus === 'string' ? recordOrStatus : recordOrStatus.access_status;
  if (typeof recordOrStatus !== 'string' && recordOrStatus.cancel_at_period_end) return 'Pauses After Period';
  if (status === 'active') return 'Active';
  if (status === 'trial') return 'Trial';
  if (status === 'past_due') return 'Past Due';
  return 'Paused';
}

function periodText(record: ChildAccess): string {
  if (record.cancel_at_period_end && record.current_period_ends_at) return `Access pauses after ${new Date(record.current_period_ends_at).toLocaleDateString()}`;
  if (record.trial_ends_at) return `Trial ends ${new Date(record.trial_ends_at).toLocaleDateString()}`;
  if (record.current_period_ends_at) return `Current period ends ${new Date(record.current_period_ends_at).toLocaleDateString()}`;
  return 'No active billing period.';
}

function planButtonText(plan: BillingPlan): string {
  const discount = plan.annual_discount_label ? ` - ${plan.annual_discount_label}` : '';
  return `${plan.display_name} ${plan.price_label}${discount}`;
}

function annualPlanContext(plan: BillingPlan): string {
  if (plan.plan_key === 'voice_annual') {
    return 'Chat + Audio Annual — $1,749/year. That’s 1 month free — equivalent to $145.75/month.';
  }
  if (plan.plan_key === 'text_annual') {
    return 'Chat Annual — $1,419/year. That’s 1 month free — equivalent to $118.25/month.';
  }
  return `${plan.display_name} ${plan.price_label}. Annual plans include 1 month free.`;
}

function defaultPlanKey(plans: BillingPlan[]): BillingPlanKey {
  return plans.find(plan => plan.plan_key === 'text_monthly')?.plan_key || plans[0]?.plan_key || 'text_monthly';
}

function checkoutSelections(records: ChildAccess[], selectedPlans: Record<string, BillingPlanKey>): CheckoutChildPlan[] {
  return records
    .filter(record => selectedPlans[record.child_id] && !hasCurrentPaidAccess(record))
    .map(record => ({
      child_id: record.child_id,
      plan_key: selectedPlans[record.child_id],
    }));
}

function childName(records: ChildAccess[], childId: string): string {
  return records.find(record => record.child_id === childId)?.child_name || 'this child';
}

function hasCurrentPaidAccess(record: ChildAccess): boolean {
  if (record.access_status !== 'active' || !record.current_period_ends_at) {
    return record.access_status === 'active' && Boolean(record.current_period_ends_at === null || record.current_period_ends_at === undefined);
  }
  return Date.parse(record.current_period_ends_at) > Date.now();
}

function readPendingCheckout(): PendingCheckout | null {
  try {
    const raw = sessionStorage.getItem(PENDING_CHECKOUT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PendingCheckout;
    if (!parsed.childId) return null;
    return {
      childId: parsed.childId,
      childName: parsed.childName || 'this child',
    };
  } catch {
    return null;
  }
}

function nextChildForCheckout(records: ChildAccess[], completedChildId: string): ChildAccess | null {
  return records.find(record => record.child_id !== completedChildId && record.access_status !== 'active') || null;
}
