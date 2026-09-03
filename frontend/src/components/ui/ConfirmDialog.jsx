import Modal from './Modal'

export default function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title = 'Are you sure?',
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
}) {
  const handleConfirm = () => {
    onConfirm()
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <button
            onClick={onClose}
            className="rounded px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            {cancelLabel}
          </button>
          <button
            onClick={handleConfirm}
            className={`rounded px-4 py-2 text-sm font-medium text-white ${
              destructive
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-slate-800 hover:bg-slate-900'
            }`}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className="text-sm text-slate-600">{message}</p>
    </Modal>
  )
}