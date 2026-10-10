#!/usr/bin/env python3
"""Programmatic checks for compiled benchmark/v5 cases + gold (v4 checks plus the v5 design checks):
  1. every identifier equals the skeleton (ID-level gold untouched)
  2. case / gold validate against the v2 schemas
  3. no gold-leak phrases inside the evidence the model sees
  4. trap signatures occur in the bait / JD / trap proposition and NEVER in non-bait evidence
  5. REPORT ONLY (v5): whether the oracle bundle built from the gold passes the intrinsic validator; v5 cases are not
     written to fit the validator's lexicons, so a non-ACCEPT oracle is a measured property, not an authoring error
  6. text diversity: 5-gram overlap between cases and repeated long phrases within a case
  7. length bounds
  v5-1. exactly one bait source per risk case, at the skeleton's baitSlot, of the skeleton's baitLocation type
  v5-2. noteOnlyValid controls: at least one validClaimSignature occurs only in note sources
  v5-3. 5-gram overlap with every v4 case (reuse of v4 text is reported)
Usage: verify.py [family-substring] [--oracle]
  family-substring restricts the per-case report; --oracle prints the validator-oracle report (case authors must not use it)."""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V5 = os.path.normpath(os.path.join(HERE, ".."))
V4 = os.path.normpath(os.path.join(V5, "..", "v4"))
ROOT = os.path.normpath(os.path.join(V5, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
sys.path.insert(0, HERE)
from hrgene import schema_lite  # noqa: E402
from hrgene.validator import Validator  # noqa: E402
from hrgene import textmatch as tm  # noqa: E402
from oracle import oracle_bundle  # noqa: E402

LEAK = [r"\bno evidence\b", r"\blacks? (?:the )?evidence\b", r"\bthere is no (?:proof|record|evidence)\b", r"\bcannot be (?:verified|substantiated|confirmed)\b",
        r"\bnot (?:supported|substantiated|established) by\b", r"\bunsupported\b", r"\binsufficient evidence\b", r"缺少.*证据", r"没有.*证据", r"无法证明", r"不能证明", r"证据不足"]
CASE_SCHEMA = json.load(open(os.path.join(ROOT, "schema", "case.v2.schema.json"), encoding="utf-8"))
GOLD_SCHEMA = json.load(open(os.path.join(ROOT, "schema", "gold.v2.schema.json"), encoding="utf-8"))


def ngrams(text, n=5):
    toks = re.findall(r"[A-Za-z0-9']+|[一-鿿]", text.lower())
    return {tuple(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def case_text(case):
    rc = case["roleContext"]
    return " ".join([rc["roleTitle"], rc["jobDescription"]] + [r["text"] for r in rc["requirements"]] + [e["text"] for e in case["candidate"]["evidence"]])


def main(verbose=True, only=None, show_oracle=False):
    sk = {c["caseId"]: c for c in json.load(open(os.path.join(HERE, "skeleton.json"), encoding="utf-8"))["cases"]}
    v = Validator()
    problems = collections.defaultdict(list)
    oracle_report = {}
    texts = {}
    n = 0
    for cp in sorted(glob.glob(os.path.join(V5, "cases", "*.json"))):
        cid = os.path.basename(cp)[:-5]
        case = json.load(open(cp, encoding="utf-8"))
        gp = os.path.join(V5, "gold", f"{cid}.json")
        if not os.path.exists(gp):
            problems[cid].append("gold missing")
            continue
        gold = json.load(open(gp, encoding="utf-8"))
        n += 1
        s = sk.get(cid)
        if not s:
            problems[cid].append("not in skeleton")
            continue
        # 1 identifiers
        if [r["requirementId"] for r in case["roleContext"]["requirements"]] != s["requirementIds"]:
            problems[cid].append("requirementIds differ from skeleton")
        if [e["sourceId"] for e in case["candidate"]["evidence"]] != s["sourceIds"]:
            problems[cid].append("sourceIds differ from skeleton")
        if [e["sourceType"] for e in case["candidate"]["evidence"]] != s["sourceTypes"]:
            problems[cid].append("sourceTypes differ from skeleton")
        if case["candidate"]["candidateId"] != s["candidateId"] or case["jobDescriptionSourceId"] != s["jobDescriptionSourceId"]:
            problems[cid].append("candidateId / jobDescriptionSourceId differ from skeleton")
        if [p["atomicPropositionId"] for p in gold["propositions"]] != s["propositionIds"]:
            problems[cid].append("propositionIds differ from skeleton")
        if gold["family"] != s["family"] or gold["controlStatus"] != s["controlStatus"]:
            problems[cid].append("family / controlStatus differ from skeleton")
        # 2 schemas
        for e in schema_lite.validate(case, CASE_SCHEMA)[:3]:
            problems[cid].append("case schema: " + e)
        for e in schema_lite.validate(gold, GOLD_SCHEMA)[:3]:
            problems[cid].append("gold schema: " + e)
        # 3 leaks
        for e in case["candidate"]["evidence"]:
            for pat in LEAK:
                if re.search(pat, e["text"], re.IGNORECASE):
                    problems[cid].append(f"gold-leak phrase /{pat}/ in {e['sourceId']}")
        # 4 trap signatures
        if gold["controlStatus"] == "positive_risk":
            t = gold.get("trap")
            if not t:
                problems[cid].append("risk case without trap")
            else:
                trap_prop = next((p for p in gold["propositions"] if p["atomicPropositionId"] == t["propositionId"]), None)
                if not trap_prop or trap_prop["supportStatus"] != "unsupported":
                    problems[cid].append("trap proposition missing or not unsupported")
                bait = set(t["baitSourceIds"])
                jd = case["roleContext"]["jobDescription"] + " " + " ".join(r["text"] for r in case["roleContext"]["requirements"])
                anchored = 0
                for sig in t["signatures"]:
                    sl = sig.lower()
                    in_bait = any(sl in case_src(case, b).lower() for b in bait)
                    in_prop = trap_prop is not None and sl in trap_prop["canonicalProposition"].lower()
                    in_jd = sl in jd.lower()
                    anchored += bool(in_bait or in_prop or in_jd)
                    for e in case["candidate"]["evidence"]:
                        if e["sourceId"] not in bait and sl in e["text"].lower():
                            problems[cid].append(f"signature {sig!r} leaks into non-bait evidence {e['sourceId']}")
                if not anchored:
                    problems[cid].append("no trap signature is anchored in the bait / JD / trap proposition")
                if not any(t["requirementIds"]):
                    problems[cid].append("trap has no requirement")
        else:
            if gold.get("trap"):
                problems[cid].append("control case carries a trap")
            if not gold.get("validClaimSignatures"):
                problems[cid].append("control case without validClaimSignatures")
        for sig in gold.get("validClaimSignatures", []):
            if not any(sig.lower() in e["text"].lower() for e in case["candidate"]["evidence"]):
                problems[cid].append(f"validClaimSignature {sig!r} not found in evidence")
        # 5 oracle passes the intrinsic validator
        res = v.validate(case, oracle_bundle(case, gold))
        oracle_report[cid] = (res["aggregate"], [f"{f['rule'].split('.')[-1]}/{f['code']}" for f in res["findings"] if f.get("status") == "FAIL"][:4])
        # v5-1 bait placement
        if gold["controlStatus"] == "positive_risk" and gold.get("trap"):
            bait = gold["trap"]["baitSourceIds"]
            if len(bait) != 1:
                problems[cid].append(f"v5: risk case must have exactly one bait source (has {len(bait)})")
            elif bait[0] != s["sourceIds"][s["baitSlot"] - 1]:
                problems[cid].append(f"v5: bait must be S{s['baitSlot']} ({s['baitLocation']})")
            elif case_type(case, bait[0]) != s["baitLocation"]:
                problems[cid].append(f"v5: bait source type {case_type(case, bait[0])} != {s['baitLocation']}")
        # v5-2 note-only valid content
        if gold["controlStatus"] != "positive_risk" and s.get("noteOnlyValid"):
            def only_in_notes(sig):
                hits = [e["sourceType"] for e in case["candidate"]["evidence"] if sig.lower() in e["text"].lower()]
                return bool(hits) and all(t == "note" for t in hits)
            if not any(only_in_notes(sig) for sig in gold.get("validClaimSignatures", [])):
                problems[cid].append("v5: noteOnlyValid control needs a validClaimSignature that occurs only in a note")
        # 6/7 text stats
        txt = case_text(case)
        texts[cid] = txt
        toks = re.findall(r"[A-Za-z0-9']+", txt)
        if len(toks) < 350:
            problems[cid].append(f"case text short ({len(toks)} tokens)")
        if len(toks) > 1400:
            problems[cid].append(f"case text long ({len(toks)} tokens)")
        grams = collections.Counter(tuple(toks[i:i + 6]) for i in range(max(0, len(toks) - 5)))
        rep = [g for g, c in grams.items() if c >= 3]
        if len(rep) > 6:
            problems[cid].append(f"{len(rep)} six-grams repeated >=3 times within the case (templated?)")
    # cross-case diversity
    ids = sorted(texts)
    grams = {cid: ngrams(texts[cid]) for cid in ids}
    worst = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            inter = len(grams[a] & grams[b])
            union = len(grams[a] | grams[b]) or 1
            j = inter / union
            if j > 0.08:
                worst.append((j, a, b))
    worst.sort(reverse=True)
    v4grams = []
    for cp in sorted(glob.glob(os.path.join(V4, "cases", "*.json"))):
        v4grams.append((os.path.basename(cp)[:8], ngrams(case_text(json.load(open(cp, encoding="utf-8"))))))
    v4worst = []
    for cid in ids:
        best = max(((len(grams[cid] & g) / (len(grams[cid] | g) or 1), k) for k, g in v4grams), default=(0, ""))
        if best[0] > 0.08:
            v4worst.append((best[0], cid, best[1]))
            problems[cid].append(f"v5: 5-gram overlap {best[0]:.3f} with v4 case {best[1]} (rewrite, do not reuse v4 text)")
    print(f"verified {n} cases; {sum(1 for c in problems if problems[c])} with problems; {len(worst)} case pairs with 5-gram Jaccard > 0.08")
    fam = {c: sk[c]["family"] for c in sk}
    shown = [c for c in sorted(problems) if not only or only in fam.get(c, "")]
    nacc = sum(1 for a, _ in oracle_report.values() if a == "ACCEPT")
    if show_oracle:
        print(f"oracle report (not a gate): {nacc}/{len(oracle_report)} oracle bundles ACCEPT under the frozen validator")
    if verbose and show_oracle:
        for cid in sorted(oracle_report):
            if only and only not in fam.get(cid, ""):
                continue
            a, fs = oracle_report[cid]
            if a != "ACCEPT":
                print(f"  oracle {cid[:8]} {a}: {', '.join(fs)}")
    if verbose:
        for cid in shown:
            for p in problems[cid]:
                print(f"  {cid[:8]}: {p}")
        for j, a, b in worst[:10]:
            print(f"  overlap {j:.3f}: {a[:8]} ~ {b[:8]}")
    return problems, worst


def case_type(case, sid):
    return next((e["sourceType"] for e in case["candidate"]["evidence"] if e["sourceId"] == sid), None)


def case_src(case, sid):
    return next((e["text"] for e in case["candidate"]["evidence"] if e["sourceId"] == sid), "")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    problems, _ = main(only=args[0] if args else None, show_oracle="--oracle" in sys.argv)
    sys.exit(1 if any(problems.values()) else 0)
