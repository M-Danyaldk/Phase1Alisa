import { Lock } from 'lucide-react';
import { SectionHeader } from '../components/SectionHeader';
import { futureModules } from '../constants';

export function FutureView() {
  return <div className="page-stack">
    <SectionHeader eyebrow="Future platform vision" title="Modules visible now, functionality later" desc="These modules are shown as Coming Soon so the MVP communicates the complete product direction without overbuilding Phase 1." />
    <div className="card-grid four">{futureModules.map(m => <div className="future-card" key={m.title}><Lock /><span>Coming Soon</span><h3>{m.title}</h3><p>{m.desc}</p></div>)}</div>
  </div>;
}
