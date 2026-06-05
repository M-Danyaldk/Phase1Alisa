import { Lock } from 'lucide-react';
import { SectionHeader } from '../components/SectionHeader';
import { futureModules } from '../constants';

export function FutureView() {
  return <div className="page-stack">
    <SectionHeader eyebrow="Coming Soon" title="Coming Soon." />
    <div className="card-grid four">{futureModules.map(m => <div className="future-card" key={m.title}><Lock /><span>Coming Soon</span><h3>{m.title}</h3><p>{m.desc}</p></div>)}</div>
  </div>;
}
