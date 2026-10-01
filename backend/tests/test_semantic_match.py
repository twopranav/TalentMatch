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
    "svelte": [0.7, 0.714],    # cos(react, svelte) ~= 0.70 -> partial credit
    "terraform": [0.0, 1.0],   # cos(react, terraform) = 0 -> no credit
    "python": [0.5, 0.5],
    "sql": [0.6, 0.4],
}


def fake_embed(texts):
    return [_VECS[t] for t in texts]


def exploding_embed(texts):
    raise AssertionError("embedder must not be called when everything matches exactly")


def test_cosine_basics():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 0]) == 0.0


def test_exact_match_after_alias_needs_no_embedding_call():
    r = compute_match(
        resume_skills=["Python", "K8s"],
        resume_months=None,
        jd_skills=["python", "kubernetes"],
        jd_min_months=None,
        embed=exploding_embed,
    )
    assert r.skills_score == 1.0
    assert r.score == 55.0  # perfect skills, no experience info -> skills weight only
    assert r.missing == []
    assert {m["jd_skill"] for m in r.matched} == {"python", "kubernetes"}


def test_close_synonym_earns_full_credit_unrelated_earns_none():
    r = compute_match(
        resume_skills=["vue"],
        resume_months=None,
        jd_skills=["react", "terraform"],
        jd_min_months=None,
        embed=fake_embed,
    )
    # react ~1.0; terraform: cos(vue, terraform) = 0.436 -> credit 0.08, below the
    # 'matched' cutoff so it is still reported as missing.
    assert r.skills_score == pytest.approx((1.0 + 0.08) / 2, abs=0.02)
    assert [m["jd_skill"] for m in r.matched] == ["react"]
    assert r.matched[0]["resume_skill"] == "vue"
    assert r.missing == ["terraform"]


def test_partial_similarity_earns_partial_credit():
    r = compute_match(
        resume_skills=["svelte"], resume_months=None,
        jd_skills=["react"], jd_min_months=None, embed=fake_embed,
    )
    # sim ~0.70 -> (0.70-0.40)/(0.85-0.40) ~= 0.67, counted as matched (>= .5)
    assert 0.55 < r.skills_score < 0.75
    assert r.matched and not r.missing


def test_experience_curve_is_absolute_and_saturating():
    assert experience_score(12, 48) == pytest.approx(0.221, abs=0.001)
    assert experience_score(24, 48) == pytest.approx(0.393, abs=0.001)
    assert experience_score(96, 48) == pytest.approx(0.865, abs=0.001)
    assert experience_score(24, 48) < experience_score(60, 48) < experience_score(240, 48) < 1.0


def test_unknown_or_zero_experience_scores_zero():
    assert experience_score(None) == 0.0
    assert experience_score(0) == 0.0


def test_experience_counts_even_when_jd_has_no_minimum():
    r = compute_match(
        resume_skills=["python"], resume_months=48,
        jd_skills=["python"], jd_min_months=None, embed=exploding_embed,
    )
    assert r.experience_score == pytest.approx(0.632, abs=0.001)
    assert r.weights_used == {"skills": 0.55, "experience": 0.45}
    assert r.meets_min_experience is None
    # 100 * (0.55 * 1.0 + 0.45 * 0.632) = 83.4
    assert r.score == pytest.approx(83.4, abs=0.1)


def test_default_weights_are_55_45_and_no_experience_caps_at_55():
    r = compute_match(
        resume_skills=["python"], resume_months=None,
        jd_skills=["python"], jd_min_months=None, embed=exploding_embed,
    )
    assert r.score == 55.0


def test_blend_uses_configured_weights():
    r = compute_match(
        resume_skills=["python"], resume_months=48,
        jd_skills=["python"], jd_min_months=None,   # skills 1.0, experience 0.632
        embed=exploding_embed,
        weights=MatchWeights(skills=0.5, experience=0.5),
    )
    assert r.score == pytest.approx(81.6, abs=0.1)


def test_weights_are_normalised():
    a = compute_match(
        resume_skills=["python"], resume_months=24, jd_skills=["python"],
        jd_min_months=None, embed=exploding_embed,
        weights=MatchWeights(skills=55, experience=45),
    )
    b = compute_match(
        resume_skills=["python"], resume_months=24, jd_skills=["python"],
        jd_min_months=None, embed=exploding_embed,
    )
    assert a.score == b.score


def test_meets_min_experience_flag_is_informational_only():
    low = compute_match(
        resume_skills=["python"], resume_months=12, jd_skills=["python"],
        jd_min_months=48, embed=exploding_embed,
    )
    same_no_min = compute_match(
        resume_skills=["python"], resume_months=12, jd_skills=["python"],
        jd_min_months=None, embed=exploding_embed,
    )
    assert low.meets_min_experience is False
    assert low.score == same_no_min.score


def test_no_resume_skills_scores_zero_without_calling_embedder():
    r = compute_match(
        resume_skills=[], resume_months=None,
        jd_skills=["python"], jd_min_months=None, embed=exploding_embed,
    )
    assert r.score == 0.0
    assert r.missing == ["python"]


def test_jd_without_skills_and_without_minimum_scores_zero_not_crash():
    r = compute_match(
        resume_skills=["python"], resume_months=60,
        jd_skills=[], jd_min_months=None, embed=exploding_embed,
    )
    assert r.score == 0.0
    assert r.skills_score is None


def test_duplicates_and_case_are_collapsed():
    r = compute_match(
        resume_skills=["Python", "python ", "PY"], resume_months=None,
        jd_skills=["python", "Python"], jd_min_months=None, embed=exploding_embed,
    )
    assert r.skills_score == 1.0
    assert len(r.matched) == 1
