import { useState } from 'react'
import { useResumes } from '../hooks/useResumes'
import ResumeUploadModal from '../components/resume/ResumeUploadModal'
import Spinner from '../components/ui/Spinner'

export default function Profile() {
  const { resumes, loading, error, refetch } = useResumes()
  const [modalOpen, setModalOpen] = useState(false)

  const currentResume = resumes[0] // USER role has at most one active resume

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-6 text-xl font-semibold text-slate-800 dark:text-slate-100">
        My Profile
      </h1>

      <section className="rounded border border-slate-200 p-4 dark:border-slate-700">
        <h2 className="mb-3 text-sm font-medium text-slate-700 dark:text-slate-300">
          Resume
        </h2>

        {loading && <Spinner size="sm" label="Loading" />}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && !error && (
          <>
            {currentResume ? (
              <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
                On file: {currentResume.original_filename}
              </p>
            ) : (
              <p className="mb-3 text-sm text-slate-400 dark:text-slate-500">
                No resume uploaded yet.
              </p>
            )}
            <button
              onClick={() => setModalOpen(true)}
              className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600"
            >
              {currentResume ? 'Replace resume' : 'Upload resume'}
            </button>
          </>
        )}
      </section>

      <ResumeUploadModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        currentResume={currentResume}
        onUploaded={refetch}
      />
    </div>
  )
}