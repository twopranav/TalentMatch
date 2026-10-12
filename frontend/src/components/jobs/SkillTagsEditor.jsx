import { useEffect, useRef, useState } from "react";

const EMPTY = [];

/**
 * Editable skill tags for a JD's extracted skills.
 *
 * Props
 *   skills    string[]                      current list (Job.skills_result)
 *   editable  boolean                       false -> plain read-only tags
 *   onSave    (nextSkills: string[]) => Promise<void>
 *             Persist the FULL new list (PUT /jobs/{id}/skills). Throw on
 *             failure; this component then reverts and shows the error.
 *
 * Behaviour
 *   - Each tag has a tiny superscript "-" button that removes it.
 *   - A dashed "+ Add skill" chip sits after the last tag; click it to type
 *     a skill, Enter adds it (input stays open for the next one), Esc/blur closes.
 *   - Every change is saved immediately; controls lock while a save is in flight.
 */
export default function SkillTagsEditor({ skills = EMPTY, editable = true, onSave }) {
  const [items, setItems] = useState(skills);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  // Follow the server value whenever the parent refetches the job.
  useEffect(() => setItems(skills), [skills]);

  useEffect(() => {
    if (adding) inputRef.current?.focus();
  }, [adding]);

  async function persist(next) {
    const previous = items;
    setItems(next);
    setSaving(true);
    setError(null);
    try {
      await onSave(next);
    } catch (e) {
      setItems(previous);
      setError(e?.response?.data?.detail || e?.message || "Couldn't save skills.");
    } finally {
      setSaving(false);
    }
  }

  function remove(skill) {
    if (saving) return;
    if (items.length === 1) {
      setError("A job needs at least one skill to match against.");
      return;
    }
    persist(items.filter((s) => s !== skill));
  }

  async function commitDraft() {
    const skill = draft.replace(/\s+/g, " ").trim();
    setDraft("");
    if (!skill || saving) return;
    if (items.some((s) => s.toLowerCase() === skill.toLowerCase())) return;
    await persist([...items, skill]);
    inputRef.current?.focus();
  }

  function onKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      commitDraft();
    } else if (e.key === "Escape") {
      setDraft("");
      setAdding(false);
    }
  }

  function onBlur() {
    if (draft.trim()) commitDraft();
    setAdding(false);
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-3 pt-1">
        {items.map((skill) => (
          <span key={skill} className="relative inline-flex">
            <span className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-sm font-medium text-indigo-800 shadow-sm dark:border-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-100">
              {skill}
            </span>
            {editable && (
              <button
                type="button"
                onClick={() => remove(skill)}
                disabled={saving}
                aria-label={`Remove ${skill}`}
                title={`Remove ${skill}`}
                className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-indigo-300 shadow ring-2 ring-white transition hover:scale-110 hover:bg-red-300 disabled:opacity-40 dark:bg-indigo-300 dark:ring-slate-900 dark:hover:bg-red-300"
              >
                <span className="block h-[2px] w-2 rounded bg-slate-900" aria-hidden="true" />
              </button>
            )}
          </span>
        ))}

        {editable &&
          (adding ? (
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              onBlur={onBlur}
              maxLength={100}
              placeholder="Add skill…"
              aria-label="New skill"
              className="w-36 rounded-full border border-dashed border-slate-400 bg-transparent px-3 py-1 text-sm text-slate-800 outline-none focus:border-indigo-500 dark:text-slate-100"
            />
          ) : (
            <button
              type="button"
              onClick={() => setAdding(true)}
              disabled={saving}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-400 px-3 py-1 text-sm text-slate-500 transition hover:border-indigo-500 hover:bg-indigo-50 hover:text-indigo-600 disabled:opacity-40 dark:text-slate-400 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-300"
            >
              <span aria-hidden="true">+</span> Add skill
            </button>
          ))}
      </div>

      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
