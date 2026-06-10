import { useEffect, useState } from 'react';
import { SectionHeader } from '../components/SectionHeader';
import { createBulkCheckoutSession, createCheckoutSession, createCustomerPortalSession, getBillingStatus, resumeChildAccess, updateChildAccess } from '../lib/api/billing';
import { getStudentAccess } from '../lib/api/studentAccess';
import { getFamilyClassroomLink } from '../lib/api/studentAuth';
import { BillingPlan, BillingPlanKey, ChildAccess, ChildAccessStatus, CheckoutChildPlan, CouponRedemption } from '../types/billing';
import { StudentAccess } from '../types/studentAccess';
import { FamilyClassroomLink } from '../types/studentSession';

const PENDING_CHECKOUT_KEY = 'msalisia_pending_checkout_child';
const BILLING_TARGET_CHILD_KEY = 'msalisia_billing_target_child';
const NEW_CHILD_LOGIN_HANDOFF_KEY = 'msalisia_new_child_login_handoff';
const MIXED_BILLING_INTERVAL_ERROR = 'Monthly and annual plans need separate checkouts. Please checkout monthly children first, then annual children.';

type PendingCheckout = {
  childId: string;
  childName: string;
  username?: string;
  pin?: string;
};

type ChildLoginHandoff = {
  childId: string;
  childName: string;
  username: string;
  pin: string;
};

