import { Menu, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { classNames } from '../../lib/classNames';

export function NavigationDrawer({
  title,
  subtitle,
  open,
  onOpen,
  onClose,
  brand,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  brand: ReactNode;
  children: ReactNode;
  footer: ReactNode;
}) {
  return <>
    <header className="mobile-topbar">
      <button className="mobile-menu-button" type="button" onClick={onOpen} aria-label="Open navigation menu" aria-expanded={open}>
        <Menu />
      </button>
      <div>
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
    </header>
    <div className={classNames('mobile-menu-layer', open && 'open')} aria-hidden={!open}>
      <button className="mobile-menu-backdrop" type="button" onClick={onClose} aria-label="Close navigation menu" tabIndex={open ? 0 : -1} />
      <aside className="mobile-drawer" aria-label={`${title} mobile navigation`}>
        <div className="mobile-drawer-header">
          {brand}
          <button className="mobile-close-button" type="button" onClick={onClose} aria-label="Close navigation menu">
            <X />
          </button>
        </div>
        <nav className="mobile-drawer-nav">
          {children}
        </nav>
        {footer}
      </aside>
    </div>
  </>;
}
