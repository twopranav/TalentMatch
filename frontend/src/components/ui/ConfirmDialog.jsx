import { useState } from 'react'
import Modal from './Modal'
import Button from './Button'
import Field from './Field'

export default function ConfirmDialog({ open, onClose, onConfirm, title = 'Are you sure?', message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', destructive = false, requireText = false, requiredText = 'DELETE', busy = false }) {
  const [confirmation, setConfirmation] = useState('')
  const canConfirm = !busy && (!requireText || confirmation === requiredText)
  const close = () => { setConfirmation(''); onClose?.() }
  const handleConfirm = async () => {
    if (!canConfirm) return
    await onConfirm?.()
    close()
  }
  return <Modal open={open} onClose={close} title={title} footer={<>
    <Button variant="secondary" onClick={close}>{cancelLabel}</Button>
    <Button variant={destructive ? 'danger' : 'primary'} onClick={handleConfirm} disabled={!canConfirm}>{busy ? 'Please wait…' : confirmLabel}</Button>
  </>}>
    <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">{message}</p>
    {requireText && <div className="mt-4"><Field label={`Type ${requiredText} to confirm`} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></div>}
  </Modal>
}
