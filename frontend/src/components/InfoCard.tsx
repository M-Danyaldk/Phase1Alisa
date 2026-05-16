import React from 'react';

export function InfoCard({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return <div className="info-card"><div className="card-icon">{icon}</div><h3>{title}</h3><p>{desc}</p></div>;
}
