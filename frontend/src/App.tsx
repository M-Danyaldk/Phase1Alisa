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
import { BillingView } from './views/BillingView';
import { FutureView } from './views/FutureView';
import { HomeView } from './views/HomeView';
import { HomeworkView } from './views/HomeworkView';
import { LearningView } from './views/LearningView';
import { ManageChildrenView } from './views/ManageChildrenView';
import { ParentOnboardingView } from './views/ParentOnboardingView';
import { ParentDashboardView } from './views/ParentDashboardView';
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
type AccessMode = 'parent' | 'child';

const AUTH_SESSION_KEY = 'msalisia-auth-session';
const STUDENT_SESSION_KEY = 'msalisia-student-session';

export function App() {
  const [accessMode, setAccessMode] = useState<AccessMode>('parent');
  const [parentView, setParentView] = useState<ParentView>('home');
  const [childView, setChildView] = useState<ChildView>('home');
  const [student, setStudent] = useState<StudentProfile>(initialStudent);
  const [connected, setConnected] = useState<'checking' | 'online' | 'offline'>('checking');
  const [authView, setAuthView] = useState<AuthView>('login');
  const [pendingVerification, setPendingVerification] = useState<PendingVerification | null>(null);
  const [session, setSession] = useState<AuthSessionResponse | null>(() => {
    const stored = localStorage.getItem(AUTH_SESSION_KEY);
    return stored ? JSON.parse(stored) as AuthSessionResponse : null;
  });
  const [profileLoading, setProfileLoading] = useState(() => Boolean(localStorage.getItem(AUTH_SESSION_KEY)));
  const [profileError, setProfileError] = useState('');
  const [currentProfile, setCurrentProfile] = useState<ProfileResponse | null>(null);
  const [children, setChildren] = useState<ChildProfile[]>([]);
  const [selectedChildId, setSelectedChildId] = useState('');
  const [childrenLoading, setChildrenLoading] = useState(() => Boolean(localStorage.getItem(AUTH_SESSION_KEY)));
  const [childrenError, setChildrenError] = useState('');
  const [showParentOnboarding, setShowParentOnboarding] = useState(false);
  const [activeLearningChildId, setActiveLearningChildId] = useState('');
  const [studentSession, setStudentSession] = useState<StudentSession | null>(() => {
    const stored = localStorage.getItem(STUDENT_SESSION_KEY);
    return stored ? JSON.parse(stored) as StudentSession : null;
  });
  const [studentMe, setStudentMe] = useState<StudentMe | null>(null);
  const [studentSessionLoading, setStudentSessionLoading] = useState(() => Boolean(localStorage.getItem(STUDENT_SESSION_KEY)));
  const [studentSessionError, setStudentSessionError] = useState('');

  useEffect(() => {
    checkHealth().then(() => setConnected('online')).catch(() => setConnected('offline'));
  }, []);

  async function loadProfile(nextSession: AuthSessionResponse) {
    if (!nextSession.access_token) {
      throw new Error('Missing session token. Please log in again.');
    }
    const profile = await getCurrentProfile(nextSession.access_token);
    setCurrentProfile(profile);
    setStudent(profileToStudent(profile));
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
    try {
      await loadProfile(nextSession);
    } catch (error) {
      localStorage.removeItem(AUTH_SESSION_KEY);
      setProfileError(error instanceof Error ? error.message : 'Could not load profile. Please log in again.');
      setSession(null);
      setAuthView('login');
      setProfileLoading(false);
      setChildrenLoading(false);
      return;
    }
    try {
      await loadChildren(nextSession);
    } catch (error) {
      setChildren([]);
      setSelectedChildId('');
      setShowParentOnboarding(false);
      setChildrenError(error instanceof Error ? error.message : 'Could not load child profiles.');
    }
    setSession(nextSession);
    setPendingVerification(null);
    setAuthView('login');
    setAccessMode('parent');
    setParentView('home');
    setChildView('home');
    setProfileLoading(false);
    setChildrenLoading(false);
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
    setProfileError('');
    setActiveLearningChildId('');
    setAccessMode('parent');
    setParentView('home');
    setChildView('home');
    setAuthView('login');
  }

  function parentLoginPath() {
    localStorage.removeItem(AUTH_SESSION_KEY);
    setSession(null);
    setCurrentProfile(null);
    setChildren([]);
    setSelectedChildId('');
    setAccessMode('parent');
    setAuthView('login');
    setStudentSessionError('');
    window.location.assign('/');
  }

  function completeStudentLogin(nextSession: StudentSession) {
    localStorage.setItem(STUDENT_SESSION_KEY, JSON.stringify(nextSession));
    setStudentSession(nextSession);
    setStudentMe({
      role: 'child',
      child_id: nextSession.child_id,
      parent_id: nextSession.parent_id,
      student_name: nextSession.student_name,
      grade_level: nextSession.grade_level,
      subjects: ['Math', 'ELA', 'Writing'],
      session_expires_at: nextSession.expires_at,
    });
    setChildView('home');
  }

  async function logoutStudent() {
    const token = studentSession?.access_token;
    localStorage.removeItem(STUDENT_SESSION_KEY);
    setStudentSession(null);
    setStudentMe(null);
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
        const message = error instanceof Error ? error.message : '';
        setStudentSessionError(message.includes('learning access is currently paused') ? message : 'Please log in again to open your classroom.');
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
    const activeLearningChild = nextChildren.find(child => child.id === activeLearningChildId);
    if (activeLearningChildId && (!activeLearningChild || activeLearningChild.status === 'inactive')) {
      setActiveLearningChildId('');
      setAccessMode('parent');
      setParentView('children');
    }
  }

  function handleOnboardingChildCreated(child: ChildProfile) {
    setChildren(prev => [...prev, child]);
    setSelectedChildId(child.id);
  }

  function openChildSession(childId: string) {
    const child = children.find(item => item.id === childId);
    if (!child || child.status === 'inactive') return;
    setSelectedChildId(childId);
    window.location.assign('/student');
  }

  function exitChildSession() {
    setAccessMode('parent');
    setParentView('home');
    setChildView('home');
    setActiveLearningChildId('');
  }

  const adminPath = window.location.pathname.replace(/\/+$/, '') === '/admin';
  if (adminPath) {
    return <div className="app-shell admin-shell">
      <main>
        <AdminOnly allowed>
          <AdminView />
        </AdminOnly>
      </main>
    </div>;
  }

  const studentPath = window.location.pathname.replace(/\/+$/, '') === '/student';
  if (studentPath) {
    if (studentSessionLoading) {
      return <div className="auth-shell">
        <div className="auth-panel">
          <div className="auth-heading">
            <span>Student Login</span>
            <h2>Opening classroom</h2>
            <p>We are checking your student session.</p>
          </div>
        </div>
      </div>;
    }

    if (!studentSession || !studentMe) {
      return <>
        <StudentLoginView onLoggedIn={completeStudentLogin} onParentLogin={parentLoginPath} />
        {studentSessionError && <p className="error-note auth-error">{studentSessionError}</p>}
      </>;
    }

    const sessionStudent: StudentProfile = {
      name: studentMe.student_name,
      grade: Number(studentMe.grade_level.replace(/\D/g, '')) || 4,
      math_level: 'Not assessed yet',
      ela_level: 'Not assessed yet',
      writing_level: 'Not assessed yet',
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

    return <ChildShell
      child={sessionChild}
      view={childView}
      connected={connected}
      onViewChange={setChildView}
      onExit={logoutStudent}
      exitLabel="Logout"
    >
      <ChildOnly allowed>
        {childView === 'home' && <HomeView student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} studentSession setView={(view) => {
          if (view === 'learn' || view === 'assessments' || view === 'homework') setChildView(view);
        }} />}
        {childView === 'learn' && <LearningView key="student-learn" student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} studentSession />}
        {childView === 'assessments' && <AssessmentView student={sessionStudent} setStudent={setStudent} childId={studentMe.child_id} accessToken={studentSession.access_token} studentSession />}
        {childView === 'practice-math' && <LearningView key="student-practice-math" student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} initialSubject="Math" studentSession />}
        {childView === 'practice-ela' && <LearningView key="student-practice-ela" student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} initialSubject="ELA" studentSession />}
        {childView === 'practice-writing' && <LearningView key="student-practice-writing" student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} initialSubject="Writing" studentSession />}
        {childView === 'homework' && <HomeworkView student={sessionStudent} accessToken={studentSession.access_token} childId={studentMe.child_id} studentSession />}
      </ChildOnly>
    </ChildShell>;
  }

  if (!session) {
    return <div className="auth-shell">
      <div className="auth-brand">
        <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
        <span>MsAlisia</span>
      </div>
      {authView === 'login' && <Login onLoggedIn={completeAuth} onSignup={() => setAuthView('signup')} />}
      {authView === 'signup' && <Signup onLogin={() => setAuthView('login')} onPendingVerification={(pending) => {
        setPendingVerification(pending);
        setAuthView('verify');
      }} />}
      {authView === 'verify' && pendingVerification && <VerifyEmail pending={pendingVerification} onPendingChange={setPendingVerification} onVerified={completeAuth} onBack={() => setAuthView('signup')} />}
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
            setParentView('home');
          }}
        />
      </main>
    </div>;
  }

  const activeLearningChild = children.find(child => child.id === activeLearningChildId);
  const childStudent = activeLearningChild ? childToStudent(activeLearningChild) : student;

  if (accessMode === 'child' && activeLearningChild) {
    return <ChildShell
      child={activeLearningChild}
      view={childView}
      connected={connected}
      onViewChange={setChildView}
      onExit={exitChildSession}
    >
      <ChildOnly allowed={accessMode === 'child' && Boolean(activeLearningChild)}>
        {childView === 'home' && <HomeView student={childStudent} accessToken={session.access_token || ''} childId={activeLearningChild.id} setView={(view) => {
          if (view === 'learn' || view === 'assessments' || view === 'homework') setChildView(view);
        }} />}
        {childView === 'learn' && <LearningView key="learn" student={childStudent} accessToken={session.access_token || ''} childId={activeLearningChild.id} />}
        {childView === 'assessments' && <AssessmentView student={childStudent} setStudent={setStudent} childId={activeLearningChild.id} accessToken={session.access_token || ''} />}
        {childView === 'practice-math' && <LearningView key="practice-math" student={childStudent} accessToken={session.access_token || ''} childId={activeLearningChild.id} initialSubject="Math" />}
        {childView === 'practice-ela' && <LearningView key="practice-ela" student={childStudent} accessToken={session.access_token || ''} childId={activeLearningChild.id} initialSubject="ELA" />}
        {childView === 'practice-writing' && <LearningView key="practice-writing" student={childStudent} accessToken={session.access_token || ''} childId={activeLearningChild.id} initialSubject="Writing" />}
        {childView === 'homework' && <HomeworkView student={childStudent} accessToken={session.access_token || ''} childId={activeLearningChild.id} />}
      </ChildOnly>
    </ChildShell>;
  }

  return (
    <ParentShell
      profile={currentProfile}
      view={parentView}
      connected={connected}
      childProfiles={children}
      selectedChildId={selectedChildId}
      childrenError={childrenError}
      onViewChange={setParentView}
      onSelectChild={setSelectedChildId}
      onOpenChildren={() => setParentView('children')}
      onLogout={logout}
    >
      <ParentOnly allowed={accessMode === 'parent'}>
        {parentView === 'home' && <ParentDashboardView
          parentName={currentProfile?.full_name || 'Parent'}
          children={children}
          selectedChildId={selectedChildId}
          onSelectChild={setSelectedChildId}
          onOpenChildSession={openChildSession}
          onViewChange={setParentView}
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
