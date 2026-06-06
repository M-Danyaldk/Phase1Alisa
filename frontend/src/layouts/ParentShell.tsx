import { FileText, Home, ImageUp, UserCircle, UserRoundPlus, WalletCards } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { NavigationDrawer } from '../components/navigation/NavigationDrawer';
import { NavItem } from '../components/NavItem';
import { StudentProfileSelector } from '../components/student/StudentProfileSelector';
import { ParentView } from '../types';
import { ProfileResponse } from '../types/auth';
import { ChildProfile } from '../types/childProfile';

type Props = {
  profile: ProfileResponse | null;
  view: ParentView;
  connected: 'checking' | 'online' | 'offline';
  childProfiles: ChildProfile[];
  selectedChildId: string;
  childrenError: string;
  onViewChange: (view: ParentView) => void;
  onSelectChild: (childId: string) => void;
  onOpenChildren: () => void;
  onLogout: () => void;
  children: ReactNode;
};

export function ParentShell({
  profile,
  view,
  childProfiles,
  selectedChildId,
  childrenError,
  onViewChange,
  onSelectChild,
  onOpenChildren,
  onLogout,
  children,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const parentName = profile ? profile.full_name : 'Parent control center';
  const brand = <div className="brand-block">
    {profile?.avatar_url ? <img src={profile.avatar_url} alt={`${profile.full_name} profile`} /> : <img src="/logo.jpeg" alt="MsAlisia logo" onError={(event) => { event.currentTarget.style.display = 'none'; }} />}
    <div>
      <h1>MsAlisia</h1>
      <p>{parentName}</p>
    </div>
  </div>;
  const navItems = (closeAfterClick = false) => <>
    <NavItem icon={<Home />} label="Dashboard" active={view === 'home'} onClick={() => { onViewChange('home'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<UserRoundPlus />} label="Child Profiles" active={view === 'children'} onClick={() => { onViewChange('children'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<FileText />} label="Reports" active={view === 'reports'} onClick={() => { onViewChange('reports'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<ImageUp />} label="Homework" active={view === 'homework'} onClick={() => { onViewChange('homework'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<WalletCards />} label="Billing" active={view === 'billing'} onClick={() => { onViewChange('billing'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<UserCircle />} label="Settings" active={view === 'profile'} onClick={() => { onViewChange('profile'); if (closeAfterClick) setMenuOpen(false); }} />
  </>;
  const logoutButton = <button className="logout-button" onClick={onLogout}>Logout</button>;

  return <div className="app-shell parent-shell">
    <NavigationDrawer
      title="MsAlisia"
      subtitle={parentName}
      open={menuOpen}
      onOpen={() => setMenuOpen(true)}
      onClose={() => setMenuOpen(false)}
      brand={brand}
      footer={logoutButton}
    >
      {navItems(true)}
    </NavigationDrawer>
    <aside className="sidebar">
      {brand}
      <nav aria-label="Parent navigation">
        {navItems()}
      </nav>
      {logoutButton}
    </aside>
    <main>
      {childrenError && <p className="error-note app-error">{childrenError}</p>}
      <StudentProfileSelector children={childProfiles} selectedChildId={selectedChildId} onSelect={onSelectChild} onManageChildren={onOpenChildren} />
      {children}
    </main>
  </div>;
}
