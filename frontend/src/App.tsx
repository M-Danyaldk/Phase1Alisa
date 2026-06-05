import { useEffect, useState } from 'react';
import { initialStudent } from './constants';
import { checkHealth } from './lib/api';
import { AdminOnly, ChildOnly, ParentOnly } from './guards/AccessGuards';
import { getStudentMe, studentLogout } from './lib/api/studentAuth';
import { childToStudent, profileToStudent } from './lib/studentProfile';
import { ChildShell } from './layouts/ChildShell';
import { ParentShell } from './layouts/ParentShell';
import { AssessmentView } from './views/AssessmentView';
import { AdminView } from './views/AdminView';
import type { AdminSection } from './views/AdminView';
import { BillingView } from './views/BillingView';
import { FutureView } from './views/FutureView';
import { HomeView } from './views/HomeView';
import { HomeworkView } from './views/HomeworkView';
import { LearningView } from './views/LearningView';
import { ManageChildrenView } from './views/ManageChildrenView';
import { ParentOnboardingView } from './views/ParentOnboardingView';
import { ParentDashboardView } from './views/ParentDashboardView';
import { CompliancePage, PrelaunchLandingView } from './views/PrelaunchLandingView';
import { ProfileView } from './views/ProfileView';
import { ReportsView } from './views/ReportsView';
import { ChildView, ParentView, StudentProfile } from './types';
import { StudentLoginView } from './views/StudentLoginView';
import { Login } from './pages/Login';
import { Signup } from './pages/Signup';
import { VerifyEmail } from './pages/VerifyEmail';
import { AuthSessionResponse, PendingVerification, ProfileResponse } from './types/auth';
import { StudentMe, StudentSession } from './types/studentSession';
import { getCurrentProfile } from './lib/api/auth';
import { listChildren } from './lib/api/children';
import { ChildProfile } from './types/childProfile';

type AuthView = 'login' | 'signup' | 'verify';

const AUTH_SESSION_KEY = 'msalisia-auth-session';
const STUDENT_SESSION_KEY = 'msalisia-student-session';
const REFERRAL_CODE_KEY = 'msalisia-referral-code';

