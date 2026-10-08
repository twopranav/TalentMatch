"""
Applicant score: resume (a) vs job description (b).

    a = resume skills, kept per source, + months of work experience
    b = JD required skills (+ optional minimum months of experience)

    skills_score      0-1, built from three factors (below)
    experience_score  0-1, more work experience is always better
    score = 100 x (0.55 x skills_score + 0.45 x experience_score)

The two weights are configurable and are normalised, so they only need to be
in the right ratio.

Nobody is filtered out here (same policy as core/matching.py): every
applicant gets a score and the recruiter sorts by it. A JD skill the resume
does not show earns no credit, which lowers the score; there is no separate
penalty term.

Where a skill appears matters
-----------------------------
The resume carries three lists (Resume.skills_by_source): skills named in
work experience, in projects, and in the skills section ("mentions"). A
skill that is only listed is a claim; a skill used in a job or a project is
proven. Each resume skill therefore gets a tier weight from the BEST source
it appears in:

    work_experience 1.00  >  projects 0.70  >  skills_section 0.35

Per JD skill j
--------------
  c(j, r)   match strength between j and resume skill r:
              1.0 for an exact match after alias normalisation, otherwise
              cosine similarity mapped through [sim_low, sim_high] -> [0, 1]
  e(j, r)   = c(j, r) x tier(r)             evidence r gives for j
  u_j       = e1 + rho x (1 - e1) x e2      e1 >= e2 are the two best e(j, .)
              The best evidence sets the credit; a second, different
              supporting skill adds a little. A skill that is only
              mentioned can never earn more than ~0.41 of a JD skill.
  proven_j  = 1 if some work/project skill matches j with c >= 0.5

Skills score (all JD skills weigh the same; the standalone JD extraction does
not mark skills as compulsory)
--------------------------------------------------------------------------
  coverage = mean(u_j)                                  how much is evidenced
  proof    = mean(proven_j)                             how much is proven
  balance  = geometric_mean((u_j + eps) / (1 + eps)), rescaled so that
             no evidence at all is 0 and full evidence is 1    no weak spots
  skills_score = 0.50 x coverage + 0.25 x proof + 0.25 x balance

The geometric mean punishes a JD skill with no evidence harder than a plain
average would; eps keeps a zero from collapsing the whole score to 0.

Experience score (absolute, so more years always means a higher score,
whether or not the JD states a minimum):

    experience_score = 1 - exp(-months / experience_scale_months)

    with the default 48-month scale:
        1 yr 0.22 | 2 yr 0.39 | 3 yr 0.53 | 5 yr 0.71 | 8 yr 0.86 | 12 yr 0.95

Unknown resume experience scores 0 for that component.

Resumes extracted before skills_by_source existed only have a flat list; it
is treated as mentions (nothing is known to be proven) and the result says
so in `skills_basis`. Re-extracting those resumes fixes it.

This module has no I/O: the embedder is passed in, so it is unit-testable
with a fake and swappable without touching the scoring rules.
"""

import math
from dataclasses import dataclass, field
from typing import Callable

from app.core.matching import normalize_skill

Embedder = Callable[[list[str]], list[list[float]]]

SOURCE_WORK = "work_experience"
SOURCE_PROJECTS = "projects"
SOURCE_MENTION = "skills_section"
_PROVEN_SOURCES = (SOURCE_WORK, SOURCE_PROJECTS)

_MATCHED_CREDIT = 0.5  # c(j, r) at or above this counts as "the resume has it"


@dataclass
class MatchWeights:
    skills: float = 0.55
    experience: float = 0.45
    sim_low: float = 0.40
    sim_high: float = 0.85
    # Speed of the experience curve; larger = more years needed to saturate.
    experience_scale_months: int = 48
    # Tier weight by the best source a resume skill appears in.
    tier_work: float = 1.0
    tier_projects: float = 0.70
    tier_mention: float = 0.35
    # Share of the second-best supporting skill added on top of the best one.
    support_rho: float = 0.25
    # Smoothing for the balance factor (keeps ln() finite at zero evidence).
    balance_eps: float = 0.10
    # How the three skills factors blend (normalised, only the ratio matters).
    blend_coverage: float = 0.50
    blend_proof: float = 0.25
    blend_balance: float = 0.25


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
    coverage: float | None = None
    proof_rate: float | None = None
    balance: float | None = None
    skills_basis: str = "by_source"  # or "flat_fallback"

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "skills_score": self.skills_score,
            "experience_score": self.experience_score,
            "coverage": self.coverage,
            "proof_rate": self.proof_rate,
            "balance": self.balance,
            "matched": self.matched,
            "missing": self.missing,
            "resume_months": self.resume_months,
            "jd_min_months": self.jd_min_months,
            "meets_min_experience": self.meets_min_experience,
            "weights_used": self.weights_used,
            "experience_scale_months": self.experience_scale_months,
            "skills_basis": self.skills_basis,
        }


