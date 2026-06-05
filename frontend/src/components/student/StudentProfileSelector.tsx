import { ChildProfile } from '../../types/childProfile';

export function StudentProfileSelector({
  children,
  selectedChildId,
  onSelect,
  onManageChildren,
}: {
  children: ChildProfile[];
  selectedChildId: string;
  onSelect: (childId: string) => void;
  onManageChildren: () => void;
}) {
  if (!children.length) return null;

  return <div className="child-switcher">
    <button className="secondary-button compact" onClick={onManageChildren}>Manage Child Profiles</button>
    <label>Viewing
      <select value={selectedChildId} onChange={event => onSelect(event.target.value)} aria-label="Select child profile">
        {children.map(child => <option key={child.id} value={child.id}>{child.name}{child.status === 'inactive' ? ' (paused)' : ''}</option>)}
      </select>
    </label>
  </div>;
}
