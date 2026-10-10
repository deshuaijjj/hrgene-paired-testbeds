#!/usr/bin/env python3
"""Build benchmark/v5/build/skeleton.json: the de-confounded testbed design (DECONFOUND_PLAN.md).

Same cell structure as v4 (6 stress families x {positive_risk, matched_clean_control} x 4 role families x 3 industries
= 144 cases; 5 resume entries, 1 work sample, 2 notes per case), with fresh identifiers and two new design fields:

  risk cases     baitLocation in {note, resume, work_sample} and baitSlot (1-based source index S1..S8): exactly one
                 bait source per case. Per family the 12 risk cases are split 4/4/4 by a Latin-square rule over
                 (role family, industry); the decision family has no natural work-sample bait and is split 6/6
                 between note and resume.
  controls       noteOnlyValid: in 6 of 12 controls per family at least one gold valid-claim signature must occur
                 only in a note.

Every non-bait note in a risk case carries factual evidence (enforced by the authoring brief, checked by review)."""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261009
FAMILIES = [
    "decision_ranking_protected_human_review_boundary",
    "ownership_role_scope_inflation",
    "qualification_seniority_mismatch",
    "unsupported_jd_technical_deployment",
    "unsupported_premise_followup_subjective_rationale",
    "unsupported_quantification_causality",
]
ROLES = ["business_and_operations", "data_and_ai", "product_and_project_management", "software_engineering"]
INDUSTRIES = ["financial_services", "industrial_and_consumer_services", "technology_and_software"]
SOURCE_TYPES = ["resume"] * 5 + ["work_sample"] + ["note"] * 2
LOCATIONS = ["note", "resume", "work_sample"]
DECISION = FAMILIES[0]


def v4_ids():
    p = os.path.join(HERE, "..", "..", "v4", "build", "skeleton.json")
    ids = set()
    for c in json.load(open(p, encoding="utf-8"))["cases"]:
        ids |= {c["caseId"], c["candidateId"], c["jobDescriptionSourceId"], *c["requirementIds"], *c["sourceIds"], *c["propositionIds"]}
    return ids


def main():
    rnd = random.Random(SEED)
    taken = v4_ids()

    def hexid(prefix, n):
        while True:
            x = prefix + "".join(rnd.choice("0123456789abcdef") for _ in range(n))
            if x not in taken:
                taken.add(x)
                return x

    def uuid():
        h = "".join(rnd.choice("0123456789abcdef") for _ in range(32))
        x = f"{h[:8]}-{h[8:12]}-4{h[13:16]}-{'89ab'[int(h[16], 16) % 4]}{h[17:20]}-{h[20:32]}"
        if x in taken:
            return uuid()
        taken.add(x)
        return x

    out = []
    for fam in FAMILIES:
        for r, role in enumerate(ROLES):
            for i, ind in enumerate(INDUSTRIES):
                pair = hexid("pair_", 8)
                for status in ("positive_risk", "matched_clean_control"):
                    c = {
                        "caseId": uuid(), "pairId": pair, "family": fam, "controlStatus": status,
                        "roleFamily": role, "industry": ind,
                        "candidateId": hexid("cand_", 16), "jobDescriptionSourceId": hexid("jd_", 16),
                        "requirementIds": [hexid("req_", 12) for _ in range(5)],
                        "sourceIds": [hexid("src_", 12) for _ in range(8)],
                        "sourceTypes": list(SOURCE_TYPES),
                        "propositionIds": [hexid("prop_", 12) for _ in range(3)],
                    }
                    if status == "positive_risk":
                        if fam == DECISION:
                            loc = "note" if (r + i) % 2 == 0 else "resume"
                        else:
                            loc = LOCATIONS[(r + i) % 3]
                        slot = {"note": rnd.choice([7, 8]), "resume": rnd.randint(1, 5), "work_sample": 6}[loc]
                        c["baitLocation"], c["baitSlot"] = loc, slot
                    else:
                        c["noteOnlyValid"] = (r + i) % 2 == 1
                    out.append(c)
    out.sort(key=lambda x: (x["family"], x["controlStatus"], x["roleFamily"], x["industry"]))
    json.dump({"schemaVersion": "jam.hrgene_v5_skeleton.v1", "seed": SEED, "count": len(out), "cases": out},
              open(os.path.join(HERE, "skeleton.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    import collections
    loc = collections.Counter((c["family"][:12], c.get("baitLocation")) for c in out if c["controlStatus"] == "positive_risk")
    print(f"{len(out)} cases")
    for k in sorted(loc):
        print(" ", k, loc[k])
    print("  noteOnlyValid controls:", sum(1 for c in out if c.get("noteOnlyValid")))


if __name__ == "__main__":
    main()
