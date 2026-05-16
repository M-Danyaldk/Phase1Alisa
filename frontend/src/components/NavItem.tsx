import React from 'react';
import { classNames } from '../lib/classNames';

export function NavItem({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) {
  return <button className={classNames('nav-item', active && 'active')} onClick={onClick}>{icon}<span>{label}</span></button>;
}
