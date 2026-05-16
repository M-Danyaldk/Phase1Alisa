import { useEffect, useState } from 'react';
import { ClipboardCheck, FileText, Home, ImageUp, MessageCircle, ShieldCheck, Sparkles, UserCircle, UserRoundPlus, Users, WalletCards } from 'lucide-react';
import { initialStudent } from './constants';
import { StudentProfileSelector } from './components/student/StudentProfileSelector';
import { NavItem } from './components/NavItem';
import { checkHealth } from './lib/api';
import { classNames } from './lib/classNames';
import { childToStudent, profileToStudent } from './lib/studentProfile';
import { AssessmentView } from './views/AssessmentView';
import { AdminView } from './views/AdminView';
import { BillingView } from './views/BillingView';
import { FutureView } from './views/FutureView';
import { HomeView } from './views/HomeView';
import { HomeworkView } from './views/HomeworkView';
import { LearningView } from './views/LearningView';
import { ManageChildrenView } from './views/ManageChildrenView';
import { OnboardingView } from './views/OnboardingView';
import { ParentOnboardingView } from './views/ParentOnboardingView';
import { ProfileView } from './views/ProfileView';
import { ReportsView } from './views/ReportsView';
import { StudentProfile, View } from './types';
import { Login } from './pages/Login';
import { Signup } from './pages/Signup';
import { VerifyEmail } from './pages/VerifyEmail';
import { AuthSessionResponse, PendingVerification, ProfileResponse } from './types/auth';
import { getCurrentProfile } from './lib/api/auth';
import { listChildren } from './lib/api/children';
import { ChildProfile } from './types/childProfile';

type AuthView = 'login' | 'signup' | 'verify';

const AUTH_SESSION_KEY = 'msalisia-auth-session';

export function App() {
  const [view, setView] = useState<View>('home');
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
    setSelectedChildId(prev => prev && records.some(child => child.id === prev) ? prev : records[0]?.id || '');
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
    setView('home');
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
    setAuthView('login');
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
    setSelectedChildId(selected && nextChildren.some(child => child.id === selected) ? selected : nextChildren[0]?.id || '');
  }

  function handleOnboardingChildCreated(child: ChildProfile) {
    setChildren(prev => [...prev, child]);
    setSelectedChildId(child.id);
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
            setView('home');
          }}
        />
      </main>
    </div>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          {currentProfile?.avatar_url ? <img src={currentProfile.avatar_url} alt={`${currentProfile.full_name} profile`} /> : <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />}
          <div>
            <h1>MsAlisia</h1>
            <p>{currentProfile ? currentProfile.full_name : 'Best Teacher. Best Mentor. Best Future.'}</p>
          </div>
        </div>
        <nav>
          <NavItem icon={<Home />} label="Home" active={view === 'home'} onClick={() => setView('home')} />
          <NavItem icon={<UserCircle />} label="Profile" active={view === 'profile'} onClick={() => setView('profile')} />
          <NavItem icon={<Users />} label="Parent Setup" active={view === 'onboarding'} onClick={() => setView('onboarding')} />
          <NavItem icon={<UserRoundPlus />} label="Child Profiles" active={view === 'children'} onClick={() => setView('children')} />
          <NavItem icon={<ClipboardCheck />} label="Assessments" active={view === 'assessments'} onClick={() => setView('assessments')} />
          <NavItem icon={<MessageCircle />} label="Start Learning" active={view === 'learn'} onClick={() => setView('learn')} />
          <NavItem icon={<ImageUp />} label="Homework & Handwriting" active={view === 'homework'} onClick={() => setView('homework')} />
          <NavItem icon={<FileText />} label="Reports" active={view === 'reports'} onClick={() => setView('reports')} />
          <NavItem icon={<WalletCards />} label="Billing & Trial" active={view === 'billing'} onClick={() => setView('billing')} />
          <NavItem icon={<ShieldCheck />} label="Admin" active={view === 'admin'} onClick={() => setView('admin')} />
          <NavItem icon={<Sparkles />} label="Future Modules" active={view === 'future'} onClick={() => setView('future')} />
        </nav>
        <div className={classNames('status-pill', connected)}>
          Backend: {connected === 'checking' ? 'Checking...' : connected === 'online' ? 'Online' : 'Offline demo mode'}
        </div>
        <button className="logout-button" onClick={logout}>Logout</button>
      </aside>
      <main>
        {childrenError && <p className="error-note app-error">{childrenError}</p>}
        <StudentProfileSelector children={children} selectedChildId={selectedChildId} onSelect={setSelectedChildId} onAddChild={() => setView('children')} />
        {view === 'home' && <HomeView student={student} accessToken={session.access_token || ''} childId={selectedChildId} setView={setView} />}
        {view === 'profile' && currentProfile && session.access_token && <ProfileView accessToken={session.access_token} profile={currentProfile} onProfileUpdated={applyProfile} />}
        {view === 'onboarding' && <OnboardingView student={student} setStudent={setStudent} />}
        {view === 'children' && session.access_token && <ManageChildrenView accessToken={session.access_token} children={children} selectedChildId={selectedChildId} onChildrenChanged={handleChildrenChanged} />}
        {view === 'assessments' && <AssessmentView student={student} setStudent={setStudent} childId={selectedChildId} />}
        {view === 'learn' && <LearningView student={student} accessToken={session.access_token || ''} childId={selectedChildId} />}
        {view === 'homework' && <HomeworkView student={student} />}
        {view === 'reports' && <ReportsView student={student} accessToken={session.access_token || ''} childId={selectedChildId} setView={setView} />}
        {view === 'billing' && <BillingView accessToken={session.access_token || ''} />}
        {view === 'admin' && <AdminView />}
        {view === 'future' && <FutureView />}
      </main>
    </div>
  );
}
