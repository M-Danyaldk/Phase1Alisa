import { ChildProfile } from '../../types/childProfile';

export function ConfirmReactivateChildModal({
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
    <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="reactivate-child-title">
      <span className="modal-eyebrow">Restore learning access</span>
      <h3 id="reactivate-child-title">Reactivate {child.name}?</h3>
      <p>Reactivating will restore this child&apos;s learning access. Do you want to continue?</p>
      <div className="modal-actions">
        <button className="secondary-button" onClick={onCancel} disabled={saving}>Cancel</button>
        <button className="primary-button safe-action" onClick={onConfirm} disabled={saving}>
          {saving ? 'Restoring...' : 'Reactivate child'}
        </button>
      </div>
    </div>
  </div>;
}
