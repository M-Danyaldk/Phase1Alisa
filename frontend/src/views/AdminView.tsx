import { useEffect, useMemo, useState } from 'react';
import { BarChart3, FileText, Settings, ShieldCheck, Users, WalletCards } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { NavItem } from '../components/NavItem';
import { SectionHeader } from '../components/SectionHeader';
import { apiGet, apiPatch, apiPost } from '../lib/api';
import { AdminAuditLog, AdminOverview, AdminSetting, AdminSubscription, AdminUser, LLMEvent, StoredAssessmentResult } from '../types';
import { ProfileResponse } from '../types/auth';

type AdminSection = 'dashboard' | 'users' | 'subscriptions' | 'reports' | 'settings' | 'admins';

type Props = {
  accessToken: string;
  profile: ProfileResponse;
  section: AdminSection;
  onSectionChange: (section: AdminSection) => void;
  onLogout: () => void;
};

const permissions = ['manage_users', 'manage_subscriptions', 'manage_courses', 'view_analytics', 'refund_payments', 'manage_admins', 'manage_settings'];

export function AdminView({ accessToken, profile, section, onSectionChange, onLogout }: Props) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${accessToken}` }), [accessToken]);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [subscriptions, setSubscriptions] = useState<AdminSubscription[]>([]);
  const [auditLogs, setAuditLogs] = useState<AdminAuditLog[]>([]);
  const [reportAssessments, setReportAssessments] = useState<StoredAssessmentResult[]>([]);
  const [reportLlmEvents, setReportLlmEvents] = useState<LLMEvent[]>([]);
  const [settings, setSettings] = useState<AdminSetting[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [invitePassword, setInvitePassword] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError('');
      try {
        if (section === 'dashboard') {
          const data = await apiGet<AdminOverview>('/api/admin/overview', authHeaders);
          if (!cancelled) setOverview(data);
        }
        if (section === 'users' || section === 'admins') {
          const data = await apiGet<{ users: AdminUser[] }>(`/api/admin/users${search ? `?search=${encodeURIComponent(search)}` : ''}`, authHeaders);
          if (!cancelled) setUsers(data.users);
        }
        if (section === 'subscriptions') {
          const data = await apiGet<{ subscriptions: AdminSubscription[] }>('/api/admin/subscriptions', authHeaders);
          if (!cancelled) setSubscriptions(data.subscriptions);
        }
        if (section === 'reports') {
          const data = await apiGet<{ assessments: StoredAssessmentResult[]; llm_events: LLMEvent[]; audit_logs: AdminAuditLog[] }>('/api/admin/reports', authHeaders);
          if (!cancelled) {
            setReportAssessments(data.assessments);
            setReportLlmEvents(data.llm_events);
            setAuditLogs(data.audit_logs);
          }
        }
        if (section === 'settings') {
          const data = await apiGet<{ settings: AdminSetting[] }>('/api/admin/settings', authHeaders);
          if (!cancelled) setSettings(data.settings);
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : 'Admin request failed.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [authHeaders, section, search]);

  async function updateUserStatus(userId: string, status: AdminUser['status']) {
    await apiPatch<AdminUser>(`/api/admin/users/${userId}/status`, { status, reason: `Changed from admin ${profile.email}` }, authHeaders);
    const data = await apiGet<{ users: AdminUser[] }>('/api/admin/users', authHeaders);
    setUsers(data.users);
  }

  async function updateSubscription(subscriptionId: string, accessStatus: AdminSubscription['access_status']) {
    await apiPatch<AdminSubscription>(`/api/admin/subscriptions/${subscriptionId}`, {
      access_status: accessStatus,
      plan_name: 'Phase 1 MVP',
      reason: `Changed from admin ${profile.email}`,
    }, authHeaders);
    const data = await apiGet<{ subscriptions: AdminSubscription[] }>('/api/admin/subscriptions', authHeaders);
    setSubscriptions(data.subscriptions);
  }

  async function inviteAdmin() {
    const email = inviteEmail.trim().toLowerCase();
    const fullName = inviteName.trim();
    if (!email || !fullName || invitePassword.length < 8) {
      setError('Admin name, email, and an 8+ character temporary password are required.');
      return;
    }
    await apiPost('/api/admin/admins/invite', {
      email,
      full_name: fullName,
      role: 'admin',
      permissions: ['manage_users', 'manage_subscriptions', 'view_analytics'],
      temporary_password: invitePassword,
    }, authHeaders);
    setInviteEmail('');
    setInviteName('');
    setInvitePassword('');
    const data = await apiGet<{ users: AdminUser[] }>('/api/admin/users', authHeaders);
    setUsers(data.users);
  }

  const adminUsers = users.filter(user => user.role === 'admin' || user.role === 'super_admin');

  return <div className="app-shell admin-shell">
    <aside className="sidebar">
      <div className="brand-block">
        <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
        <div>
          <h1>Admin</h1>
          <p>{profile.full_name}</p>
        </div>
      </div>
      <nav aria-label="Admin navigation">
        <NavItem icon={<BarChart3 />} label="Dashboard" active={section === 'dashboard'} onClick={() => onSectionChange('dashboard')} />
        <NavItem icon={<Users />} label="Users" active={section === 'users'} onClick={() => onSectionChange('users')} />
        <NavItem icon={<WalletCards />} label="Subscriptions" active={section === 'subscriptions'} onClick={() => onSectionChange('subscriptions')} />
        <NavItem icon={<FileText />} label="Reports" active={section === 'reports'} onClick={() => onSectionChange('reports')} />
        <NavItem icon={<Settings />} label="Settings" active={section === 'settings'} onClick={() => onSectionChange('settings')} />
        <NavItem icon={<ShieldCheck />} label="Admins" active={section === 'admins'} onClick={() => onSectionChange('admins')} />
      </nav>
      <button className="logout-button" onClick={onLogout}>Logout</button>
    </aside>
    <main>
      <SectionHeader eyebrow="Admin Console" title={titleFor(section)} desc="Role-based access is enforced by the backend for every admin request." />
      {error && <p className="error-note app-error">{error}</p>}
      {loading && <p className="muted-copy">Loading admin data...</p>}
      {section === 'dashboard' && overview && <Dashboard overview={overview} />}
      {section === 'users' && <UsersSection users={users} currentUserId={profile.id} search={search} onSearch={setSearch} onStatus={updateUserStatus} />}
      {section === 'subscriptions' && <SubscriptionsSection subscriptions={subscriptions} onStatus={updateSubscription} />}
      {section === 'reports' && <ReportsSection assessments={reportAssessments} llmEvents={reportLlmEvents} logs={auditLogs} />}
      {section === 'settings' && <SettingsSection settings={settings} />}
      {section === 'admins' && <AdminsSection users={adminUsers} inviteEmail={inviteEmail} inviteName={inviteName} invitePassword={invitePassword} onEmail={setInviteEmail} onName={setInviteName} onPassword={setInvitePassword} onInvite={inviteAdmin} />}
    </main>
  </div>;
}

function Dashboard({ overview }: { overview: AdminOverview }) {
  return <div className="page-stack">
    <div className="card-grid three">
      <InfoCard icon={<Users />} title="Users" desc={`${overview.totals.users} total users, including ${overview.totals.admins} admins.`} />
      <InfoCard icon={<WalletCards />} title="Subscriptions" desc={`${overview.totals.active_subscriptions} active and ${overview.totals.past_due_subscriptions} past due.`} />
      <InfoCard icon={<BarChart3 />} title="AI Usage" desc={`${overview.llm_events.length} recent LLM events available for review.`} />
    </div>
    <div className="admin-grid">
      <ListCard title="Recent Students" items={overview.students.map(student => `${student.name} - Grade ${student.grade}`)} empty="No student profiles yet." />
      <ListCard title="Recent Assessments" items={overview.assessments.map(item => `${item.student_name || 'Student'} - ${item.subject} - ${item.estimated_level}`)} empty="No assessments yet." />
      <ListCard title="Recent Admin Actions" items={overview.audit_logs.map(log => `${log.action} - ${log.target_type}`)} empty="No admin actions yet." />
    </div>
  </div>;
}

function UsersSection({ users, currentUserId, search, onSearch, onStatus }: { users: AdminUser[]; currentUserId: string; search: string; onSearch: (value: string) => void; onStatus: (id: string, status: AdminUser['status']) => void }) {
  return <div className="page-stack">
    <label>Search users<input value={search} onChange={event => onSearch(event.target.value)} placeholder="Name or email" /></label>
    <div className="report-card">
      <h3>User accounts</h3>
      <ul>{users.map(user => {
        const isSelf = user.id === currentUserId;
        return <li key={user.id}>{user.full_name} - {user.email} - {user.role} - {user.status} {isSelf ? <span className="muted-copy">Current admin</span> : <button className="secondary-button" onClick={() => onStatus(user.id, user.status === 'active' ? 'suspended' : 'active')}>{user.status === 'active' ? 'Suspend' : 'Reactivate'}</button>}</li>;
      })}</ul>
    </div>
  </div>;
}

function SubscriptionsSection({ subscriptions, onStatus }: { subscriptions: AdminSubscription[]; onStatus: (id: string, status: AdminSubscription['access_status']) => void }) {
  return <div className="report-card">
    <h3>Subscriptions</h3>
    <ul>{subscriptions.map(item => <li key={item.id}>{item.child_name || item.child_id} - {item.plan_name} - {item.access_status} <button className="secondary-button" onClick={() => onStatus(item.id, item.access_status === 'active' ? 'inactive' : 'active')}>{item.access_status === 'active' ? 'Pause' : 'Activate'}</button></li>)}</ul>
  </div>;
}

function SettingsSection({ settings }: { settings: AdminSetting[] }) {
  return <div className="report-card">
    <h3>Platform settings</h3>
    {!settings.length && <p>No settings configured yet.</p>}
    <ul>{settings.map(setting => <li key={setting.key}>{setting.key}: {JSON.stringify(setting.value)}</li>)}</ul>
  </div>;
}

function AdminsSection({ users, inviteEmail, inviteName, invitePassword, onEmail, onName, onPassword, onInvite }: { users: AdminUser[]; inviteEmail: string; inviteName: string; invitePassword: string; onEmail: (value: string) => void; onName: (value: string) => void; onPassword: (value: string) => void; onInvite: () => void }) {
  return <div className="page-stack">
    <section className="form-card">
      <h3>Create admin</h3>
      <label>Name<input value={inviteName} onChange={event => onName(event.target.value)} /></label>
      <label>Email<input type="email" value={inviteEmail} onChange={event => onEmail(event.target.value)} /></label>
      <label>Temporary password<input type="password" value={invitePassword} onChange={event => onPassword(event.target.value)} /></label>
      <button className="primary-button" onClick={onInvite}>Create Admin</button>
    </section>
    <ListCard title="Admin accounts" items={users.map(user => `${user.full_name} - ${user.email} - ${user.role}`)} empty="No admin accounts found." />
  </div>;
}

function ReportsSection({ assessments, llmEvents, logs }: { assessments: StoredAssessmentResult[]; llmEvents: LLMEvent[]; logs: AdminAuditLog[] }) {
  return <div className="page-stack">
    <div className="admin-grid">
      <ListCard title="Learning activity" items={assessments.map(item => `${item.student_name || 'Student'} - ${item.subject} - ${item.estimated_level}`)} empty="No assessment activity yet." />
      <ListCard title="AI usage" items={llmEvents.map(event => `${event.provider} - ${event.model} - ${event.purpose}${event.fallback_used ? ' - fallback used' : ''}`)} empty="No AI usage events yet." />
      <ListCard title="Audit logs" items={logs.map(log => `${log.created_at || ''} - ${log.action} - ${log.target_type}`)} empty="No audit logs yet." />
    </div>
  </div>;
}

function ListCard({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return <div className="report-card">
    <h3>{title}</h3>
    {!items.length && <p>{empty}</p>}
    {!!items.length && <ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>}
  </div>;
}

function titleFor(section: AdminSection): string {
  return {
    dashboard: 'Admin dashboard',
    users: 'User management',
    subscriptions: 'Subscription management',
    reports: 'Reports and audit logs',
    settings: 'Platform settings',
    admins: 'Admin management',
  }[section];
}

export type { AdminSection };
