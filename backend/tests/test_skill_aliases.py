"""
Data-integrity tests for the skill alias table.

These guard the *shape* of the data in app/core/skill_aliases.py, so a bad
edit to the table fails loudly in CI instead of silently mis-matching
candidates in production.
"""

from collections import defaultdict

from app.core.matching import normalize_skill
from app.core.skill_aliases import CURATED_ALIASES, EXTRA_GROUPS, SKILL_ALIASES


def test_skill_aliases_are_acyclic() -> None:
    """No canonical target may itself be an alias key (prevents multi-hop chains)."""
    alias_keys = set(SKILL_ALIASES)

    for alias, target in SKILL_ALIASES.items():
        assert target not in alias_keys, (
            f"'{target}' (target of '{alias}') is also an alias key"
        )


def test_no_alias_is_claimed_by_two_skills() -> None:
    """
    setdefault() in the builder keeps the first claimant and silently drops
    the rest, so a clash would never raise. This makes it loud.
    """
    claimed_by = defaultdict(set)
    for canonical, variants in EXTRA_GROUPS.items():
        for variant in variants:
            claimed_by[variant.strip().lower()].add(canonical)

    clashes = {a: sorted(c) for a, c in claimed_by.items() if len(c) > 1}
    assert not clashes, f"aliases claimed by more than one skill: {clashes}"


def test_curated_entries_win_over_bulk_entries() -> None:
    for alias, canonical in CURATED_ALIASES.items():
        assert SKILL_ALIASES[alias] == canonical


def test_alias_keys_are_already_normalized() -> None:
    """normalize_skill() lowercases and strips input before lookup, so a key
    with capitals or stray spaces could never be found."""
    bad = [k for k in SKILL_ALIASES if k != k.strip().lower()]
    assert not bad, f"keys that can never match: {bad}"


def test_normalize_skill_uses_the_merged_table() -> None:
    assert normalize_skill("  Python 3.11 ") == "python"      # bulk table
    assert normalize_skill("py") == "python"                   # curated table
    assert normalize_skill("Totally Unknown") == "totally unknown"