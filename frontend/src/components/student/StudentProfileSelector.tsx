import { ChildProfile } from '../../types/childProfile';

export function StudentProfileSelector({
  children,
  selectedChildId,
  onSelect,
  onAddChild,
}: {
  children: ChildProfile[];
  selectedChildId: string;
  onSelect: (childId: string) => void;
  onAddChild: () => void;
}) {
  if (!children.length) return null;

  return <div className="child-switcher">
    <label>Viewing
      <select value={selectedChildId} onChange={event => onSelect(event.target.value)} aria-label="Select child profile">
        {children.map(child => <option key={child.id} value={child.id}>{child.name}{child.status === 'inactive' ? ' (paused)' : ''}</option>)}
      </select>
    </label>
    <button className="secondary-button compact" onClick={onAddChild}>Add Child</button>
  </div>;
}
