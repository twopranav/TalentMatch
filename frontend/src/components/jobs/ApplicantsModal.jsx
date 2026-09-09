import Modal from '../ui/Modal'
import ApplicantsPanel from './ApplicantsPanel'

export default function ApplicantsModal({ job, open, onClose }) {
  if (!job) return null

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Applicants — ${job.title}`}
      footer={
        <button onClick={onClose} className="rounded px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
          Close
        </button>
      }
    >
      <ApplicantsPanel job={job} active={open} />
    </Modal>
  )
}