export function BillingView({ accessToken = '', onCheckoutComplete }: { accessToken?: string; onCheckoutComplete?: (childId: string) => void }) {
  const [records, setRecords] = useState<ChildAccess[]>([]);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [couponRedemptions, setCouponRedemptions] = useState<CouponRedemption[]>([]);
  const [paidCheckoutRequired, setPaidCheckoutRequired] = useState(false);
  const [couponCode, setCouponCode] = useState('');
  const [selectedPlans, setSelectedPlans] = useState<Record<string, BillingPlanKey>>({});
  const [checkoutPlanKey, setCheckoutPlanKey] = useState<BillingPlanKey>('text_annual');
  const [familyLink, setFamilyLink] = useState<FamilyClassroomLink | null>(null);
  const [newChildLogin, setNewChildLogin] = useState<ChildLoginHandoff | null>(() => readChildLoginHandoff());
  const [revealedTrialHandoffId, setRevealedTrialHandoffId] = useState('');
  const [completedCheckoutAccess, setCompletedCheckoutAccess] = useState<StudentAccess | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingChildId, setSavingChildId] = useState('');
  const [savingAccessAction, setSavingAccessAction] = useState<'pause' | 'resume' | ''>('');
  const [checkoutKey, setCheckoutKey] = useState('');
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState('');
  const [checkoutError, setCheckoutError] = useState('');
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
    if (!accessToken) return;
    getFamilyClassroomLink(accessToken)
      .then(setFamilyLink)
      .catch(() => setFamilyLink(null));
  }, [accessToken]);

  useEffect(() => {
    if (!records.length || !plans.length) return;
    const defaultKey = defaultPlanKey(plans);
    setCheckoutPlanKey(current => plans.some(plan => plan.plan_key === current) ? current : defaultKey);
    setSelectedPlans(current => {
      const next = { ...current };
      for (const record of records) {
        if (!hasCurrentPaidAccess(record) && !next[record.child_id]) {
          next[record.child_id] = defaultKey;
        }
      }
      return next;
    });
  }, [records, plans]);

  useEffect(() => {
    if (!records.length || !plans.length) return;
    const targetChildId = sessionStorage.getItem(BILLING_TARGET_CHILD_KEY);
    if (!targetChildId) return;
    const target = records.find(record => record.child_id === targetChildId);
    if (!target || hasCurrentPaidAccess(target)) {
      sessionStorage.removeItem(BILLING_TARGET_CHILD_KEY);
      return;
    }
    setSelectedPlans(current => ({
      ...current,
      [targetChildId]: current[targetChildId] || defaultPlanKey(plans),
    }));
    window.setTimeout(() => {
      document.getElementById('subscribe-children')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
    sessionStorage.removeItem(BILLING_TARGET_CHILD_KEY);
  }, [records, plans]);

  useEffect(() => {
    if (!window.location.pathname.includes('/billing/success')) return;
    const pending = readPendingCheckout();
    if (pending) {
      setCompletedCheckout(pending);
      sessionStorage.removeItem(PENDING_CHECKOUT_KEY);
    }
  }, []);

  useEffect(() => {
    if (!window.location.pathname.includes('/billing/cancel')) return;
    sessionStorage.removeItem(PENDING_CHECKOUT_KEY);
    setMessage('Checkout was canceled. You can review billing options below when you are ready.');
  }, []);

  useEffect(() => {
    if (!accessToken || !completedCheckout) return;
    getStudentAccess(accessToken, completedCheckout.childId)
      .then(setCompletedCheckoutAccess)
      .catch(() => setCompletedCheckoutAccess(null));
  }, [accessToken, completedCheckout]);

  function chooseCheckoutPlan(planKey: BillingPlanKey) {
    setCheckoutPlanKey(planKey);
    setSelectedPlans(current => {
      const next = { ...current };
      for (const record of records) {
        if (next[record.child_id] && !hasCurrentPaidAccess(record)) {
          next[record.child_id] = planKey;
        }
      }
      return next;
    });
  }

  function startFreeTrialForNewChild() {
    if (!newChildLogin) return;
    setError('');
    setCheckoutError('');
    setRevealedTrialHandoffId(newChildLogin.childId);
    setMessage(`Use the classroom link and PIN below for ${newChildLogin.childName}. The 7-day trial starts when your child signs in for the first time.`);
  }

  function dismissNewChildLogin() {
    sessionStorage.removeItem(NEW_CHILD_LOGIN_HANDOFF_KEY);
    setNewChildLogin(null);
  }

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
    setCheckoutError('');
    setMessage('');
    try {
      const child = records.find(record => record.child_id === childId);
      sessionStorage.setItem(PENDING_CHECKOUT_KEY, JSON.stringify({
        childId,
        childName: child?.child_name || 'this child',
        ...(newChildLogin?.childId === childId ? {
          username: newChildLogin.username,
          pin: newChildLogin.pin,
        } : {}),
      }));
      window.location.href = await createCheckoutSession(accessToken, childId, planKey, couponCode);
    } catch (submitError) {
      const nextError = submitError instanceof Error ? submitError.message : 'Could not start Stripe checkout.';
      setError(nextError);
      setCheckoutError(nextError);
      setCheckoutKey('');
    }
  }

  async function beginBulkCheckout() {
    const selected = checkoutSelections(records, selectedPlans);
    if (!selected.length) {
      setError('Choose at least one child and plan before checkout.');
      setCheckoutError('Choose at least one child and plan before checkout.');
      return;
    }
    const unavailable = selected.find(selection => !plans.find(plan => plan.plan_key === selection.plan_key)?.stripe_price_configured);
    if (unavailable) {
      const nextError = `${childName(records, unavailable.child_id)} has a selected plan that is not connected to Stripe yet. Choose another plan or configure the missing Stripe price.`;
      setError(nextError);
      setCheckoutError(nextError);
      return;
    }
    if (hasMixedBillingIntervals(selected, plans)) {
      setError(MIXED_BILLING_INTERVAL_ERROR);
      setCheckoutError(MIXED_BILLING_INTERVAL_ERROR);
      return;
    }
    setCheckoutKey('bulk');
    setError('');
    setCheckoutError('');
    setMessage('');
    try {
      sessionStorage.setItem(PENDING_CHECKOUT_KEY, JSON.stringify({
        childId: selected[0].child_id,
        childName: selected.length === 1 ? childName(records, selected[0].child_id) : `${selected.length} children`,
        ...(selected.length === 1 && newChildLogin?.childId === selected[0].child_id ? {
          username: newChildLogin.username,
          pin: newChildLogin.pin,
        } : {}),
      }));
      window.location.href = await createBulkCheckoutSession(accessToken, selected, couponCode);
    } catch (submitError) {
      const nextError = submitError instanceof Error ? submitError.message : 'Could not start Stripe checkout.';
      setError(nextError);
      setCheckoutError(nextError);
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

  const checkoutSelectionCount = checkoutSelections(records, selectedPlans).length;
  const nextCheckoutChild = completedCheckout ? nextChildForCheckout(records, completedCheckout.childId) : null;
  const checkoutProcessing = completedCheckout && !records.find(record => record.child_id === completedCheckout.childId && record.access_status === 'active');
  const classroomUrl = familyLink ? `${window.location.origin}${familyLink.classroom_path}` : '';
  const targetRecord = newChildLogin ? records.find(record => record.child_id === newChildLogin.childId) : null;
  const canStartTrialForNewChild = Boolean(newChildLogin && !paidCheckoutRequired && targetRecord && !childAccessAllowsLearning(targetRecord));
  const showNewChildLoginProof = Boolean(newChildLogin && (revealedTrialHandoffId === newChildLogin.childId || childAccessAllowsLearning(targetRecord)));

  return <div className="page-stack">
    <SectionHeader eyebrow="Billing and access" title="Choose access for your children" desc="Select a plan, keep the children you want included, and continue to secure checkout." />

    {message && <p className="success-note">{message}</p>}
    {error && <p className="error-note">{error}</p>}

    {newChildLogin && <section className="report-card new-child-access-card">
      <div>
        <span className="eyebrow">{newChildLogin.childName}</span>
        <h3>Start learning</h3>
        <p>Use the free trial for the first child, or subscribe now if you prefer to start with a paid plan.</p>
      </div>
      {showNewChildLoginProof && <div className="student-login-proof">
        {classroomUrl && <label>Family classroom link<input readOnly value={classroomUrl} /></label>}
        <label>Username<input readOnly value={newChildLogin.username} /></label>
        <label>PIN<input readOnly value={newChildLogin.pin} /></label>
      </div>}
      <div className="parent-action-row">
        {canStartTrialForNewChild && <button className="primary-button" onClick={startFreeTrialForNewChild}>
          Start Free 7-Day Trial
        </button>}
        {classroomUrl && showNewChildLoginProof && <button className="primary-button" onClick={() => window.location.assign(classroomUrl)}>Open Classroom</button>}
        <button className="secondary-button" onClick={() => {
          setSelectedPlans(current => ({ ...current, [newChildLogin.childId]: current[newChildLogin.childId] || defaultPlanKey(plans) }));
          document.getElementById('subscribe-children')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }}>Subscribe Now</button>
        <button className="link-button" type="button" onClick={dismissNewChildLogin}>Hide this panel</button>
      </div>
    </section>}

    <section className="report-card" id="subscribe-children">
      <div className="section-row">
        <div>
          <h3>Subscribe children</h3>
          <p className="muted-copy">Children without paid access are selected by default. Choose a plan, uncheck anyone to exclude, then continue to checkout.</p>
        </div>
      </div>
      <label className="checkout-plan-picker">Plan for this checkout
        <select value={checkoutPlanKey} onChange={(event) => chooseCheckoutPlan(event.target.value as BillingPlanKey)}>
          {plans.map(plan => <option key={plan.plan_key} value={plan.plan_key} disabled={!plan.stripe_price_configured}>{planButtonText(plan)}</option>)}
        </select>
      </label>
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
                <small>{paid ? `Already subscribed. ${periodText(record)}` : 'Ready for plan selection'}</small>
              </span>
            </label>
            {paid
              ? <span className="subscription-covered-note">Covered for this billing period</span>
              : <select
                value={selectedPlans[record.child_id] || defaultPlanKey(plans)}
                disabled={!selected}
                onChange={(event) => choosePlan(record.child_id, event.target.value as BillingPlanKey)}
              >
                {plans.map(plan => <option key={plan.plan_key} value={plan.plan_key} disabled={!plan.stripe_price_configured}>{planButtonText(plan)}</option>)}
              </select>}
          </div>;
        })}
      </div>
      <div className="billing-checkout-footer">
        <label className="coupon-field compact-coupon">
          <span>Coupon code</span>
          <input value={couponCode} onChange={(event) => setCouponCode(event.target.value)} placeholder="Optional" />
        </label>
        <button className="secondary-button compact" onClick={openPortal} disabled={portalLoading || !records.length}>{portalLoading ? 'Opening...' : 'Update Payment Details'}</button>
        <button className="primary-button" onClick={beginBulkCheckout} disabled={!checkoutSelectionCount || checkoutKey === 'bulk'}>
          {checkoutKey === 'bulk' ? 'Opening Checkout...' : `Checkout ${checkoutSelectionCount || ''}`.trim()}
        </button>
      </div>
      {checkoutError && <p className="error-note">{checkoutError}</p>}
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
            <h3>Payment confirmed for {completedCheckout.childName}.</h3>
            <p className="muted-copy">Use the family classroom link and student login below to help your child sign in.</p>
            <div className="student-login-proof">
              {classroomUrl && <label>Family classroom link<input readOnly value={classroomUrl} /></label>}
              {(completedCheckout.username || completedCheckoutAccess?.username) && <label>Username<input readOnly value={completedCheckout.username || completedCheckoutAccess?.username || ''} /></label>}
              {completedCheckout.pin
                ? <label>PIN<input readOnly value={completedCheckout.pin} /></label>
                : <p className="muted-copy">Use the PIN created for this child in Child Profiles.</p>}
            </div>
            <div className="parent-action-row">
              {classroomUrl && <button className="primary-button" type="button" onClick={() => window.location.assign(classroomUrl)}>Open Classroom</button>}
              <button className="secondary-button" type="button" onClick={() => onCheckoutComplete?.(completedCheckout.childId)}>Back to Dashboard</button>
            </div>
          </>}
    </section>}

    <div className="billing-list">
      {loading && <p className="muted-copy">Loading child access...</p>}
      {!loading && !records.length && <p className="muted-copy">No child profiles found. Add a child profile first.</p>}
      {records.map(record => <div className="billing-child-card" key={record.child_id}>
        <div>
          <span className={`access-status ${record.cancel_at_period_end ? 'past_due' : record.access_status}`}>{labelForStatus(record)}</span>
          <h3>{record.child_name}</h3>
          {billingPlanSummary(record) && <p>{billingPlanSummary(record)}</p>}
          {periodText(record) && <p>{periodText(record)}</p>}
        </div>
        <div className="billing-actions">
          {record.cancel_at_period_end
            ? <button className="secondary-button compact" onClick={() => resumeAccess(record.child_id)} disabled={savingChildId === record.child_id}>
              {savingChildId === record.child_id && savingAccessAction === 'resume' ? 'Resuming access...' : 'Resume Access'}
            </button>
            : hasCurrentPaidAccess(record) ? <button className="pause-access-link" onClick={() => pauseAccess(record.child_id)} disabled={savingChildId === record.child_id}>
              {savingChildId === record.child_id && savingAccessAction === 'pause' ? 'Pausing access...' : 'Pause after current period'}
            </button> : null}
        </div>
        <div className="billing-actions billing-plan-actions">
          <div className={hasCurrentPaidAccess(record) ? 'subscription-management-note' : 'subscription-management-note muted'}>
            <strong>{hasCurrentPaidAccess(record) ? 'This child is already covered for the current billing period.' : 'Use Subscribe children above to choose access.'}</strong>
            <span>{record.access_paused_reason === 'payment_failed' ? 'Payment failed. Access is paused until payment succeeds.' : 'Use Update Payment Details for plan, payment, or subscription changes.'}</span>
          </div>
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
  if (status === 'inactive' && typeof recordOrStatus !== 'string') {
    const hasPriorAccess = Boolean(recordOrStatus.current_period_ends_at || recordOrStatus.trial_started_at || recordOrStatus.trial_ends_at);
    return hasPriorAccess ? 'Paused' : 'Billing Required';
  }
  if (status === 'inactive') return 'Billing Required';
  return 'Paused';
}

function periodText(record: ChildAccess): string {
  if (record.access_paused_reason === 'payment_failed') return 'Payment failed. Access is paused until payment succeeds.';
  if (record.cancel_at_period_end && record.current_period_ends_at) return `Access pauses after ${new Date(record.current_period_ends_at).toLocaleDateString()}`;
  if (record.trial_ends_at) return `Trial ends ${new Date(record.trial_ends_at).toLocaleDateString()}`;
  if (record.current_period_ends_at) return `Current period ends ${new Date(record.current_period_ends_at).toLocaleDateString()}`;
  return '';
}

function billingPlanSummary(record: ChildAccess): string {
  const planName = (record.plan_name || '').trim();
  if (!planName || planName.toLowerCase() === 'no paid plan selected') return '';
  return `${record.grade_level} - ${planName}`;
}

function planButtonText(plan: BillingPlan): string {
  const discount = plan.annual_discount_label ? ` - ${plan.annual_discount_label}` : '';
  return `${plan.display_name} ${plan.price_label}${discount}`;
}

function defaultPlanKey(plans: BillingPlan[]): BillingPlanKey {
  return plans.find(plan => plan.plan_key === 'text_annual')?.plan_key || plans.find(plan => plan.plan_key === 'text_monthly')?.plan_key || plans[0]?.plan_key || 'text_annual';
}

function checkoutSelections(records: ChildAccess[], selectedPlans: Record<string, BillingPlanKey>): CheckoutChildPlan[] {
  return records
    .filter(record => selectedPlans[record.child_id] && !hasCurrentPaidAccess(record))
    .map(record => ({
      child_id: record.child_id,
      plan_key: selectedPlans[record.child_id],
    }));
}

function hasMixedBillingIntervals(selections: CheckoutChildPlan[], plans: BillingPlan[]): boolean {
  const intervals = new Set(selections.map(selection => plans.find(plan => plan.plan_key === selection.plan_key)?.billing_interval).filter(Boolean));
  return intervals.size > 1;
}

function childName(records: ChildAccess[], childId: string): string {
  return records.find(record => record.child_id === childId)?.child_name || 'this child';
}

function childAccessAllowsLearning(record?: ChildAccess | null): boolean {
  if (!record) return false;
  if (record.access_status === 'active') {
    return !record.current_period_ends_at || Date.parse(record.current_period_ends_at) > Date.now();
  }
  if (record.access_status === 'trial') {
    return Boolean(record.trial_ends_at && Date.parse(record.trial_ends_at) > Date.now());
  }
  return false;
}

function hasCurrentPaidAccess(record: ChildAccess): boolean {
  if (record.access_status !== 'active' || !record.current_period_ends_at) {
    return record.access_status === 'active' && Boolean(record.current_period_ends_at === null || record.current_period_ends_at === undefined);
  }
  return Date.parse(record.current_period_ends_at) > Date.now();
}

function readChildLoginHandoff(): ChildLoginHandoff | null {
  try {
    const raw = sessionStorage.getItem(NEW_CHILD_LOGIN_HANDOFF_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ChildLoginHandoff;
    if (!parsed.childId || !parsed.username || !parsed.pin) return null;
    return parsed;
  } catch {
    sessionStorage.removeItem(NEW_CHILD_LOGIN_HANDOFF_KEY);
    return null;
  }
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

