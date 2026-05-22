import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { BarChart3, Bot, BookOpen, Calendar, Download, FileText, Settings, ShieldCheck, Users, WalletCards } from 'lucide-react';
import { InfoCard } from '../components/InfoCard';
import { NavItem } from '../components/NavItem';
import { SectionHeader } from '../components/SectionHeader';
import { apiGet, apiPatch, apiPost } from '../lib/api';
import { AdminAuditLog, AdminLearningActivity, AdminOverview, AdminSetting, AdminSubscription, AdminUser, LLMEvent, StoredAssessmentResult } from '../types';
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
  const [learningActivity, setLearningActivity] = useState<AdminLearningActivity[]>([]);
  const [reportAssessments, setReportAssessments] = useState<StoredAssessmentResult[]>([]);
  const [reportLlmEvents, setReportLlmEvents] = useState<LLMEvent[]>([]);
  const [settings, setSettings] = useState<AdminSetting[]>([]);
  const [search, setSearch] = useState('');
  const [userRoleFilter, setUserRoleFilter] = useState('All');
  const [userStatusFilter, setUserStatusFilter] = useState('All');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [updatingUserId, setUpdatingUserId] = useState('');
  const [updatingSubscriptionId, setUpdatingSubscriptionId] = useState('');
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
          const data = await apiGet<{ learning_activity: AdminLearningActivity[]; assessments: StoredAssessmentResult[]; llm_events: LLMEvent[]; audit_logs: AdminAuditLog[] }>('/api/admin/reports', authHeaders);
          if (!cancelled) {
            setLearningActivity(data.learning_activity || []);
            setReportAssessments(data.assessments || []);
            setReportLlmEvents(data.llm_events || []);
            setAuditLogs(data.audit_logs || []);
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
    const previous = users;
    setUpdatingUserId(userId);
    setError('');
    setUsers(prev => prev.map(user => user.id === userId ? { ...user, status } : user));
    try {
      const updated = await apiPatch<AdminUser>(`/api/admin/users/${userId}/status`, { status, reason: `Changed from admin ${profile.email}` }, authHeaders);
      setUsers(prev => prev.map(user => user.id === userId ? { ...user, ...updated } : user));
    } catch (updateError) {
      setUsers(previous);
      setError(updateError instanceof Error ? updateError.message : 'Could not update user status.');
    } finally {
      setUpdatingUserId('');
    }
  }

  async function updateSubscription(subscriptionId: string, accessStatus: AdminSubscription['access_status']) {
    setUpdatingSubscriptionId(subscriptionId);
    setSubscriptions(prev => prev.map(item => item.id === subscriptionId ? { ...item, access_status: accessStatus } : item));
    try {
      const updated = await apiPatch<AdminSubscription>(`/api/admin/subscriptions/${subscriptionId}`, {
        access_status: accessStatus,
        plan_name: 'Phase 1 MVP',
        reason: `Changed from admin ${profile.email}`,
      }, authHeaders);
      setSubscriptions(prev => prev.map(item => item.id === subscriptionId ? { ...item, ...updated, child_name: item.child_name, grade_level: item.grade_level } : item));
    } catch (updateError) {
      const data = await apiGet<{ subscriptions: AdminSubscription[] }>('/api/admin/subscriptions', authHeaders);
      setSubscriptions(data.subscriptions);
      setError(updateError instanceof Error ? updateError.message : 'Could not update subscription.');
    } finally {
      setUpdatingSubscriptionId('');
    }
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

  async function updateSetting(key: string, value: Record<string, unknown>, reason: string) {
    const updated = await apiPatch<AdminSetting>(`/api/admin/settings/${encodeURIComponent(key)}`, { value, reason }, authHeaders);
    setSettings(prev => {
      const exists = prev.some(setting => setting.key === updated.key);
      return exists ? prev.map(setting => setting.key === updated.key ? updated : setting) : [...prev, updated];
    });
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
      {loading && <p className="muted-copy">{section === 'reports' && learningActivity.length ? 'Refreshing report data...' : 'Loading admin data...'}</p>}
      {section === 'dashboard' && overview && <Dashboard overview={overview} />}
      {section === 'users' && <UsersSection users={users} currentUser={profile} search={search} roleFilter={userRoleFilter} statusFilter={userStatusFilter} updatingId={updatingUserId} onSearch={setSearch} onRoleFilter={setUserRoleFilter} onStatusFilter={setUserStatusFilter} onStatus={updateUserStatus} />}
      {section === 'subscriptions' && <SubscriptionsSection subscriptions={subscriptions} updatingId={updatingSubscriptionId} onStatus={updateSubscription} />}
      {section === 'reports' && <ReportsSection learningActivity={learningActivity} assessments={reportAssessments} llmEvents={reportLlmEvents} logs={auditLogs} />}
      {section === 'settings' && <SettingsSection settings={settings} onUpdate={updateSetting} />}
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

function UsersSection({
  users,
  currentUser,
  search,
  roleFilter,
  statusFilter,
  updatingId,
  onSearch,
  onRoleFilter,
  onStatusFilter,
  onStatus,
}: {
  users: AdminUser[];
  currentUser: ProfileResponse;
  search: string;
  roleFilter: string;
  statusFilter: string;
  updatingId: string;
  onSearch: (value: string) => void;
  onRoleFilter: (value: string) => void;
  onStatusFilter: (value: string) => void;
  onStatus: (id: string, status: AdminUser['status']) => void;
}) {
  const filteredUsers = users.filter(user => {
    const term = search.trim().toLowerCase();
    const matchesSearch = !term || user.full_name.toLowerCase().includes(term) || user.email.toLowerCase().includes(term);
    const matchesRole = roleFilter === 'All' || user.role === roleFilter;
    const matchesStatus = statusFilter === 'All' || user.status === statusFilter;
    return matchesSearch && matchesRole && matchesStatus;
  });
  return <div className="page-stack">
    <div className="report-filter-card users-filter-card">
      <label>Search users<input value={search} onChange={event => onSearch(event.target.value)} placeholder="Name or email" /></label>
      <label>Role<select value={roleFilter} onChange={event => onRoleFilter(event.target.value)}><option>All</option><option value="parent">Parent</option><option value="student">Student</option><option value="admin">Admin</option><option value="super_admin">Super Admin</option></select></label>
      <label>Status<select value={statusFilter} onChange={event => onStatusFilter(event.target.value)}><option>All</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="inactive">Inactive</option></select></label>
    </div>
    <section className="report-card admin-report-table-card">
      <div className="admin-table-heading">
        <h3><Users />User accounts</h3>
        <span className="muted-copy">Showing {filteredUsers.length} of {users.length}</span>
      </div>
      {!filteredUsers.length && <p className="muted-copy table-empty-note">No users match these filters.</p>}
      {!!filteredUsers.length && <div className="admin-table-scroll">
        <table className="admin-table">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>{filteredUsers.map(user => {
            const isSelf = user.id === currentUser.id;
            const targetIsAdmin = user.role === 'admin' || user.role === 'super_admin';
            const currentIsSuperAdmin = currentUser.role === 'super_admin';
            const canManage = !isSelf && (!targetIsAdmin || currentIsSuperAdmin);
            const label = isSelf ? 'Current admin' : targetIsAdmin && !currentIsSuperAdmin ? 'Admin protected' : 'Locked';
            const updating = updatingId === user.id;
            return <tr key={user.id}>
              <td><StudentCell name={user.full_name} detail={user.role} /></td>
              <td>{user.email}</td>
              <td><span className="admin-badge purple">{user.role.replace('_', ' ')}</span></td>
              <td><span className={`admin-badge ${user.status === 'active' ? 'green' : 'gold'}`}>{user.status}</span></td>
              <td>{canManage ? <button className="secondary-button compact" disabled={updating} onClick={() => onStatus(user.id, user.status === 'active' ? 'suspended' : 'active')}>{updating ? 'Saving...' : user.status === 'active' ? 'Suspend' : 'Reactivate'}</button> : <span className="muted-copy">{label}</span>}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
    </section>
  </div>;
}

function SubscriptionsSection({ subscriptions, updatingId, onStatus }: { subscriptions: AdminSubscription[]; updatingId: string; onStatus: (id: string, status: AdminSubscription['access_status']) => void }) {
  const activeCount = subscriptions.filter(item => item.access_status === 'active').length;
  const trialCount = subscriptions.filter(item => item.access_status === 'trial').length;
  const pastDueCount = subscriptions.filter(item => item.access_status === 'past_due').length;
  const inactiveCount = subscriptions.filter(item => item.access_status === 'inactive').length;
  return <div className="page-stack">
    <div className="report-metric-grid">
      <ReportMetric icon={<WalletCards />} title="Active" value={activeCount} accent="green" />
      <ReportMetric icon={<Calendar />} title="Trial" value={trialCount} accent="purple" />
      <ReportMetric icon={<ShieldCheck />} title="Past Due" value={pastDueCount} accent="gold" />
      <ReportMetric icon={<FileText />} title="Inactive" value={inactiveCount} accent="blue" />
    </div>
    <section className="report-card admin-report-table-card">
      <div className="admin-table-heading">
        <h3><WalletCards />Subscriptions</h3>
        <span className="muted-copy">Showing {subscriptions.length} live records</span>
      </div>
      {!subscriptions.length && <p className="muted-copy table-empty-note">No subscriptions found yet.</p>}
      {!!subscriptions.length && <div className="admin-table-scroll">
        <table className="admin-table">
          <thead><tr><th>Student</th><th>Plan</th><th>Grade</th><th>Status</th><th>Ends</th><th>Action</th></tr></thead>
          <tbody>{subscriptions.map(item => {
            const nextStatus = item.access_status === 'active' ? 'inactive' : 'active';
            const updating = updatingId === item.id;
            const endDate = item.current_period_ends_at || item.trial_ends_at;
            return <tr key={item.id}>
              <td><StudentCell name={item.child_name || 'Student'} detail={shortId(item.child_id)} /></td>
              <td>{item.plan_name || 'No plan set'}</td>
              <td>{item.grade_level || 'Not set'}</td>
              <td><span className={`admin-badge ${subscriptionBadgeClass(item.access_status)}`}>{subscriptionStatusLabel(item.access_status)}</span></td>
              <td>{endDate ? formatDateTime(endDate) : 'Not set'}</td>
              <td><button className="secondary-button compact" disabled={updating} onClick={() => onStatus(item.id, nextStatus)}>{updating ? 'Saving...' : item.access_status === 'active' ? 'Pause' : 'Activate'}</button></td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
    </section>
  </div>;
}

function SettingsSection({ settings, onUpdate }: { settings: AdminSetting[]; onUpdate: (key: string, value: Record<string, unknown>, reason: string) => Promise<void> }) {
  const adminSecurity = settings.find(setting => setting.key === 'admin_security');
  const platform = settings.find(setting => setting.key === 'platform');
  const [admin2faRequired, setAdmin2faRequired] = useState(Boolean(adminSecurity?.value.admin_2fa_required));
  const [sessionMinutes, setSessionMinutes] = useState(Number(adminSecurity?.value.session_minutes || 60));
  const [lockoutMinutes, setLockoutMinutes] = useState(Number(adminSecurity?.value.failed_login_lockout_minutes || 15));
  const [maintenanceMode, setMaintenanceMode] = useState(Boolean(platform?.value.maintenance_mode));
  const [savingKey, setSavingKey] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    setAdmin2faRequired(Boolean(adminSecurity?.value.admin_2fa_required));
    setSessionMinutes(Number(adminSecurity?.value.session_minutes || 60));
    setLockoutMinutes(Number(adminSecurity?.value.failed_login_lockout_minutes || 15));
    setMaintenanceMode(Boolean(platform?.value.maintenance_mode));
  }, [adminSecurity?.value, platform?.value]);

  async function saveAdminSecurity() {
    setSavingKey('admin_security');
    setMessage('');
    try {
      await onUpdate('admin_security', {
        admin_2fa_required: admin2faRequired,
        session_minutes: Math.max(5, Math.min(1440, sessionMinutes || 60)),
        failed_login_lockout_minutes: Math.max(1, Math.min(1440, lockoutMinutes || 15)),
      }, 'Admin security settings updated from admin console.');
      setMessage('Admin security settings saved.');
    } finally {
      setSavingKey('');
    }
  }

  async function savePlatform() {
    setSavingKey('platform');
    setMessage('');
    try {
      await onUpdate('platform', {
        maintenance_mode: maintenanceMode,
      }, 'Platform settings updated from admin console.');
      setMessage('Platform settings saved.');
    } finally {
      setSavingKey('');
    }
  }

  return <div className="page-stack">
    {message && <p className="success-note">{message}</p>}
    <div className="settings-card-grid">
      <SettingGroup
        icon={<ShieldCheck />}
        title="Admin Security"
        desc="Controls that protect staff-only access."
        action={<button className="primary-button compact-admin-action" onClick={saveAdminSecurity} disabled={savingKey === 'admin_security'}>{savingKey === 'admin_security' ? 'Saving...' : 'Save Security'}</button>}
      >
        <SettingToggle label="Two-factor requirement" note="Require stronger verification for admin accounts." checked={admin2faRequired} onChange={setAdmin2faRequired} />
        <SettingNumber label="Session timeout" note="Recommended admin session length in minutes." value={sessionMinutes} min={5} max={1440} onChange={setSessionMinutes} suffix="minutes" />
        <SettingNumber label="Failed login lockout" note="Temporary lockout after repeated failed attempts." value={lockoutMinutes} min={1} max={1440} onChange={setLockoutMinutes} suffix="minutes" />
      </SettingGroup>
      <SettingGroup
        icon={<Settings />}
        title="Platform Controls"
        desc="High-level controls for platform availability."
        action={<button className="primary-button compact-admin-action" onClick={savePlatform} disabled={savingKey === 'platform'}>{savingKey === 'platform' ? 'Saving...' : 'Save Platform'}</button>}
      >
        <SettingToggle label="Maintenance mode" note={maintenanceMode ? 'Users may be blocked while maintenance mode is active.' : 'Platform is open for normal use.'} checked={maintenanceMode} onChange={setMaintenanceMode} />
      </SettingGroup>
    </div>
    <section className="report-card admin-settings-note">
      <h3>Deployment note</h3>
      <p>These settings are read from the database. Changes that affect login sessions or two-factor authentication must also match the production auth provider configuration.</p>
    </section>
  </div>;
}

function SettingGroup({ icon, title, desc, action, children }: { icon: ReactNode; title: string; desc: string; action: ReactNode; children: ReactNode }) {
  return <section className="report-card setting-group-card">
    <div className="setting-group-header">
      <div className="setting-group-icon">{icon}</div>
      <div>
        <h3>{title}</h3>
        <p>{desc}</p>
      </div>
      {action}
    </div>
    <div className="setting-row-list">
      {children}
    </div>
  </section>;
}

function SettingToggle({ label, note, checked, onChange }: { label: string; note: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <div className="setting-row">
    <div>
      <strong>{label}</strong>
      <span>{note}</span>
    </div>
    <label className="admin-toggle" aria-label={label}>
      <input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} />
      <span>{checked ? 'On' : 'Off'}</span>
    </label>
  </div>;
}

function SettingNumber({ label, note, value, min, max, suffix, onChange }: { label: string; note: string; value: number; min: number; max: number; suffix: string; onChange: (value: number) => void }) {
  return <div className="setting-row">
    <div>
      <strong>{label}</strong>
      <span>{note}</span>
    </div>
    <label className="setting-number-control">
      <input type="number" min={min} max={max} value={value} onChange={event => onChange(Number(event.target.value))} />
      <span>{suffix}</span>
    </label>
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

function ReportsSection({ learningActivity, assessments, llmEvents, logs }: { learningActivity: AdminLearningActivity[]; assessments: StoredAssessmentResult[]; llmEvents: LLMEvent[]; logs: AdminAuditLog[] }) {
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({});
  const [studentFilter, setStudentFilter] = useState('');
  const [subjectFilter, setSubjectFilter] = useState('All');
  const [gradeFilter, setGradeFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const subjects = useMemo(() => uniqueOptions(learningActivity.map(item => item.subject).filter(Boolean)), [learningActivity]);
  const grades = useMemo(() => uniqueOptions(learningActivity.map(item => item.grade_level).filter(Boolean)), [learningActivity]);
  const statuses = useMemo(() => uniqueOptions(learningActivity.map(item => item.status).filter(Boolean)), [learningActivity]);

  useEffect(() => {
    if (subjectFilter !== 'All' && !subjects.includes(subjectFilter)) setSubjectFilter('All');
    if (gradeFilter !== 'All' && !grades.includes(gradeFilter)) setGradeFilter('All');
    if (statusFilter !== 'All' && !statuses.includes(statusFilter)) setStatusFilter('All');
  }, [gradeFilter, grades, statusFilter, statuses, subjectFilter, subjects]);

  const filteredLearning = learningActivity.filter(row => {
    const matchesStudent = !studentFilter.trim() || row.student_name.toLowerCase().includes(studentFilter.trim().toLowerCase());
    const matchesSubject = subjectFilter === 'All' || row.subject === subjectFilter;
    const matchesGrade = gradeFilter === 'All' || row.grade_level === gradeFilter;
    const matchesStatus = statusFilter === 'All' || row.status === statusFilter;
    return matchesStudent && matchesSubject && matchesGrade && matchesStatus;
  });
  const hasAnyReportData = learningActivity.length || llmEvents.length || logs.length;
  const dataRange = reportDateRange([...learningActivity.map(item => item.latest_activity_at), ...llmEvents.map(item => item.created_at), ...logs.map(item => item.created_at)]);
  const activeStudents = learningActivity.filter(item => item.status === 'active').length;
  const filtersActive = Boolean(studentFilter.trim()) || subjectFilter !== 'All' || gradeFilter !== 'All' || statusFilter !== 'All';
  function clearFilters() {
    setStudentFilter('');
    setSubjectFilter('All');
    setGradeFilter('All');
    setStatusFilter('All');
  }
  function toggleTable(title: string) {
    setExpandedTables(prev => ({ ...prev, [title]: !prev[title] }));
  }
  return <div className="page-stack">
    {!hasAnyReportData && <div className="report-card"><h3>No report data yet</h3><p className="muted-copy">Reports will populate when students, assessments, AI usage, or admin actions are saved.</p></div>}
    <div className="report-actions">
      <button className="secondary-button"><Calendar /> {dataRange}</button>
      <button className="secondary-button" onClick={() => exportReportCsv(assessments, llmEvents, logs)}><Download /> Export Report</button>
    </div>
    <div className="report-metric-grid">
      <ReportMetric icon={<BookOpen />} title="Total Students" value={learningActivity.length} accent="purple" />
      <ReportMetric icon={<Bot />} title="AI Requests" value={llmEvents.length} accent="blue" />
      <ReportMetric icon={<Users />} title="Active Students" value={activeStudents} accent="green" />
      <ReportMetric icon={<ShieldCheck />} title="Admin Actions" value={logs.length} accent="gold" />
    </div>
    <div className="report-filter-card">
      <label>Search student<input value={studentFilter} onChange={event => setStudentFilter(event.target.value)} placeholder="Student name" /></label>
      <label>Subject<select value={subjectFilter} onChange={event => setSubjectFilter(event.target.value)} disabled={!subjects.length}><option>All</option>{subjects.map(subject => <option key={subject}>{subject}</option>)}</select></label>
      <label>Grade<select value={gradeFilter} onChange={event => setGradeFilter(event.target.value)} disabled={!grades.length}><option>All</option>{grades.map(grade => <option key={grade}>{grade}</option>)}</select></label>
      <label>Status<select value={statusFilter} onChange={event => setStatusFilter(event.target.value)} disabled={!statuses.length}><option>All</option>{statuses.map(status => <option key={status} value={status}>{statusLabel(status)}</option>)}</select></label>
      {filtersActive && <div className="report-filter-actions"><button className="secondary-button compact" onClick={clearFilters}>Clear Filters</button></div>}
    </div>
    <ReportTableCard
      title="Learning activity"
      icon={<BookOpen />}
      columns={['Student', 'Subject', 'Grade', 'Status', 'Last Activity']}
      empty={learningActivity.length ? 'No students match these filters.' : 'No student profiles found yet.'}
      expanded={Boolean(expandedTables['Learning activity'])}
      onToggle={() => toggleTable('Learning activity')}
      rows={filteredLearning.map(item => [
        <StudentCell name={item.student_name} detail={item.latest_level || item.latest_activity_type} />,
        item.subject,
        item.grade_level,
        <span className={`admin-badge ${statusBadgeClass(item.status)}`}>{statusLabel(item.status)}</span>,
        formatDateTime(item.latest_activity_at),
      ])}
    />
    <div className="report-split-grid">
      <ReportTableCard
        title="AI usage"
        icon={<Bot />}
        columns={['Provider', 'Model', 'Feature Used', 'Date / Time']}
        empty="No AI usage events yet."
        expanded={Boolean(expandedTables['AI usage'])}
        onToggle={() => toggleTable('AI usage')}
        rows={llmEvents.map(event => [
          event.provider,
          event.model,
          <span className="admin-badge purple">{event.purpose}</span>,
          formatDateTime(event.created_at),
        ])}
      />
      <ReportTableCard
        title="Audit logs"
        icon={<ShieldCheck />}
        columns={['Time', 'Admin', 'Action', 'Details']}
        empty="No audit logs yet."
        expanded={Boolean(expandedTables['Audit logs'])}
        onToggle={() => toggleTable('Audit logs')}
        rows={logs.map(log => [
          formatDateTime(log.created_at),
          shortId(log.admin_user_id),
          <span className="admin-badge gold">{humanAction(log.action)}</span>,
          `${log.target_type}${log.target_id ? ` - ${shortId(log.target_id)}` : ''}`,
        ])}
      />
    </div>
  </div>;
}

function ReportMetric({ icon, title, value, accent }: { icon: ReactNode; title: string; value: number; accent: 'purple' | 'blue' | 'green' | 'gold' }) {
  return <div className="report-metric-card">
    <div className={`report-metric-icon ${accent}`}>{icon}</div>
    <div>
      <span>{title}</span>
      <strong>{value}</strong>
      <small>Live platform snapshot</small>
    </div>
  </div>;
}

function ReportTableCard({ title, icon, columns, rows, empty, expanded, onToggle }: { title: string; icon: ReactNode; columns: string[]; rows: ReactNode[][]; empty: string; expanded: boolean; onToggle: () => void }) {
  const visibleRows = expanded ? rows : rows.slice(0, 8);
  return <section className="report-card admin-report-table-card">
    <div className="admin-table-heading">
      <h3>{icon}{title}</h3>
      {rows.length > 8 && <button className="secondary-button compact" onClick={onToggle}>{expanded ? 'Show Less' : 'View All'}</button>}
    </div>
    {!rows.length && <p className="muted-copy">{empty}</p>}
    {!!rows.length && <div className="admin-table-scroll">
      <table className="admin-table">
        <thead><tr>{columns.map(column => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>{visibleRows.map((row, rowIndex) => <tr key={`${title}-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${title}-${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>)}</tbody>
      </table>
    </div>}
    {!!rows.length && <p className="admin-table-footnote">Showing {visibleRows.length} of {rows.length} live records.</p>}
  </section>;
}

function StudentCell({ name, detail }: { name: string; detail?: string }) {
  const initials = name.split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase() || 'ST';
  return <div className="admin-student-cell"><span>{initials}</span><div><strong>{name}</strong><small>{detail || 'Learning activity'}</small></div></div>;
}

function formatDateTime(value?: string | null): string {
  if (!value) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function humanAction(value: string): string {
  return value.split('_').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    active: 'Active',
    inactive: 'Inactive',
    pending_consent: 'Pending consent',
    suspended: 'Suspended',
  };
  return labels[value] || humanAction(value);
}

function statusBadgeClass(value: string): 'green' | 'gold' | 'purple' {
  if (value === 'active') return 'green';
  if (value === 'inactive' || value === 'suspended') return 'gold';
  return 'purple';
}

function subscriptionStatusLabel(value: AdminSubscription['access_status']): string {
  const labels: Record<AdminSubscription['access_status'], string> = {
    active: 'Active',
    trial: 'Trial',
    inactive: 'Inactive',
    past_due: 'Past due',
  };
  return labels[value] || humanAction(value);
}

function subscriptionBadgeClass(value: AdminSubscription['access_status']): 'green' | 'gold' | 'purple' {
  if (value === 'active') return 'green';
  if (value === 'past_due' || value === 'inactive') return 'gold';
  return 'purple';
}

function shortId(value?: string): string {
  if (!value) return 'System';
  return value.length > 10 ? `${value.slice(0, 8)}...` : value;
}

function reportDateRange(values: Array<string | undefined | null>): string {
  const dates: Date[] = [];
  values.forEach(value => {
    if (!value) return;
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) dates.push(date);
  });
  dates.sort((a, b) => a.getTime() - b.getTime());
  if (!dates.length) return 'Latest available records';
  const format = (date: Date) => date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  return `${format(dates[0])} - ${format(dates[dates.length - 1])}`;
}

function uniqueOptions(values: string[]): string[] {
  return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b));
}

function exportReportCsv(assessments: StoredAssessmentResult[], llmEvents: LLMEvent[], logs: AdminAuditLog[]) {
  const rows = [
    ['Section', 'Primary', 'Secondary', 'Status/Type', 'Date'],
    ...assessments.map(item => ['Learning activity', item.student_name || 'Student', item.subject, item.estimated_level, item.created_at || '']),
    ...llmEvents.map(event => ['AI usage', event.provider, event.model, event.purpose, event.created_at || '']),
    ...logs.map(log => ['Audit log', log.action, log.target_type, log.target_id || '', log.created_at || '']),
  ];
  const csv = rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `msalisia-admin-report-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
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
