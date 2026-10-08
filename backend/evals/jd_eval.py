"""python -m evals.jd_eval path/to/jds [--no-llm] [--draft]"""
import argparse
import json
import re
from pathlib import Path

from app.core.jd_skills_llm_extract import extract_jd_skills_with_meta
from app.core.jd_skills_locator import locate_jd_requirements
from app.core.skills_text_prep import (
    normalize_parentheses, postprocess_skills, strip_structural_labels,
)
from evals.jd_gold import GOLD_SECTIONS, GOLD_SKILLS

_BUL = re.compile(r"^\s*(\(cid:\d+\)|[-*•●–>])\s*")


def stem(fname):
    return re.sub(r"\s*\(\d+\)$", "", Path(fname).stem).lower()


def _eval_norm(value):
    value = value or ""
    value = value.replace("\u2018", "'").replace("\u2019", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    value = value.replace("\u2013", "-").replace("\u2014", "-")
    value = re.sub(r"^\s*(?:\(cid:\d+\)|[-*•●–>]|\d{1,2}[.)](?=\s))\s*", "", value)
    return " ".join(value.lower().split()).rstrip(":").strip()


def _last_line(text):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return lines[-1] if lines else None


def _close(a, b):
    a, b = " " + a.replace("/", " ") + " ", " " + b.replace("/", " ") + " "
    return a == b or a in b or b in a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jd_dir")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--draft", action="store_true")
    args = ap.parse_args()

    files = sorted(p for p in Path(args.jd_dir).iterdir()
                   if p.suffix.lower() in {".pdf", ".docx", ".txt"})
    by_stem = {stem(p.name): p for p in files}

    # ---- locate
    LOC = {}
    for p in files:
        try:
            LOC[p.name] = locate_jd_requirements(p.read_bytes(), p.name)
        except Exception as exc:
            LOC[p.name] = None
            print(f"locator FAILED {p.name}: {type(exc).__name__}: {exc}")

    # ---- eval 1: locator
    found_ok = head_ok = bound_ok = 0
    for gname, gold in GOLD_SECTIONS.items():
        p = by_stem.get(stem(gname))
        got = LOC.get(p.name) if p else None
        if got is None:
            print("FAIL (missing/failed):", gname)
            continue
        want_found = gold["heading"] is not None
        f_ok = bool(got["found"]) == want_found
        h_ok = (not got["found"] and not (got["heading"] or "").strip()) if not want_found \
            else got["found"] and _eval_norm(got["heading"]) == _eval_norm(gold["heading"])
        last = _last_line(got["section_text"])
        b_ok = (not got["found"] and not last) if gold["last_line"] is None \
            else got["found"] and _eval_norm(last) == _eval_norm(gold["last_line"])
        found_ok += f_ok; head_ok += h_ok; bound_ok += b_ok
        if not (f_ok and h_ok and b_ok):
            print(f"FAIL {p.name}\n  want {gold['heading']!r} / {gold['last_line']!r}\n"
                  f"  got  {got['heading']!r} / {last!r}")
    n = len(GOLD_SECTIONS)
    print(f"section found: {found_ok}/{n}  heading: {head_ok}/{n}  boundary: {bound_ok}/{n}")

    RES = {}
    if not args.no_llm:
        for name, sec in LOC.items():
            if not sec or not sec["found"] or not sec["section_text"].strip():
                RES[name] = {"error": "no requirements section located"}
                continue
            prepared = strip_structural_labels(normalize_parentheses(sec["section_text"])).strip()
            try:
                raw, meta = extract_jd_skills_with_meta(prepared)
            except Exception as exc:
                RES[name] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            final, dropped, _ = postprocess_skills(raw, source_text=prepared)
            RES[name] = {"error": None, "prepared": prepared, "final": final,
                         "dropped": dropped, "meta": meta}

        # ---- eval 2: skills
        TP = FP = FN = exact = checked = 0
        for gname, want_list in GOLD_SKILLS.items():
            p = by_stem.get(stem(gname))
            res = RES.get(p.name) if p else None
            if not res or res.get("error"):
                print("no LLM result:", gname, "->", (res or {}).get("error", "not run"))
                continue
            norm = lambda s: " ".join(str(s).lower().split())
            want = {norm(x) for x in want_list}
            got = {norm(x) for x in res["final"]}
            prepared = norm(res["prepared"].replace("\n", " "))
            missing = sorted(w for w in want if not any(_close(w, g) for g in got))
            extra = sorted(g for g in got if not any(_close(g, w) for w in want))
            TP += len(want) - len(missing); FP += len(extra); FN += len(missing)
            checked += 1; exact += int(not missing and not extra)
            if missing or extra or res["dropped"]:
                print(f"{p.name}\n  missing_upstream: {[m for m in missing if m not in prepared]}"
                      f"\n  missing_llm: {[m for m in missing if m in prepared]}"
                      f"\n  extra: {extra}\n  hallucinated_dropped: {res['dropped']}")
        pr = TP / (TP + FP) if TP + FP else 0.0
        rc = TP / (TP + FN) if TP + FN else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        print(f"files checked: {checked}/{len(GOLD_SKILLS)} | exact: {exact}/{checked}")
        print(f"precision {pr:.3f}  recall {rc:.3f}  f1 {f1:.3f}")

        # ---- token table
        tot_in = tot_out = 0
        for name, res in RES.items():
            m = res.get("meta")
            if not m:
                continue
            i, o, r = m["prompt_tokens"] or 0, m["completion_tokens"] or 0, m.get("reasoning_tokens")
            tot_in += i; tot_out += o
            print(f"{name}: in={i} reasoning={r if r is not None else 'n/a'} out={o}")
        print(f"TOTAL in={tot_in} out={tot_out} all={tot_in + tot_out}")

    # ---- optional draft answer keys (diagnostic only)
    if args.draft:
        ds, dk = {}, {}
        for name, sec in LOC.items():
            if sec is None:
                continue
            tail = [_BUL.sub("", l).strip() for l in sec["section_text"].splitlines() if l.strip()]
            ds[name] = {"heading": sec["heading"] if sec["found"] else None,
                        "last_line": tail[-1] if tail else None}
            r = RES.get(name)
            if r and not r.get("error"):
                dk[name] = r["final"]
        Path("jd_gold_draft.txt").write_text(
            "GOLD_SECTIONS = " + json.dumps(ds, indent=4, ensure_ascii=False)
            + "\n\nGOLD_SKILLS = " + json.dumps(dk, indent=4, ensure_ascii=False),
            encoding="utf-8")
        print("saved -> jd_gold_draft.txt")


if __name__ == "__main__":
    main()