#!/usr/bin/env python3
"""Table 1: one rule contract (ownership_scope) as stored, and how the same rule reaches the model in C1 (prose) and
C2 (contract block) for one real benchmark case.

Case selection rule (fixed before looking at any output): the first caseId, in sorted order, of the ownership family
(`ownership_role_scope_inflation`) with controlStatus `positive_risk`. The rendering is produced by the frozen
runtime (`rules.py` render_prose / render_contract) and checked to be a verbatim substring of the request actually sent
(`benchmark/v4/requests/C1.jsonl`, `C2.jsonl`).

    python3 tab1_contract.py      # writes tab1_contract.md next to this script
"""
import glob
import json
import os
import sys
import textwrap

sys.dont_write_bytecode = True   # no __pycache__ next to the analysis scripts
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
sys.path.insert(0, HERE)
from hrgene.rules import RuleSet  # noqa: E402
from setup_facts import extract_block, static_codes  # noqa: E402

BENCH = os.path.join(ROOT, "benchmark", "v4")
RULE_ID = "hrgene.ownership_scope"
FAMILY = "ownership_role_scope_inflation"
GOLD_NOTE = ("added by this script, not part of the rule file: requiresGold checks are never run by the validator "
             "(detectors.py never reads gold) and are excluded from the C2 prompt's checkedBy list (rules.py); the "
             "corresponding gold-anchored test is computed only at scoring time (scoring.py, trap signature on the supported side)")


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def compact(obj, depth=0, max_depth=2):
    """Keys up to `max_depth` on their own lines; anything deeper inline."""
    pad = " " * depth
    if isinstance(obj, dict) and depth < max_depth:
        items = [f'{pad} {json.dumps(k, ensure_ascii=False)}: {compact(v, depth + 1, max_depth).lstrip()}' for k, v in obj.items()]
        return pad + "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(obj, list) and depth < max_depth and any(isinstance(x, dict) for x in obj):
        items = [pad + " " + json.dumps(x, ensure_ascii=False, separators=(", ", ": ")) for x in obj]
        return pad + "[\n" + ",\n".join(items) + "\n" + pad + "]"
    return pad + json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))


def words(s):
    return len(s.split())


def main():
    rs = RuleSet(os.path.join(ROOT, "rules", "canonical-rules.v2.json"))
    rule = rs.by_id[RULE_ID]
    excerpt = {"ruleId": rule["ruleId"], "title": rule["title"], "version": rule["version"], "kind": rule["kind"], "severity": rule["severity"], "activation": rule["activation"],
               "obligation": rule["obligation"], "validationTarget": json.loads(json.dumps(rule["validationTarget"])),
               "handling": rule["handling"], "provenance": rule["provenance"]}
    for c in excerpt["validationTarget"]["checks"]:
        if c.get("requiresGold"):
            c["_annotation"] = "scoring only"
    gold_ids = [c["id"] for c in rule["validationTarget"]["checks"] if c.get("requiresGold")]
    # --- case selection
    chosen = None
    for f in sorted(glob.glob(os.path.join(BENCH, "gold", "*.json"))):
        g = load_json(f)
        if g["family"] == FAMILY and g["controlStatus"] == "positive_risk":
            chosen = g["caseId"]
            break
    case = load_json(os.path.join(BENCH, "cases", chosen + ".json"))
    act = rs.activation(case)[RULE_ID]
    assert act["active"], "selected case does not activate the rule"
    prose_all = rs.render_prose(case)
    contract_all = rs.render_contract(case)
    prose_lines = prose_all.split("\n")
    prose_header = prose_lines[0]
    prose_line = next(ln for ln in prose_lines[1:] if ln.split(". ", 1)[1] == rule["obligation"]["prose"])
    contract_header = contract_all.split("\n", 1)[0]
    block = extract_block(contract_all, RULE_ID)
    b0 = contract_all.index(block)
    block_display = textwrap.dedent(contract_all[contract_all.rfind("\n", 0, b0) + 1:b0 + len(block)])
    sent = {}
    for cond in ("C1", "C2"):
        with open(os.path.join(BENCH, "requests", f"{cond}.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r["case_id"] == chosen:
                    sent[cond] = r["messages"][0]["content"]
    checks = {"C1 rules section is a substring of the sent C1 system message": prose_all in sent["C1"],
              "C1 rule line is in the sent message": prose_line in sent["C1"],
              "C2 contract section is a substring of the sent C2 system message": contract_all in sent["C2"],
              "C2 rule block is in the sent message": block in sent["C2"]}
    assert all(checks.values()), checks
    codes, _, _ = static_codes()
    rule_codes = sorted(c for c, e in codes.items() if RULE_ID in e["rules"])
    declared = [c["id"] for c in rule["validationTarget"]["checks"] if not c.get("requiresGold")]
    o = rule["obligation"]
    duty = sum(words(s) for s in o["mustDo"]) + sum(words(s) for s in o["mustNot"]) + words(o["route"])
    n_active = len(rs.active_rules(case))

    L = []
    A = L.append
    A("# Table 1 — one rule contract and its two renderings")
    A("")
    A("Definitions. The excerpt is the `hrgene.ownership_scope` entry of `rules/canonical-rules.v2.json` with its six contract "
      "fields (activation, obligation, validationTarget, handling, severity, provenance) copied verbatim; the only addition is the "
      "`_annotation` key on `requiresGold` checks. The renderings are the output of the frozen `RuleSet.render_prose` (C1) and "
      "`RuleSet.render_contract` (C2) for one case chosen by a fixed rule (first sorted caseId of the ownership family with "
      "controlStatus positive_risk); both are verified to be verbatim substrings of the request that was sent. Word counts are "
      "whitespace-split tokens: *prose* = `obligation.prose`; *duty text* = `mustDo` + `mustNot` + `route`; *block* = the whole "
      "rendered C2 block for this rule, including `severity`, `applies`, `checkedBy` and `onViolation`. *Implemented codes* are "
      "the code strings the validator can emit for this rule (static parse of `detectors.py`, see `setup_facts.md`).")
    A("")
    A("## Contract excerpt (rule file)")
    A("")
    A("```json")
    A(compact(excerpt))
    A("```")
    A("")
    A(f"`_annotation`: {GOLD_NOTE}. Gold-only check(s) of this rule: {', '.join('`' + g + '`' for g in gold_ids)}.")
    A("")
    A(f"Declared validator check(s): {', '.join('`' + c + '`' for c in declared)}. Implemented codes for this rule: "
      f"{', '.join('`' + c + '`' for c in rule_codes)} (codes not in the declared list are undeclared implementation checks).")
    A("")
    A(f"## Rendering for case `{chosen}` ({n_active} of {len(rs.rules)} rules active; this rule active because `{act['why']}` fired)")
    A("")
    A("C1 (prose), header line and this rule's line as sent:")
    A("")
    A("```text")
    A(prose_header)
    A("…")
    A(prose_line)
    A("```")
    A("")
    A("C2 (contract block), header line and this rule's block as sent (inside `{\"rulesetDigest\": …, \"rules\": [ … ]}`):")
    A("")
    A("```text")
    A(contract_header)
    A("…")
    A(block_display)
    A("```")
    A("")
    A(f"Word counts for this rule: prose {words(o['prose'])}; duty text {duty}; rendered block {words(block)}.")
    A("")
    A("Verification: " + "; ".join(f"{k}: {v}" for k, v in checks.items()) + ".")
    A("")
    with open(os.path.join(HERE, "tab1_contract.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("case", chosen, "checks", all(checks.values()))


if __name__ == "__main__":
    main()
