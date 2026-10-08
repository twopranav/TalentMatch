"""
Pure tests for the applicant score (app/core/semantic_match.py).
No DB, Redis or network: the embedder is a fake with hand-picked vectors so
every expected number below is derivable by hand.
"""

import pytest

from app.core.semantic_match import MatchWeights, compute_match, cosine, experience_score


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield


# 2-d "embedding space": frontend-ish words point one way, ops-ish the other.
_VECS = {
    "react": [1.0, 0.0],
    "vue": [0.9, 0.436],       # cos(react, vue) ~= 0.90 -> full credit
    "svelte": [0.7, 0.714],    # cos(react, svelte) ~= 0.70 -> credit ~0.667
    "terraform": [0.0, 1.0],   # cos(react, terraform) = 0 -> no credit
    "python": [0.5, 0.5],
    "sql": [0.6, 0.4],
}


def fake_embed(texts):
    return [_VECS[t] for t in texts]


def orth_embed(texts):
    """Every distinct string gets its own axis: only exact matches score."""
    return [[1.0 if i == j else 0.0 for j in range(len(texts))] for i, _ in enumerate(texts)]


def exploding_embed(texts):
    raise AssertionError("embedder must not be called here")


def work(*skills):
    return {"work_experience": list(skills), "projects": [], "skills_section": []}


def projects(*skills):
    return {"work_experience": [], "projects": list(skills), "skills_section": []}


def mention(*skills):
    return {"work_experience": [], "projects": [], "skills_section": list(skills)}


def score_for(by_source, jd=("python",), months=None, embed=fake_embed):
    return compute_match(
        resume_skills_by_source=by_source, resume_months=months,
        jd_skills=list(jd), jd_min_months=None, embed=embed,
    )


def test_cosine_basics():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 0]) == 0.0


# ---------------------------------------------------------------- tiers ----

def test_exact_match_in_work_needs_no_embedding_call():
    r = compute_match(
        resume_skills_by_source=work("Python", "K8s"),
        resume_months=None,
        jd_skills=["python", "kubernetes"],
        jd_min_months=None,
        embed=exploding_embed,
    )
    assert r.skills_score == 1.0
    assert r.score == 55.0  # perfect skills, no experience info -> skills weight only
    assert r.missing == []
    assert {m["jd_skill"] for m in r.matched} == {"python", "kubernetes"}
    assert all(m["status"] == "proven" for m in r.matched)


def test_same_skill_scores_work_over_projects_over_mention():
    w = score_for(work("python")).score
    p = score_for(projects("python")).score
    m = score_for(mention("python")).score
    assert w > p > m > 0


def test_skill_in_several_sources_takes_the_highest_tier():
    both = score_for({"work_experience": [], "projects": ["python"], "skills_section": ["python"]})
    only_projects = score_for(projects("python"))
    assert both.score == only_projects.score
    assert both.matched[0]["source"] == "projects"

    top = score_for({"work_experience": ["python"], "projects": ["python"], "skills_section": ["python"]})
    assert top.matched[0]["source"] == "work_experience"
    assert top.skills_score == 1.0


def test_a_mention_alone_is_not_proof():
    r = score_for(mention("python"))
    assert r.proof_rate == 0.0
    assert r.matched[0]["status"] == "mentioned"
    # tier 0.35 only: coverage 0.35; with one JD skill balance equals it too
    assert r.coverage == pytest.approx(0.35, abs=0.001)
    assert r.balance == pytest.approx(0.35, abs=0.001)
    assert r.skills_score == pytest.approx(0.5 * 0.35 + 0.25 * 0.35, abs=0.002)


def test_a_project_is_proof():
    r = score_for(projects("python"))
    assert r.proof_rate == 1.0
    assert r.matched[0]["status"] == "proven"
    assert r.coverage == pytest.approx(0.70, abs=0.001)


def test_a_skill_listed_and_used_beats_the_same_skill_only_listed():
    listed_only = score_for(mention("python"), jd=("python", "sql"), embed=orth_embed)
    listed_and_used = score_for(
        {"work_experience": ["python"], "projects": [], "skills_section": ["python"]},
        jd=("python", "sql"), embed=orth_embed,
    )
    assert listed_and_used.score > listed_only.score


# ------------------------------------------------- more skills -> higher ----

def test_covering_more_jd_skills_scores_higher():
    jd = ("react", "python", "sql")
    one = score_for(work("react"), jd=jd, embed=orth_embed).score
    two = score_for(work("react", "python"), jd=jd, embed=orth_embed).score
    three = score_for(work("react", "python", "sql"), jd=jd, embed=orth_embed).score
    assert one < two < three


def test_missing_a_jd_skill_lowers_the_score_and_is_reported_missing():
    full = score_for(work("python", "react"), jd=("python", "react"), embed=orth_embed)
    short = score_for(work("python"), jd=("python", "react"), embed=orth_embed)
    assert short.score < full.score
    assert short.missing == ["react"]


def test_unrelated_skill_earns_nothing():
    r = score_for(work("terraform"), jd=("react",))
    assert r.coverage == 0.0
    assert r.missing == ["react"]
    assert r.score == 0.0


# ---------------------------------------------- semantic neighbours / support

def test_close_synonym_in_work_earns_full_credit():
    r = score_for(work("vue"), jd=("react",))
    assert r.coverage == pytest.approx(1.0, abs=0.001)
    assert r.matched[0]["resume_skill"] == "vue"


def test_partial_similarity_earns_partial_credit():
    r = score_for(work("svelte"), jd=("react",))
    # sim ~0.70 -> credit ~0.667, tier 1.0
    assert 0.6 < r.coverage < 0.75
    assert r.matched and not r.missing