function readStoredJson<T>(key: string): T | null {
  const stored = localStorage.getItem(key);
  if (!stored) return null;
  try {
    return JSON.parse(stored) as T;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

export function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname.replace(/\/+$/, '') || '/');
  const [parentView, setParentView] = useState<ParentView>('home');
  const [childView, setChildView] = useState<ChildView>('home');
  const [student, setStudent] = useState<StudentProfile>(initialStudent);
  const [connected, setConnected] = useState<'checking' | 'online' | 'offline'>('checking');
  const [authView, setAuthView] = useState<AuthView>('login');
  const [pendingVerification, setPendingVerification] = useState<PendingVerification | null>(null);
  const [session, setSession] = useState<AuthSessionResponse | null>(() => readStoredJson<AuthSessionResponse>(AUTH_SESSION_KEY));
  const [profileLoading, setProfileLoading] = useState(() => Boolean(localStorage.getItem(AUTH_SESSION_KEY)));
  const [profileError, setProfileError] = useState('');
  const [currentProfile, setCurrentProfile] = useState<ProfileResponse | null>(null);
  const [children, setChildren] = useState<ChildProfile[]>([]);
  const [selectedChildId, setSelectedChildId] = useState('');
  const [childrenLoading, setChildrenLoading] = useState(() => Boolean(localStorage.getItem(AUTH_SESSION_KEY)));
  const [childrenError, setChildrenError] = useState('');
  const [showParentOnboarding, setShowParentOnboarding] = useState(false);
  const [paidCheckoutRequiredAfterSignup, setPaidCheckoutRequiredAfterSignup] = useState(false);
  const [studentSession, setStudentSession] = useState<StudentSession | null>(() => readStoredJson<StudentSession>(STUDENT_SESSION_KEY));
  const [studentMe, setStudentMe] = useState<StudentMe | null>(null);
  const [studentSessionLoading, setStudentSessionLoading] = useState(() => Boolean(localStorage.getItem(STUDENT_SESSION_KEY)));
  const [studentSessionError, setStudentSessionError] = useState('');
  const [studentSessionNotice, setStudentSessionNotice] = useState('');
  const [childDashboardNotice, setChildDashboardNotice] = useState('');

  useEffect(() => {
    checkHealth().then(() => setConnected('online')).catch(() => setConnected('offline'));
  }, []);

  useEffect(() => {
    function syncPathname() {
      setPathname(window.location.pathname.replace(/\/+$/, '') || '/');
    }
    window.addEventListener('popstate', syncPathname);
    return () => window.removeEventListener('popstate', syncPathname);
  }, []);

  useEffect(() => {
    if (pathname.startsWith('/ref/')) {
      const code = pathname.split('/')[2]?.trim();
      if (code) localStorage.setItem(REFERRAL_CODE_KEY, code);
      setAuthView('signup');
      navigate('/signup');
      return;
    }
    if (pathname === '/login') setAuthView('login');
    if (pathname === '/signup') setAuthView('signup');
    if (pathname === '/verify') setAuthView('verify');
  }, [pathname]);

  useEffect(() => {
    if (!session || pathname === '/' || pathname === '/student' || pathname.startsWith('/admin') || pathname === '/login' || pathname === '/signup' || pathname === '/verify') {
      return;
    }
    if (pathname === '/dashboard') setParentView('home');
    if (pathname === '/children') setParentView('children');
    if (pathname === '/reports') setParentView('reports');
    if (pathname === '/billing' || pathname === '/billing/success' || pathname === '/billing/cancel') setParentView('billing');
    if (pathname === '/settings') setParentView('profile');
    if (pathname === '/future') setParentView('future');
  }, [pathname, session]);

  function navigate(path: string) {
    window.history.pushState(null, '', path);
    setPathname(path.replace(/\/+$/, '') || '/');
  }

  function changeParentView(view: ParentView) {
    setParentView(view);
    navigate(parentPathForView(view));
  }

  async function loadProfile(nextSession: AuthSessionResponse) {
    if (!nextSession.access_token) {
      throw new Error('Missing session token. Please log in again.');
    }
    const profile = await getCurrentProfile(nextSession.access_token);
    setCurrentProfile(profile);
    setStudent(profileToStudent(profile));
    return profile;
  }

  async function loadChildren(nextSession: AuthSessionResponse) {
    if (!nextSession.access_token) return [];
    const records = await listChildren(nextSession.access_token);
    setChildren(records);
    setSelectedChildId(prev => prev && records.some(child => child.id === prev) ? prev : preferredChildId(records));
    if (!records.length) {
      setShowParentOnboarding(true);
    }
    return records;
  }

  function applyProfile(profile: ProfileResponse) {
    setCurrentProfile(profile);
    setStudent(profileToStudent(profile));
  }

  async function completeAuth(nextSession: AuthSessionResponse) {
    localStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(nextSession));
    setProfileLoading(true);
    setChildrenLoading(true);
    setProfileError('');
    setChildrenError('');
    let profile: ProfileResponse;
    try {
      profile = await loadProfile(nextSession);
    } catch (error) {
      localStorage.removeItem(AUTH_SESSION_KEY);
      setProfileError(error instanceof Error ? error.message : 'Could not load profile. Please log in again.');
      setSession(null);
      setAuthView('login');
      setProfileLoading(false);
      setChildrenLoading(false);
      return;
    }
    const isAdmin = profile.role === 'admin' || profile.role === 'super_admin';
    if (isAdmin) {
      setSession(nextSession);
      setPendingVerification(null);
      setAuthView('login');
      setProfileLoading(false);
      setChildrenLoading(false);
      navigate('/admin/dashboard');
      return;
    }
    let loadedChildren: ChildProfile[] = [];
    try {
      loadedChildren = await loadChildren(nextSession);
    } catch (error) {
      setChildren([]);
      setSelectedChildId('');
      setShowParentOnboarding(false);
      setChildrenError(error instanceof Error ? error.message : 'Could not load child profiles.');
    }
    const paidCheckoutRequired = nextSession.paid_checkout_required === true;
    setPaidCheckoutRequiredAfterSignup(paidCheckoutRequired);
    setSession(nextSession);
    setPendingVerification(null);
    setAuthView('login');
    setParentView(paidCheckoutRequired && loadedChildren.length ? 'billing' : 'home');
    setChildView('home');
    setProfileLoading(false);
    setChildrenLoading(false);
    navigate(paidCheckoutRequired && loadedChildren.length ? '/billing' : '/dashboard');
  }

  function logout() {
    localStorage.removeItem(AUTH_SESSION_KEY);
    setSession(null);
    setStudent(initialStudent);
    setCurrentProfile(null);
    setChildren([]);
    setSelectedChildId('');
    setChildrenError('');
    setShowParentOnboarding(false);
    setPaidCheckoutRequiredAfterSignup(false);
    setProfileError('');
    setParentView('home');
    setChildView('home');
    setAuthView('login');
  }

  function completeStudentLogin(nextSession: StudentSession) {
    const levels = nextSession.learning_levels || {};
    localStorage.setItem(STUDENT_SESSION_KEY, JSON.stringify(nextSession));
    setStudentSession(nextSession);
    setStudentSessionNotice('');
    setStudentSessionError('');
    setChildDashboardNotice('');
    setStudentMe({
      role: 'child',
      child_id: nextSession.child_id,
      parent_id: nextSession.parent_id,
      student_name: nextSession.student_name,
      grade_level: nextSession.grade_level,
      subjects: ['Math', 'ELA', 'Writing'],
      learning_levels: levels,
      access_allowed: nextSession.access_allowed ?? true,
      billing_status: nextSession.billing_status,
      blocked_reason: nextSession.blocked_reason,
      voice_allowed: nextSession.voice_allowed ?? false,
      child_blocked_message: nextSession.child_blocked_message,
      session_expires_at: nextSession.expires_at,
    });
    setChildView('home');
  }

  async function logoutStudent(notice = '') {
    const token = studentSession?.access_token;
    localStorage.removeItem(STUDENT_SESSION_KEY);
    setStudentSession(null);
    setStudentMe(null);
    setStudentSessionNotice(notice);
    setChildDashboardNotice('');
    setChildView('home');
    if (token) {
      try { await studentLogout(token); } catch { /* already cleared locally */ }
    }
  }

  useEffect(() => {
    if (!session) return;
    setProfileLoading(true);
    setChildrenLoading(true);
    setProfileError('');
    setChildrenError('');
    loadProfile(session)
      .catch(error => {
        localStorage.removeItem(AUTH_SESSION_KEY);
        setProfileError(error instanceof Error ? error.message : 'Could not load profile. Please log in again.');
        setSession(null);
        setAuthView('login');
      })
      .finally(() => setProfileLoading(false));
    loadChildren(session)
      .catch(error => {
        setChildrenError(error instanceof Error ? error.message : 'Could not load child profiles.');
      })
      .finally(() => setChildrenLoading(false));
  }, [session?.access_token]);

  useEffect(() => {
    if (!studentSession?.access_token) {
      setStudentSessionLoading(false);
      return;
    }
    setStudentSessionLoading(true);
    setStudentSessionError('');
    getStudentMe(studentSession.access_token)
      .then(setStudentMe)
      .catch(error => {
        localStorage.removeItem(STUDENT_SESSION_KEY);
        setStudentSession(null);
        setStudentMe(null);
        setStudentSessionNotice('');
        const message = error instanceof Error ? error.message : '';
        setStudentSessionError(message.includes('There is something your parent needs to take care of') ? message : 'Please log in again to open your classroom.');
      })
      .finally(() => setStudentSessionLoading(false));
  }, [studentSession?.access_token]);

  useEffect(() => {
    const selectedChild = children.find(child => child.id === selectedChildId);
    if (selectedChild) {
      setStudent(childToStudent(selectedChild));
    } else if (currentProfile) {
      setStudent(profileToStudent(currentProfile));
    }
  }, [children, currentProfile, selectedChildId]);

  function handleChildrenChanged(nextChildren: ChildProfile[], nextSelectedChildId?: string) {
    setChildren(nextChildren);
    const selected = nextSelectedChildId || selectedChildId;
    setSelectedChildId(selected && nextChildren.some(child => child.id === selected) ? selected : preferredChildId(nextChildren));
  }

  function handleSelectChild(childId: string) {
    setSelectedChildId(childId);
    const selectedChild = children.find(child => child.id === childId);
    if (selectedChild) setStudent(childToStudent(selectedChild));
  }

  function handleOnboardingChildCreated(child: ChildProfile) {
    setChildren(prev => [...prev, child]);
    setSelectedChildId(child.id);
  }

  const landingPath = pathname === '/';
  if (landingPath) {
    return <PrelaunchLandingView onNavigate={navigate} />;
  }

  if (pathname === '/privacy' || pathname === '/ai-disclosure' || pathname === '/data-deletion' || pathname === '/support') {
    const type = pathname.slice(1) as 'privacy' | 'ai-disclosure' | 'data-deletion' | 'support';
    return <CompliancePage type={type} onNavigate={navigate} />;
  }

  const adminPath = pathname === '/admin' || pathname.startsWith('/admin/');
  if (adminPath) {
    if (!session) {
      return <div className="auth-shell">
        <div className="auth-brand">
          <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
          <span>MsAlisia Admin</span>
        </div>
        <Login onLoggedIn={completeAuth} onSignup={() => setAuthView('signup')} />
        {profileError && <p className="error-note auth-error">{profileError}</p>}
      </div>;
    }
    if (profileLoading || !currentProfile) {
      return <div className="auth-shell">
        <div className="auth-panel">
          <div className="auth-heading">
            <span>Admin</span>
            <h2>Checking access</h2>
            <p>{profileError || 'We are verifying your admin permissions.'}</p>
          </div>
          {profileError && <button className="primary-button" onClick={logout}>Login Again</button>}
        </div>
      </div>;
    }
    const allowed = currentProfile.role === 'admin' || currentProfile.role === 'super_admin';
    if (!allowed) {
      return <div className="auth-shell">
        <div className="auth-panel">
          <div className="auth-heading">
            <span>Access denied</span>
            <h2>Admin permission is required</h2>
            <p>This account does not have access to the admin console.</p>
          </div>
          <button className="primary-button" onClick={logout}>Logout</button>
        </div>
      </div>;
    }
    const section = adminSectionFromPath(pathname);
    return <AdminOnly allowed>
      <AdminView
        accessToken={session.access_token || ''}
        profile={currentProfile}
        section={section}
        onSectionChange={(nextSection) => navigate(`/admin/${nextSection}`)}
        onLogout={logout}
      />
    </AdminOnly>;
  }

  const studentPath = pathname === '/student';
  if (studentPath) {
    if (studentSessionLoading) {
      return <div className="auth-shell">
        <div className="auth-panel">
          <div className="auth-heading">
            <span>Hey there!</span>
            <h2>Opening classroom</h2>
            <p>We are checking your student session.</p>
          </div>
        </div>
      </div>;
    }

    if (!studentSession || !studentMe) {
      return <>
        <StudentLoginView onLoggedIn={completeStudentLogin} notice={studentSessionNotice} />
        {studentSessionError && <p className="error-note auth-error">{studentSessionError}</p>}
      </>;
    }

    const levels = studentMe.learning_levels || {};
    const sessionStudent: StudentProfile = {
      name: studentMe.student_name,
      grade: Number(studentMe.grade_level.replace(/\D/g, '')) || 4,
      math_level: levels.Math || 'Not assessed yet',
      ela_level: levels.ELA || 'Not assessed yet',
      writing_level: levels.Writing || 'Not assessed yet',
      confidence: 'Ready to learn',
      focus_notes: 'Student login session',
      parent_notes: '',
    };
    const sessionChild: ChildProfile = {
      id: studentMe.child_id,
      parent_id: studentMe.parent_id,
      name: studentMe.student_name,
      grade_level: studentMe.grade_level,
      subjects: (studentMe.subjects as ChildProfile['subjects']) || ['Math', 'ELA', 'Writing'],
      status: 'active',
      parental_consent_accepted: true,
    };
    const childAccessBlocked = studentMe.access_allowed === false;
    const requireStudentRelogin = (message: string) => {
      void logoutStudent(message);
    };
    const childBlockedMessage = studentMe.child_blocked_message || 'Hi there! There is something your parent needs to take care of. Go find them and let them know — they will have you back learning in no time!';

    return <ChildShell
      child={sessionChild}
      view={childView}
      connected={connected}
      onViewChange={setChildView}
      onExit={() => logoutStudent()}
      exitLabel="Logout"
    >
      <ChildOnly allowed>
        {childAccessBlocked && <div className="page-stack narrow">
          <section className="report-card access-message">
            <h3>Almost ready</h3>
            <p>{childBlockedMessage}</p>
          </section>
        </div>}
        {!childAccessBlocked && childView === 'home' && <HomeView student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} studentSession notice={childDashboardNotice} setView={(view) => {
          setChildDashboardNotice('');
          if (view === 'learn' || view === 'assessments' || view === 'homework') setChildView(view);
        }} />}
        {!childAccessBlocked && childView === 'learn' && <LearningView key="student-learn" student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} studentSession voiceAllowed={studentMe.voice_allowed === true} onRequireRelogin={requireStudentRelogin} onInactivePause={(message) => {
          setChildDashboardNotice(message);
          setChildView('home');
        }} />}
        {!childAccessBlocked && childView === 'assessments' && <AssessmentView
          student={sessionStudent}
          setStudent={setStudent}
          childId={studentMe.child_id}
          accessToken={studentSession.access_token}
          studentSession
          onContinueLearning={() => setChildView('learn')}
          onBackToDashboard={() => setChildView('home')}
        />}
        {!childAccessBlocked && childView === 'practice-math' && <LearningView key="student-practice-math" student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} initialSubject="Math" studentSession voiceAllowed={studentMe.voice_allowed === true} onRequireRelogin={requireStudentRelogin} onInactivePause={(message) => {
          setChildDashboardNotice(message);
          setChildView('home');
        }} />}
        {!childAccessBlocked && childView === 'practice-ela' && <LearningView key="student-practice-ela" student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} initialSubject="ELA" studentSession voiceAllowed={studentMe.voice_allowed === true} onRequireRelogin={requireStudentRelogin} onInactivePause={(message) => {
          setChildDashboardNotice(message);
          setChildView('home');
        }} />}
        {!childAccessBlocked && childView === 'practice-writing' && <LearningView key="student-practice-writing" student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} initialSubject="Writing" studentSession voiceAllowed={studentMe.voice_allowed === true} onRequireRelogin={requireStudentRelogin} onInactivePause={(message) => {
          setChildDashboardNotice(message);
          setChildView('home');
        }} />}
        {!childAccessBlocked && childView === 'homework' && <HomeworkView student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} studentSession setView={setChildView} />}
      </ChildOnly>
    </ChildShell>;
  }

  const authPath = pathname === '/login' || pathname === '/signup' || pathname === '/verify';
  if (!session) {
    if (!authPath) {
      return <PrelaunchLandingView onNavigate={navigate} />;
    }
    return <div className="auth-shell">
      <div className="auth-brand">
        <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
        <span>MsAlisia</span>
      </div>
      {authView === 'login' && <Login onLoggedIn={completeAuth} onSignup={() => { setAuthView('signup'); navigate('/signup'); }} />}
      {authView === 'signup' && <Signup onLogin={() => { setAuthView('login'); navigate('/login'); }} onPendingVerification={(pending) => {
        setPendingVerification(pending);
        setAuthView('verify');
        navigate('/verify');
      }} />}
      {authView === 'verify' && pendingVerification && <VerifyEmail pending={pendingVerification} onPendingChange={setPendingVerification} onVerified={completeAuth} onBack={() => { setAuthView('signup'); navigate('/signup'); }} />}
      {profileError && <p className="error-note auth-error">{profileError}</p>}
    </div>;
  }

  if (profileLoading || childrenLoading) {
    return <div className="auth-shell">
      <div className="auth-panel">
        <div className="auth-heading">
          <span>Loading Profile</span>
          <h2>Preparing your dashboard</h2>
          <p>We are fetching your saved MsAlisia profile and child profiles.</p>
        </div>
      </div>
    </div>;
  }

  if (showParentOnboarding && session.access_token && currentProfile) {
    return <div className="app-shell onboarding-shell">
      <main>
        <ParentOnboardingView
          accessToken={session.access_token}
          parentName={currentProfile.full_name}
          onChildCreated={handleOnboardingChildCreated}
          onContinue={() => {
            setShowParentOnboarding(false);
            if (paidCheckoutRequiredAfterSignup) {
              setParentView('billing');
              navigate('/billing');
            } else {
              setParentView('home');
            }
          }}
        />
      </main>
    </div>;
  }

  return (
    <ParentShell
      profile={currentProfile}
      view={parentView}
      connected={connected}
      childProfiles={children}
      selectedChildId={selectedChildId}
      childrenError={childrenError}
      onViewChange={changeParentView}
      onSelectChild={handleSelectChild}
      onOpenChildren={() => changeParentView('children')}
      onLogout={logout}
    >
      <ParentOnly allowed>
        {parentView === 'home' && <ParentDashboardView
          accessToken={session.access_token || ''}
          parentName={currentProfile?.full_name || 'Parent'}
          children={children}
          selectedChildId={selectedChildId}
          onSelectChild={handleSelectChild}
          onViewChange={changeParentView}
        />}
        {parentView === 'profile' && currentProfile && session.access_token && <ProfileView accessToken={session.access_token} profile={currentProfile} onProfileUpdated={applyProfile} />}
        {parentView === 'children' && session.access_token && <ManageChildrenView accessToken={session.access_token} children={children} selectedChildId={selectedChildId} onChildrenChanged={handleChildrenChanged} />}
        {parentView === 'reports' && <ReportsView student={student} accessToken={session.access_token || ''} childId={selectedChildId} setView={(view) => {
          if (view === 'reports') setParentView('reports');
        }} />}
        {parentView === 'billing' && <BillingView accessToken={session.access_token || ''} />}
        {parentView === 'future' && <FutureView />}
      </ParentOnly>
    </ParentShell>
  );
}

function preferredChildId(children: ChildProfile[]): string {
  return children.find(child => child.status !== 'inactive')?.id || children[0]?.id || '';
}

function parentPathForView(view: ParentView): string {
  if (view === 'home') return '/dashboard';
  if (view === 'profile') return '/settings';
  return `/${view}`;
}

function adminSectionFromPath(pathname: string): AdminSection {
  const section = pathname.split('/')[2] as AdminSection | undefined;
  if (section === 'users' || section === 'subscriptions' || section === 'reports' || section === 'settings' || section === 'admins' || section === 'owner-financials') {
    return section;
  }
  return 'dashboard';
}
