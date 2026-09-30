"""
Applicant score: resume (a) vs job description (b).

    a = resume skills + months of experience
    b = JD required skills + minimum months of experience
    score = weighted blend of
              skills      semantic match of every JD skill against the resume's skills
              experience  resume_months / jd_min_months, capped at 1

Nobody is filtered out here (same policy as core/matching.py): every
applicant gets a score and the recruiter sorts by it.

Skills are matched one JD skill at a time rather than by embedding the two
whole documents, because (1) the recruiter can then see exactly which JD
skills were covered and by what ("kubernetes" <- "k8s", 0.91), and (2) a
single blended vector is poor at "did they cover ALL of these" and blind to
numbers such as years of experience, which is why experience is scored
numerically instead of semantically.

Per JD skill:
  * exact match after alias normalisation (matching.normalize_skill) -> 1.0,
    no embedding call
  * otherwise the best cosine similarity against the resume's skills,
    mapped through [sim_low, sim_high] -> [0, 1]

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
    skills: float = 0.8
    experience: float = 0.2
    sim_low: float = 0.40
    sim_high: float = 0.85


@dataclass
class MatchResult:
    score: float  # 0-100, one decimal
    skills_score: float | None  # 0-1, None if the JD lists no skills
    experience_score: float | None  # 0-1, None if the JD sets no minimum
    matched: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    resume_months: int | None = None
    jd_min_months: int | None = None
    weights_used: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "skills_score": self.skills_score,
            "experience_score": self.experience_score,
            "matched": self.matched,
            "missing": self.missing,
            "resume_months": self.resume_months,
            "jd_min_months": self.jd_min_months,
            "weights_used": self.weights_used,
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


def score_experience(
    resume_months: int | None,
    jd_min_months: int | None,
) -> float | None:
    """None = the JD sets no minimum, so experience is not part of the score.
    0 months required (fresher marker) is treated the same way.
    Unknown resume experience against a real requirement scores 0."""
    if not jd_min_months or jd_min_months <= 0:
        return None
    if resume_months is None or resume_months <= 0:
        return 0.0
    return min(1.0, resume_months / jd_min_months)


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
    exp_score = score_experience(resume_months, jd_min_months)

    parts: list[tuple[str, float, float]] = []
    if skills_score is not None:
        parts.append(("skills", w.skills, skills_score))
    if exp_score is not None:
        parts.append(("experience", w.experience, exp_score))

    total_w = sum(p[1] for p in parts)
    if not parts or total_w <= 0:
        final, used = 0.0, {}
    else:
        final = sum(weight * value for _, weight, value in parts) / total_w
        used = {name: round(weight / total_w, 3) for name, weight, _ in parts}

    return MatchResult(
        score=round(final * 100, 1),
        skills_score=None if skills_score is None else round(skills_score, 3),
        experience_score=None if exp_score is None else round(exp_score, 3),
        matched=matched,
        missing=missing,
        resume_months=resume_months,
        jd_min_months=jd_min_months,
        weights_used=used,
    )
