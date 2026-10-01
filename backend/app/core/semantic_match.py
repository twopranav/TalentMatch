"""
Applicant score: resume (a) vs job description (b).

    a = resume skills + months of experience
    b = JD required skills (+ optional minimum months of experience)

    skills_score      how close the resume's skills are to the JD's skills (0-1)
    experience_score  how much experience the resume shows (0-1, more is better)
    score = 100 x (0.55 x skills_score + 0.45 x experience_score)

The two weights are configurable and are normalised, so they only need to be
in the right ratio.

Nobody is filtered out here (same policy as core/matching.py): every
applicant gets a score and the recruiter sorts by it.

Skills are matched one JD skill at a time rather than by embedding the two
whole documents, so the recruiter can see exactly which JD skills were
covered and by what ("kubernetes" <- "k8s", 0.91).

Per JD skill:
  * exact match after alias normalisation (matching.normalize_skill) -> 1.0,
    no embedding call
  * otherwise the best cosine similarity against the resume's skills,
    mapped through [sim_low, sim_high] -> [0, 1]

Experience score (absolute, so more years always means a higher score,
whether or not the JD states a minimum):

    experience_score = 1 - exp(-months / experience_scale_months)

    with the default 48-month scale:
        1 yr 0.22 | 2 yr 0.39 | 3 yr 0.53 | 5 yr 0.71 | 8 yr 0.86 | 12 yr 0.95

Unknown resume experience scores 0 for that component.

This module has no I/O: the embedder is passed in, so it is unit-testable
with a fake and swappable without touching the scoring rules.
"""

import math
from dataclasses import dataclass, field
from typing import Callable

from app.core.matching import normalize_skill

Embedder = Callable[[list[str]], list[list[float]]]

_MATCHED_CREDIT = 0.5  # a JD skill counts as "matched" for display at >= this credit


@dataclass
class MatchWeights:
    skills: float = 0.55
    experience: float = 0.45
    sim_low: float = 0.40
    sim_high: float = 0.85
    # Speed of the experience curve; larger = more years needed to saturate.
    experience_scale_months: int = 48


@dataclass
class MatchResult:
    score: float  # 0-100, one decimal
    skills_score: float | None  # 0-1, None if the JD lists no skills
    experience_score: float  # 0-1, from the resume's total months
    matched: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    resume_months: int | None = None
    jd_min_months: int | None = None
    meets_min_experience: bool | None = None  # None = can't tell / no minimum
    weights_used: dict = field(default_factory=dict)
    experience_scale_months: int = 48

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "skills_score": self.skills_score,
            "experience_score": self.experience_score,
            "matched": self.matched,
            "missing": self.missing,
            "resume_months": self.resume_months,
            "jd_min_months": self.jd_min_months,
            "meets_min_experience": self.meets_min_experience,
            "weights_used": self.weights_used,
            "experience_scale_months": self.experience_scale_months,
        }


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _credit(sim: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0 if sim >= high else 0.0
    return min(1.0, max(0.0, (sim - low) / (high - low)))


def _clean(skills: list[str] | None) -> list[str]:
    """Trim, lowercase, alias-normalise, dedupe (order preserved)."""
    out: dict[str, None] = {}
    for s in skills or []:
        if isinstance(s, str) and s.strip():
            out[normalize_skill(s)] = None
    return list(out)


def score_skills(
    resume_skills: list[str] | None,
    jd_skills: list[str] | None,
    embed: Embedder,
    weights: MatchWeights,
) -> tuple[float | None, list[dict], list[str]]:
    jd = _clean(jd_skills)
    if not jd:
        return None, [], []

    resume = _clean(resume_skills)
    resume_set = set(resume)

    credits: dict[str, float] = {}
    best: dict[str, tuple[str | None, float]] = {}

    to_embed_jd: list[str] = []
    for j in jd:
        if j in resume_set:
            credits[j] = 1.0
            best[j] = (j, 1.0)
        else:
            to_embed_jd.append(j)

    if to_embed_jd and resume:
        # One batched call for everything not settled by exact match.
        texts = list(dict.fromkeys(to_embed_jd + resume))
        vectors = dict(zip(texts, embed(texts)))
        for j in to_embed_jd:
            sim, who = max(
                ((cosine(vectors[j], vectors[r]), r) for r in resume),
                key=lambda t: t[0],
            )
            credits[j] = _credit(sim, weights.sim_low, weights.sim_high)
            best[j] = (who, sim)
    else:
        for j in to_embed_jd:
            credits[j] = 0.0
            best[j] = (None, 0.0)

    matched, missing = [], []
    for j in jd:
        who, sim = best[j]
        if credits[j] >= _MATCHED_CREDIT:
            matched.append(
                {
                    "jd_skill": j,
                    "resume_skill": who,
                    "similarity": round(sim, 3),
                    "credit": round(credits[j], 3),
                }
            )
        else:
            missing.append(j)

    return sum(credits.values()) / len(jd), matched, missing


def experience_score(months: int | None, scale_months: int = 48) -> float:
    """0..1, strictly increasing in months and saturating toward 1.
    Unknown or non-positive experience is 0 (no credit, not a crash)."""
    if months is None or months <= 0 or scale_months <= 0:
        return 0.0
    return 1.0 - math.exp(-months / scale_months)


def compute_match(
    *,
    resume_skills: list[str] | None,
    resume_months: int | None,
    jd_skills: list[str] | None,
    jd_min_months: int | None,
    embed: Embedder,
    weights: MatchWeights | None = None,
) -> MatchResult:
    w = weights or MatchWeights()

    skills_score, matched, missing = score_skills(resume_skills, jd_skills, embed, w)
    exp_score = experience_score(resume_months, w.experience_scale_months)

    w_skills = max(0.0, w.skills)
    w_exp = max(0.0, w.experience)
    total_w = w_skills + w_exp

    if skills_score is None or total_w <= 0:
        # Nothing to match the resume against (JD lists no skills).
        final, used = 0.0, {}
    else:
        final = (w_skills * skills_score + w_exp * exp_score) / total_w
        used = {
            "skills": round(w_skills / total_w, 3),
            "experience": round(w_exp / total_w, 3),
        }

    meets_min: bool | None = None
    if jd_min_months and jd_min_months > 0 and resume_months is not None:
        meets_min = resume_months >= jd_min_months

    return MatchResult(
        score=round(final * 100, 1),
        skills_score=None if skills_score is None else round(skills_score, 3),
        experience_score=round(exp_score, 3),
        matched=matched,
        missing=missing,
        resume_months=resume_months,
        jd_min_months=jd_min_months,
        meets_min_experience=meets_min,
        weights_used=used,
        experience_scale_months=w.experience_scale_months,
    )