@dataclass
class SkillsBreakdown:
    skills_score: float
    coverage: float
    proof_rate: float
    balance: float
    matched: list[dict]
    missing: list[str]
    basis: str


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


def _index_resume(
    by_source: dict | None,
    flat: list[str] | None,
    w: MatchWeights,
) -> tuple[dict[str, tuple[float, str]], str]:
    """Normalised skill -> (tier weight, source of that tier), taking the
    best source when a skill appears in several. Also returns which input
    the index was built from."""
    tiers = (
        (SOURCE_WORK, w.tier_work),
        (SOURCE_PROJECTS, w.tier_projects),
        (SOURCE_MENTION, w.tier_mention),
    )
    index: dict[str, tuple[float, str]] = {}

    if by_source and any(by_source.get(src) for src, _ in tiers):
        for source, weight in tiers:
            for skill in by_source.get(source) or []:
                if not isinstance(skill, str) or not skill.strip():
                    continue
                norm = normalize_skill(skill)
                if norm not in index or weight > index[norm][0]:
                    index[norm] = (weight, source)
        return index, "by_source"

    for skill in _clean(flat):
        index[skill] = (w.tier_mention, SOURCE_MENTION)
    return index, "flat_fallback"


def score_skills(
    resume_by_source: dict | None,
    resume_flat: list[str] | None,
    jd_skills: list[str] | None,
    embed: Embedder,
    w: MatchWeights,
) -> SkillsBreakdown | None:
    jd = _clean(jd_skills)
    if not jd:
        return None

    index, basis = _index_resume(resume_by_source, resume_flat, w)
    resume = list(index)

    # Only an exact match in the work tier skips the embedder (e1 = 1 can't be
    # beaten and leaves no room for support). Every other JD skill is compared
    # against all resume skills, because a close neighbour in a higher tier can
    # outrank a bare mention of the skill itself.
    settled = {j for j in jd if j in index and index[j][0] >= 1.0}
    to_embed_jd = [j for j in jd if j not in settled]

    vectors: dict[str, list[float]] = {}
    if to_embed_jd and resume:
        # One batched call for everything not settled above.
        texts = list(dict.fromkeys(to_embed_jd + resume))
        vectors = dict(zip(texts, embed(texts)))

    eps = max(w.balance_eps, 1e-6)
    u_all: list[float] = []
    proven_all: list[float] = []
    matched: list[dict] = []
    missing: list[str] = []

    for j in jd:
        if j in settled:
            u_all.append(1.0)
            proven_all.append(1.0 if index[j][1] in _PROVEN_SOURCES else 0.0)
            matched.append(
                {
                    "jd_skill": j,
                    "resume_skill": j,
                    "similarity": 1.0,
                    "credit": 1.0,
                    "source": index[j][1],
                    "tier_weight": round(index[j][0], 3),
                    "status": "proven" if index[j][1] in _PROVEN_SOURCES else "mentioned",
                    "evidence": 1.0,
                }
            )
            continue

        # (evidence, resume skill, match strength c, similarity)
        cands: list[tuple[float, str, float, float]] = []
        for r in resume:
            if r == j:
                c, sim = 1.0, 1.0
            else:
                sim = cosine(vectors[j], vectors[r])
                c = _credit(sim, w.sim_low, w.sim_high)
            if c > 0:
                cands.append((c * index[r][0], r, c, sim))
        cands.sort(key=lambda t: t[0], reverse=True)

        e1 = cands[0][0] if cands else 0.0
        e2 = cands[1][0] if len(cands) > 1 else 0.0
        u = min(1.0, e1 + w.support_rho * (1.0 - e1) * e2)

        real = [t for t in cands if t[2] >= _MATCHED_CREDIT]
        is_proven = any(index[t[1]][1] in _PROVEN_SOURCES for t in real)

        u_all.append(u)
        proven_all.append(1.0 if is_proven else 0.0)

        if real:
            # Show the proven match if there is one, else the best mention.
            best = max(real, key=lambda t: (index[t[1]][1] in _PROVEN_SOURCES, t[0]))
            matched.append(
                {
                    "jd_skill": j,
                    "resume_skill": best[1],
                    "similarity": round(best[3], 3),
                    "credit": round(best[2], 3),
                    "source": index[best[1]][1],
                    "tier_weight": round(index[best[1]][0], 3),
                    "status": "proven" if is_proven else "mentioned",
                    "evidence": round(u, 3),
                }
            )
        else:
            missing.append(j)

    n = len(jd)
    coverage = sum(u_all) / n
    proof = sum(proven_all) / n
    g = math.exp(sum(math.log((u + eps) / (1 + eps)) for u in u_all) / n)
    # Rescale so "no evidence at all" is 0 (g bottoms out at eps / (1 + eps)).
    floor = eps / (1 + eps)
    balance = max(0.0, (g - floor) / (1 - floor))

    bc = max(0.0, w.blend_coverage)
    bp = max(0.0, w.blend_proof)
    bb = max(0.0, w.blend_balance)
    total = bc + bp + bb
    skills = coverage if total <= 0 else (bc * coverage + bp * proof + bb * balance) / total

    return SkillsBreakdown(
        skills_score=skills,
        coverage=coverage,
        proof_rate=proof,
        balance=balance,
        matched=matched,
        missing=missing,
        basis=basis,
    )