def test_second_supporting_skill_adds_a_little():
    alone = score_for(projects("vue"), jd=("react",))
    with_support = score_for(projects("vue", "svelte"), jd=("react",))
    assert alone.matched[0]["evidence"] == pytest.approx(0.70, abs=0.001)
    # 0.70 + 0.25 * (1 - 0.70) * (0.667 * 0.70) = 0.735
    assert with_support.matched[0]["evidence"] == pytest.approx(0.735, abs=0.002)
    assert with_support.score > alone.score


def test_mentions_can_never_reach_the_proven_range():
    r = score_for(mention("vue", "svelte"), jd=("react",))
    # 0.35 + 0.25 * 0.65 * (0.667 * 0.35) ~= 0.388, always below 0.41
    assert r.matched[0]["evidence"] < 0.41
    assert r.matched[0]["status"] == "mentioned"


# ----------------------------------------------------------- fallback ------

def test_flat_list_without_sources_is_treated_as_mentions():
    flat = compute_match(
        resume_skills=["python"], resume_months=None,
        jd_skills=["python"], jd_min_months=None, embed=fake_embed,
    )
    as_mention = score_for(mention("python"))
    assert flat.skills_basis == "flat_fallback"
    assert as_mention.skills_basis == "by_source"
    assert flat.score == as_mention.score
    assert flat.matched[0]["status"] == "mentioned"


def test_empty_by_source_falls_back_to_the_flat_list():
    r = compute_match(
        resume_skills_by_source={"work_experience": [], "projects": [], "skills_section": []},
        resume_skills=["python"], resume_months=None,
        jd_skills=["python"], jd_min_months=None, embed=fake_embed,
    )
    assert r.skills_basis == "flat_fallback"


# ------------------------------------------------------------ experience ---

def test_experience_curve_is_absolute_and_saturating():
    assert experience_score(12, 48) == pytest.approx(0.221, abs=0.001)
    assert experience_score(24, 48) == pytest.approx(0.393, abs=0.001)
    assert experience_score(96, 48) == pytest.approx(0.865, abs=0.001)
    assert experience_score(24, 48) < experience_score(60, 48) < experience_score(240, 48) < 1.0


def test_unknown_or_zero_experience_scores_zero():
    assert experience_score(None) == 0.0
    assert experience_score(0) == 0.0


def test_more_years_of_work_experience_always_ranks_higher():
    scores = [score_for(work("python"), months=m).score for m in (0, 6, 24, 60, 120, 240)]
    assert scores == sorted(scores)
    assert len(set(scores)) == len(scores)


def test_experience_counts_even_when_jd_has_no_minimum():
    r = compute_match(
        resume_skills_by_source=work("python"), resume_months=48,
        jd_skills=["python"], jd_min_months=None, embed=exploding_embed,
    )
    assert r.experience_score == pytest.approx(0.632, abs=0.001)
    assert r.weights_used == {"skills": 0.55, "experience": 0.45}
    assert r.meets_min_experience is None
    # 100 * (0.55 * 1.0 + 0.45 * 0.632) = 83.4
    assert r.score == pytest.approx(83.4, abs=0.1)


def test_blend_uses_configured_weights():
    r = compute_match(
        resume_skills_by_source=work("python"), resume_months=48,
        jd_skills=["python"], jd_min_months=None,   # skills 1.0, experience 0.632
        embed=exploding_embed,
        weights=MatchWeights(skills=0.5, experience=0.5),
    )
    assert r.score == pytest.approx(81.6, abs=0.1)


def test_weights_are_normalised():
    a = compute_match(
        resume_skills_by_source=work("python"), resume_months=24, jd_skills=["python"],
        jd_min_months=None, embed=exploding_embed,
        weights=MatchWeights(skills=55, experience=45),
    )
    b = compute_match(
        resume_skills_by_source=work("python"), resume_months=24, jd_skills=["python"],
        jd_min_months=None, embed=exploding_embed,
    )
    assert a.score == b.score


def test_meets_min_experience_flag_is_informational_only():
    low = compute_match(
        resume_skills_by_source=work("python"), resume_months=12, jd_skills=["python"],
        jd_min_months=48, embed=exploding_embed,
    )
    same_no_min = compute_match(
        resume_skills_by_source=work("python"), resume_months=12, jd_skills=["python"],
        jd_min_months=None, embed=exploding_embed,
    )
    assert low.meets_min_experience is False
    assert low.score == same_no_min.score


# ---------------------------------------------------------------- edges ----

def test_no_resume_skills_scores_zero_without_calling_embedder():
    r = compute_match(
        resume_skills_by_source=work(), resume_skills=[], resume_months=None,
        jd_skills=["python"], jd_min_months=None, embed=exploding_embed,
    )
    assert r.score == 0.0
    assert r.missing == ["python"]


def test_jd_without_skills_scores_zero_not_crash():
    r = compute_match(
        resume_skills_by_source=work("python"), resume_months=60,
        jd_skills=[], jd_min_months=None, embed=exploding_embed,
    )
    assert r.score == 0.0
    assert r.skills_score is None


def test_duplicates_case_and_aliases_are_collapsed():
    r = compute_match(
        resume_skills_by_source=work("Python", "python ", "PY"), resume_months=None,
        jd_skills=["python", "Python"], jd_min_months=None, embed=exploding_embed,
    )
    assert r.skills_score == 1.0
    assert len(r.matched) == 1


def test_a_gap_drags_balance_below_coverage():
    # one JD skill fully proven, the other absent
    r = score_for(work("python"), jd=("python", "react"), embed=orth_embed)
    assert r.coverage == pytest.approx(0.5, abs=0.001)
    assert r.balance < r.coverage
    assert r.proof_rate == 0.5
