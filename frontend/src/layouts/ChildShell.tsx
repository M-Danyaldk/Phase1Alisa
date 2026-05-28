import { BookOpen, ClipboardCheck, Home, ImageUp, MessageCircle, PenTool } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { NavigationDrawer } from '../components/navigation/NavigationDrawer';
import { NavItem } from '../components/NavItem';
import { classNames } from '../lib/classNames';
import { ChildView } from '../types';
import { ChildProfile } from '../types/childProfile';

type Props = {
  child: ChildProfile;
  view: ChildView;
  connected: 'checking' | 'online' | 'offline';
  onViewChange: (view: ChildView) => void;
  onExit: () => void;
  exitLabel?: string;
  children: ReactNode;
};

export function ChildShell({ child, view, connected, onViewChange, onExit, exitLabel = 'Back to Parent Area', children }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const brand = <div className="brand-block child-brand">
    <div className="student-avatar small" aria-hidden="true">{child.name.charAt(0).toUpperCase()}</div>
    <div>
      <h1>MsAlisia</h1>
      <p>{child.name}&apos;s classroom</p>
    </div>
  </div>;
  const status = <div className={classNames('status-pill', connected)}>
    Backend: {connected === 'checking' ? 'Checking...' : connected === 'online' ? 'Online' : 'Offline demo mode'}
  </div>;
  const navItems = (closeAfterClick = false) => <>
    <NavItem icon={<Home />} label="Student Dashboard" active={view === 'home'} onClick={() => { onViewChange('home'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<MessageCircle />} label="Learn" active={view === 'learn'} onClick={() => { onViewChange('learn'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<ClipboardCheck />} label="Assessment" active={view === 'assessments'} onClick={() => { onViewChange('assessments'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<BookOpen />} label="Practice Math" active={view === 'practice-math'} onClick={() => { onViewChange('practice-math'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<BookOpen />} label="Practice ELA" active={view === 'practice-ela'} onClick={() => { onViewChange('practice-ela'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<PenTool />} label="Practice Writing" active={view === 'practice-writing'} onClick={() => { onViewChange('practice-writing'); if (closeAfterClick) setMenuOpen(false); }} />
    <NavItem icon={<ImageUp />} label="Homework Upload" active={view === 'homework'} onClick={() => { onViewChange('homework'); if (closeAfterClick) setMenuOpen(false); }} />
  </>;
  const exitButton = <button className="logout-button" onClick={onExit}>{exitLabel}</button>;

  return <div className="app-shell child-shell">
    <NavigationDrawer
      title="MsAlisia"
      subtitle={`${child.name}'s classroom`}
      open={menuOpen}
      onOpen={() => setMenuOpen(true)}
      onClose={() => setMenuOpen(false)}
      brand={brand}
      footer={<>{status}{exitButton}</>}
    >
      {navItems(true)}
    </NavigationDrawer>
    <aside className="sidebar">
      {brand}
      <nav aria-label="Student navigation">
        {navItems()}
      </nav>
      {status}
      {exitButton}
    </aside>
    <main>
      {children}
    </main>
  </div>;
}
