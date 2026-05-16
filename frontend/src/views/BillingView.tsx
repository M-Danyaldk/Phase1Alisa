import { useEffect, useState } from 'react';
import { CheckCircle2, Clock, CreditCard, Users } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { SectionHeader } from '../components/SectionHeader';
import { listChildAccess, updateChildAccess } from '../lib/api/billing';
import { ChildAccess, ChildAccessStatus } from '../types/billing';

export function BillingView({ accessToken = '' }: { accessToken?: string }) {
  const [records, setRecords] = useState<ChildAccess[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingChildId, setSavingChildId] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function load() {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      setRecords(await listChildAccess(accessToken));
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

  const activeCount = records.filter(record => record.access_status === 'active' || record.access_status === 'trial').length;

  return <div className="page-stack">
    <SectionHeader eyebrow="Billing and access" title="Subscription access by child" desc="Each child has a separate access record, so one parent account can manage multiple children without mixing subscriptions or learning data." />

    {message && <p className="success-note">{message}</p>}
    {error && <p className="error-note">{error}</p>}

    <div className="card-grid three">
      <InfoCard icon={<Users />} title="Children Covered" desc={`${activeCount} of ${records.length} child profile(s) currently have trial or active access.`} />
      <InfoCard icon={<CreditCard />} title="Stripe Status" desc="Payment processing is ready for a future Stripe connection. This MVP stores child access in Supabase." />
      <InfoCard icon={<Clock />} title="Trial Rule" desc="New child profiles can be placed on a 7-day trial before a paid plan is connected." />
    </div>

    <div className="pricing-card">
      <h3>$129/month per student</h3>
      <p>Family discount: 5% for 2+ students. In production, Stripe subscriptions should update these child access records through a secure backend webhook.</p>
    </div>

    <div className="billing-list">
      {loading && <p className="muted-copy">Loading child access...</p>}
      {!loading && !records.length && <p className="muted-copy">No child profiles found. Add a child profile first.</p>}
      {records.map(record => <div className="billing-child-card" key={record.child_id}>
        <div>
          <span className={`access-status ${record.access_status}`}>{labelForStatus(record.access_status)}</span>
          <h3>{record.child_name}</h3>
          <p>{record.grade_level} · {record.plan_name}</p>
          <p>{periodText(record)}</p>
        </div>
        <div className="billing-actions">
          <button className="secondary-button compact" onClick={() => changeStatus(record.child_id, 'trial')} disabled={savingChildId === record.child_id}>Start Trial</button>
          <button className="secondary-button compact" onClick={() => changeStatus(record.child_id, 'active')} disabled={savingChildId === record.child_id}>Mark Active</button>
          <button className="secondary-button compact danger" onClick={() => changeStatus(record.child_id, 'inactive')} disabled={savingChildId === record.child_id}>Pause Access</button>
        </div>
      </div>)}
    </div>

    <div className="report-card">
      <h3>How this connects subscriptions to children</h3>
      <p>Each access row stores both the parent account ID and the child profile ID. Later, when Stripe is added, the webhook should update the matching child access row for the child selected at checkout.</p>
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
  return 'Inactive';
}

function periodText(record: ChildAccess): string {
  if (record.trial_ends_at) return `Trial ends ${new Date(record.trial_ends_at).toLocaleDateString()}`;
  if (record.current_period_ends_at) return `Current period ends ${new Date(record.current_period_ends_at).toLocaleDateString()}`;
  return 'No active billing period.';
}
