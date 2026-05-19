import { ChildProfile } from '../../types/childProfile';

export function ConfirmDeactivateChildModal({
  child,
  saving,
  onCancel,
  onConfirm,
}: {
  child: ChildProfile;
  saving: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return <div className="modal-backdrop" role="presentation">
    <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="deactivate-child-title">
      <span className="modal-eyebrow">Pause learning access</span>
      <h3 id="deactivate-child-title">Deactivate {child.name}?</h3>
      <p>
        Deactivating will pause your child&apos;s learning progress and remove their active access. Are you sure you want to continue?
      </p>
      <div className="modal-actions">
        <button className="primary-button safe-action" onClick={onCancel} disabled={saving}>Keep child active</button>
        <button className="secondary-button confirm-danger" onClick={onConfirm} disabled={saving}>
          {saving ? 'Pausing...' : 'Yes, deactivate child'}
        </button>
      </div>
    </div>
  </div>;
}
