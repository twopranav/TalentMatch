"""
Formerly: Hugging Face Inference Providers-based structured extraction.

Both entry points that used to live here are gone:

- extract_candidate_profile() -- candidates now fill in their own profile
  fields manually (see app/models/user.py, app/schemas/user.py's
  UserProfileUpdate) instead of having them LLM-extracted from the resume
  PDF. Only the standalone skills-only pass in
  app/core/skills_llm_extract.py still runs automatically on upload.

- extract_job_requirements() -- being replaced by a narrow, section-located
  skills-only JD pipeline mirroring the resume one (locate section -> clean
  -> narrow extract -> hallucination-check), instead of a single call over
  the whole JD text pulling skills + compulsory_skills + experience +
  education at once.

Nothing in this file has a caller left. It's kept only as a stepping stone
-- update the call sites below, then delete this file entirely:

- app/api/routes/jobs.py -- imports ExtractionError, extract_job_requirements
  and calls extract_job_requirements() in upload_jd(). Rewrite that route
  body once the new JD pipeline exists.
- app/schemas/extraction.py -- CandidateProfileExtraction and
  JobRequirementsExtraction become unused once nothing validates against
  them.
- eval_harness.py / backfill_extraction.py (not reviewed) -- likely import
  _extract_candidate_profile_for_eval() and/or
  _extract_job_requirements_for_eval(), which were eval-only variants of
  the two removed functions. Check both before deleting this file.
"""