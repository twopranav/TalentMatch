import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { fetchLLMConfigs, fetchLLMProviders, probeLLMConfig, updateLLMConfig } from '../api/llmConfig'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import { formatEnumLabel, getErrorMessage } from '../utils/format'
import PageHeader from '../components/ui/PageHeader'
import StatusBadge from '../components/ui/StatusBadge'
import Button from '../components/ui/Button'

const inputClass =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'

const isUnset = (c) => c.provider === 'unset' || c.model === 'unset'

function TaskRow({ config, providers, onSaved, bulkTestResult, onProbeComplete, testingAll, canEdit }) {
  const { showToast } = useToast()
  const [provider, setProvider] = useState(config.provider)
  const [model, setModel] = useState(config.model === 'unset' ? '' : config.model)
  const [saving, setSaving] = useState(false)
  const [probing, setProbing] = useState(false)
  const [probeResult, setProbeResult] = useState(config.last_test_result ?? null)
  const [lastTestedAt, setLastTestedAt] = useState(config.last_tested_at ?? config.last_probe_at ?? null)

  const providerKnown = providers.includes(provider)
  const dirty = provider !== config.provider || model.trim() !== (config.model === 'unset' ? '' : config.model)
  const canSave = canEdit && dirty && providerKnown && model.trim() !== '' && !saving
  const canProbe = canEdit && !dirty && !isUnset(config) && !probing && !saving && !testingAll

  useEffect(() => {
    if (!bulkTestResult) return
    setProbeResult(bulkTestResult.result)
    setLastTestedAt(bulkTestResult.testedAt)
  }, [bulkTestResult])

  const save = async () => {
    setSaving(true)
    try {
      const saved = await updateLLMConfig(config.task, provider, model.trim())
      onSaved(saved)
      setProbeResult(null) // any earlier test was against the old settings
      setLastTestedAt(null)
      onProbeComplete(config.task, null, null)
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
      const result = await probeLLMConfig(config.task)
      const testedAt = new Date().toISOString()
      setProbeResult(result)
      setLastTestedAt(testedAt)
      onProbeComplete(config.task, result, testedAt)
    } catch (err) {
      const result = { ok: false, stage: 'request', error: getErrorMessage(err, 'The test request failed.') }
      const testedAt = new Date().toISOString()
      setProbeResult(result)
      setLastTestedAt(testedAt)
      onProbeComplete(config.task, result, testedAt)
    } finally {
      setProbing(false)
    }
  }

  return (
    <div className="border-b border-slate-100 px-4 py-4 last:border-0 dark:border-slate-800">
      <div className="mb-3 flex items-center gap-2">
        <span className="font-medium text-slate-900 dark:text-slate-100">{formatEnumLabel(config.task)}</span>
        <span className="font-mono text-xs text-slate-400 dark:text-slate-500">{config.task}</span>
        {isUnset(config) && <StatusBadge status="unset">Not set</StatusBadge>}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="w-44 text-xs font-medium text-slate-500 dark:text-slate-400">
          Provider
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            disabled={!canEdit}
            className={`${inputClass} mt-1 disabled:cursor-not-allowed disabled:opacity-60`}
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
            disabled={!canEdit}
            className={`${inputClass} mt-1 font-mono disabled:cursor-not-allowed disabled:opacity-60`}
          />
        </label>

        {canEdit && <div className="flex items-center gap-2">
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
        </div>}
      </div>

      {probing && (
        <div className="mt-3"><Spinner size="sm" label="Testing connection" /></div>
      )}

      {lastTestedAt && <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">Last tested {new Date(lastTestedAt).toLocaleString()}</p>}

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
  const { user } = useAuth()
  // The server only lets the superuser save or test; admins can view the configuration.
  const canEdit = user?.role === 'superuser'
  const [configs, setConfigs] = useState([])
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [testingAll, setTestingAll] = useState(false)
  const [bulkResults, setBulkResults] = useState({})
  const { showToast } = useToast()

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

  const handleSaved = (saved) => {
    setConfigs((current) => current.map((c) => (c.task === saved.task ? saved : c)))
    setBulkResults((current) => { const next = { ...current }; delete next[saved.task]; return next })
  }

  const recordProbe = (task, result, testedAt) => setBulkResults((current) => ({ ...current, [task]: result ? { result, testedAt } : undefined }))
  const unsetCount = configs.filter(isUnset).length
  const testAll = async () => {
    const eligible = configs.filter((config) => !isUnset(config))
    if (!eligible.length || testingAll) return
    setTestingAll(true)
    let passed = 0
    let failed = 0
    for (const config of eligible) {
      let result
      try {
        result = await probeLLMConfig(config.task)
      } catch (err) {
        result = { ok: false, stage: 'request', error: getErrorMessage(err, 'The test request failed.') }
      }
      const testedAt = new Date().toISOString()
      recordProbe(config.task, result, testedAt)
      if (result?.ok) passed += 1
      else failed += 1
    }
    setTestingAll(false)
    showToast(`Test all complete: ${passed} passed, ${failed} failed${unsetCount ? `, ${unsetCount} unset skipped` : ''}.`, failed ? 'error' : 'success')
  }

  return (
    <div className="mx-auto max-w-[1440px] px-8 py-8">
      <PageHeader eyebrow="Administration" title="LLM configuration" description="Choose the provider and model used by each extraction task. Changes apply immediately; API keys remain in server environment settings and every change is audited." action={canEdit ? <Button onClick={testAll} disabled={loading || Boolean(error) || testingAll || configs.every(isUnset)}>{testingAll ? 'Testing models…' : 'Test all models'}</Button> : null} />

      {!canEdit && <p role="status" className="mb-4 rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-300">You can view this configuration. Only the superuser can change providers and models or run connection tests.</p>}

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
          {unsetCount === 1 ? ' it' : ' them'} will fail until one is set{canEdit ? '.' : '. Ask the superuser to set it.'}
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
            <TaskRow key={config.task} config={config} providers={providers} onSaved={handleSaved} bulkTestResult={bulkResults[config.task]} onProbeComplete={recordProbe} testingAll={testingAll} canEdit={canEdit} />
          ))}
        </div>
      )}
    </div>
  )
}
