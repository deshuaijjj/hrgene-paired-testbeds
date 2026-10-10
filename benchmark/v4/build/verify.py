#!/usr/bin/env python3
"""Programmatic checks for compiled benchmark/v4 cases + gold:
  1. every identifier equals the skeleton (ID-level gold untouched)
  2. case / gold validate against the v2 schemas
  3. no gold-leak phrases inside the evidence the model sees
  4. trap signatures occur in the bait / JD / trap proposition and NEVER in non-bait evidence
  5. the oracle bundle built from the gold passes the intrinsic validator (ACCEPT) - gold and lexicons agree
  6. text diversity: 5-gram overlap between cases and repeated long phrases within a case
  7. length bounds"""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V4 = os.path.normpath(os.path.join(HERE, ".."))
ROOT = os.path.normpath(os.path.join(V4, "..", ".."))
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


def main(verbose=True):
    sk = {c["caseId"]: c for c in json.load(open(os.path.join(HERE, "skeleton.json"), encoding="utf-8"))["cases"]}
    v = Validator()
    problems = collections.defaultdict(list)
    texts = {}
    n = 0
    for cp in sorted(glob.glob(os.path.join(V4, "cases", "*.json"))):
        cid = os.path.basename(cp)[:-5]
        case = json.load(open(cp, encoding="utf-8"))
        gp = os.path.join(V4, "gold", f"{cid}.json")
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
        if res["aggregate"] != "ACCEPT":
            for f in res["findings"][:3]:
                problems[cid].append(f"oracle {res['aggregate']}: {f['rule'].split('.')[-1]}/{f['code']} at {f['path']}: {f['message'][:80]}")
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
    print(f"verified {n} cases; {sum(1 for c in problems if problems[c])} with problems; {len(worst)} case pairs with 5-gram Jaccard > 0.08")
    if verbose:
        for cid in sorted(problems):
            for p in problems[cid]:
                print(f"  {cid[:8]}: {p}")
        for j, a, b in worst[:10]:
            print(f"  overlap {j:.3f}: {a[:8]} ~ {b[:8]}")
    return problems, worst


def case_src(case, sid):
    return next((e["text"] for e in case["candidate"]["evidence"] if e["sourceId"] == sid), "")


if __name__ == "__main__":
    problems, _ = main()
    sys.exit(1 if any(problems.values()) else 0)
