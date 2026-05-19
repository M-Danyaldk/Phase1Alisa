import type { ReactNode } from 'react';

type AccessMode = 'parent' | 'child' | 'admin';

const messages: Record<AccessMode, string> = {
  parent: 'This area is for parents only.',
  child: 'This area is for students. Please open a child learning session to continue.',
  admin: 'Admin access is separate and protected.',
};

function AccessMessage({ mode }: { mode: AccessMode }) {
  return <div className="page-stack narrow">
    <section className="report-card access-message">
      <h3>Access protected</h3>
      <p>{messages[mode]}</p>
    </section>
  </div>;
}

export function ParentOnly({ allowed, children }: { allowed: boolean; children: ReactNode }) {
  return allowed ? <>{children}</> : <AccessMessage mode="parent" />;
}

export function ChildOnly({ allowed, children }: { allowed: boolean; children: ReactNode }) {
  return allowed ? <>{children}</> : <AccessMessage mode="child" />;
}

export function AdminOnly({ allowed, children }: { allowed: boolean; children: ReactNode }) {
  return allowed ? <>{children}</> : <AccessMessage mode="admin" />;
}