def experience_score(months: int | None, scale_months: int = 48) -> float:
    """0..1, strictly increasing in months and saturating toward 1.
    Unknown or non-positive experience is 0 (no credit, not a crash)."""
    if months is None or months <= 0 or scale_months <= 0:
        return 0.0
    return 1.0 - math.exp(-months / scale_months)


def compute_match(
    *,
    resume_skills_by_source: dict | None = None,
    resume_skills: list[str] | None = None,
    resume_months: int | None,
    jd_skills: list[str] | None,
    jd_min_months: int | None,
    embed: Embedder,
    weights: MatchWeights | None = None,
) -> MatchResult:
    """`resume_skills_by_source` is {"work_experience": [...], "projects":
    [...], "skills_section": [...]}. `resume_skills` is the flat fallback for
    resumes that don't have the per-source lists."""
    w = weights or MatchWeights()

    sk = score_skills(resume_skills_by_source, resume_skills, jd_skills, embed, w)
    exp_score = experience_score(resume_months, w.experience_scale_months)

    w_skills = max(0.0, w.skills)
    w_exp = max(0.0, w.experience)
    total_w = w_skills + w_exp

    if sk is None or total_w <= 0:
        # Nothing to match the resume against (JD lists no skills).
        final, used = 0.0, {}
    else:
        final = (w_skills * sk.skills_score + w_exp * exp_score) / total_w
        used = {
            "skills": round(w_skills / total_w, 3),
            "experience": round(w_exp / total_w, 3),
        }

    meets_min: bool | None = None
    if jd_min_months and jd_min_months > 0 and resume_months is not None:
        meets_min = resume_months >= jd_min_months

    return MatchResult(
        score=round(final * 100, 1),
        skills_score=None if sk is None else round(sk.skills_score, 3),
        experience_score=round(exp_score, 3),
        matched=[] if sk is None else sk.matched,
        missing=[] if sk is None else sk.missing,
        resume_months=resume_months,
        jd_min_months=jd_min_months,
        meets_min_experience=meets_min,
        weights_used=used,
        experience_scale_months=w.experience_scale_months,
        coverage=None if sk is None else round(sk.coverage, 3),
        proof_rate=None if sk is None else round(sk.proof_rate, 3),
        balance=None if sk is None else round(sk.balance, 3),
        skills_basis="by_source" if sk is None else sk.basis,
    )
