import { useCallback, useEffect, useState } from 'react'
import { fetchLLMConfigs, fetchLLMProviders, probeLLMConfig, updateLLMConfig } from '../api/llmConfig'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import { formatEnumLabel, getErrorMessage } from '../utils/format'

const inputClass =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'

const isUnset = (c) => c.provider === 'unset' || c.model === 'unset'

function TaskRow({ config, providers, onSaved }) {
  const { showToast } = useToast()
  const [provider, setProvider] = useState(config.provider)
  const [model, setModel] = useState(config.model === 'unset' ? '' : config.model)
  const [saving, setSaving] = useState(false)
  const [probing, setProbing] = useState(false)
  const [probeResult, setProbeResult] = useState(null)

  const providerKnown = providers.includes(provider)
  const dirty = provider !== config.provider || model.trim() !== (config.model === 'unset' ? '' : config.model)
  const canSave = dirty && providerKnown && model.trim() !== '' && !saving
  const canProbe = !dirty && !isUnset(config) && !probing && !saving

  const save = async () => {
    setSaving(true)
    try {
      const saved = await updateLLMConfig(config.task, provider, model.trim())
      onSaved(saved)
      setProbeResult(null) // any earlier test was against the old settings
      showToast(`${formatEnumLabel(config.task)} now uses ${saved.provider} / ${saved.model}.`, 'success')
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not save this configuration.'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const probe = async () => {
    setProbing(true)
    setProbeResult(null)
    try {
      setProbeResult(await probeLLMConfig(config.task))
    } catch (err) {
      setProbeResult({ ok: false, stage: 'request', error: getErrorMessage(err, 'The test request failed.') })
    } finally {
      setProbing(false)
    }
  }

  return (
    <div className="border-b border-slate-100 px-4 py-4 last:border-0 dark:border-slate-800">
      <div className="mb-3 flex items-center gap-2">
        <span className="font-medium text-slate-900 dark:text-slate-100">{formatEnumLabel(config.task)}</span>
        <span className="font-mono text-xs text-slate-400 dark:text-slate-500">{config.task}</span>
        {isUnset(config) && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
            Not set
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="w-44 text-xs font-medium text-slate-500 dark:text-slate-400">
          Provider
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className={`${inputClass} mt-1`}
          >
            {!providerKnown && <option value={provider} disabled>Select a provider…</option>}
            {providers.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>

        <label className="min-w-56 flex-1 text-xs font-medium text-slate-500 dark:text-slate-400">
          Model
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g. gpt-4o-mini"
            spellCheck={false}
            className={`${inputClass} mt-1 font-mono`}
          />
        </label>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={save}
            disabled={!canSave}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={probe}
            disabled={!canProbe}
            title={dirty ? 'Save your changes first — the test uses the saved configuration' : 'Makes one real call to the provider'}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            {probing ? 'Testing…' : 'Test'}
          </button>
        </div>
      </div>

      {probing && (
        <div className="mt-3"><Spinner size="sm" label="Testing connection" /></div>
      )}

      {probeResult && (
        <p
          role="status"
          className={`mt-3 break-words rounded-lg px-3 py-2 text-xs ${
            probeResult.ok
              ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
              : 'bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-300'
          }`}
        >
          {probeResult.ok ? (
            <>Working — replied “{probeResult.reply}” in {probeResult.elapsed_s}s.</>
          ) : (
            <>
              Failed{probeResult.stage === 'config' ? ' (configuration)' : probeResult.stage === 'provider_call' ? ' (provider call)' : ''}
              : {probeResult.error}
            </>
          )}
        </p>
      )}
    </div>
  )
}

export default function LLMSettings() {
  const [configs, setConfigs] = useState([])
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([fetchLLMConfigs(), fetchLLMProviders()])
      .then(([rows, names]) => {
        setConfigs(rows)
        setProviders(names)
      })
      .catch((err) => setError(getErrorMessage(err, 'Could not load the LLM configuration. Please try again.')))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleSaved = (saved) =>
    setConfigs((current) => current.map((c) => (c.task === saved.task ? saved : c)))

  const unsetCount = configs.filter(isUnset).length

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">LLM settings</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Choose the provider and model used by each extraction task. Changes apply to the very next extraction —
          no deploy needed. API keys stay in server environment settings. Every change is recorded in the audit history.
        </p>
      </div>

      {loading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading LLM configuration" />
        </div>
      )}

      {error && (
        <div className="flex items-center gap-3 text-sm text-red-600 dark:text-red-400">
          <span>{error}</span>
          <button type="button" onClick={load} className="font-medium underline">Retry</button>
        </div>
      )}

      {!loading && !error && unsetCount > 0 && (
        <p className="mb-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {unsetCount} {unsetCount === 1 ? 'task has' : 'tasks have'} no model chosen yet. Extraction for
          {unsetCount === 1 ? ' it' : ' them'} will fail until one is set.
        </p>
      )}

      {!loading && !error && configs.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No tasks are configured. Run the database migrations to seed them.
          </p>
        </div>
      )}

      {!loading && !error && configs.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          {configs.map((config) => (
            <TaskRow key={config.task} config={config} providers={providers} onSaved={handleSaved} />
          ))}
        </div>
      )}
    </div>
  )
}
