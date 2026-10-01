"""
Skill normalization and matching for candidate ranking.

No elimination happens here or anywhere downstream of it: every
applicant who applies is scored and ranked, never filtered out for
missing compulsory skills, a missing skills section, or anything else.
compulsory_skill_match_ratio() feeds the *score* -- it does not gate
who gets scored. Recruiters see the full applicant list, sorted by
score, and make the final call themselves.
"""

from app.core.skill_aliases import SKILL_ALIASES


def compulsory_skill_match_ratio(
    matched_count: int,
    compulsory_count: int,
) -> float:
    """
    Fraction of compulsory JD skills the candidate matched, in [0, 1].

    This is one input into the eventual weighted score (alongside
    experience/education matching) -- NOT a pass/fail gate. A candidate
    who matches 0 of 3 compulsory skills still gets scored and shown to
    the recruiter; they just score lower on this component.

    A JD with no compulsory skills contributes a neutral 1.0, since
    there's nothing explicit to score against.
    """
    if compulsory_count == 0:
        return 1.0

    return min(matched_count / compulsory_count, 1.0)


def test_skill_aliases_are_acyclic() -> None:
    """
    Ensure no canonical alias target is itself another alias key.

    This prevents accidental multi-hop normalization.
    """
    alias_keys = set(SKILL_ALIASES)

    for value in SKILL_ALIASES.values():
        assert value not in alias_keys, (
            f"'{value}' is both an alias target and an alias key"
        )


def normalize_skill(raw: str) -> str:
    """
    Normalize one skill for matching.
    """
    key = raw.strip().lower()
    return SKILL_ALIASES.get(key, key)


def normalize_skills(skills: list[str]) -> set[str]:
    """
    Normalize and deduplicate a skill collection.
    """
    return {
        normalize_skill(skill)
        for skill in skills
        if skill and skill.strip()
    }


def count_matched_skills(
    candidate_skills: list[str],
    jd_skills: list[str],
) -> int:
    """
    Count normalized JD skills present in candidate skills.
    """
    candidate_set = normalize_skills(candidate_skills)

    return sum(
        1
        for skill in jd_skills
        if normalize_skill(skill) in candidate_set
    )


def count_matched_compulsory_skills(
    candidate_skills: list[str],
    compulsory_skills: list[str],
) -> int:
    """
    Count only explicitly compulsory JD skills matched by the candidate.

    Feeds compulsory_skill_match_ratio() for scoring -- not a gate.
    """
    return count_matched_skills(
        candidate_skills,
        compulsory_skills,
    )


# Backward-compatible alias for any older caller still using the old name.
def count_matched_required_skills(
    candidate_skills: list[str],
    required_skills: list[str],
) -> int:
    return count_matched_compulsory_skills(
        candidate_skills,
        required_skills,
    )