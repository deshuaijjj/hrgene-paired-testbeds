"""Run the nine detectors and aggregate."""
import json
import os

from . import bundle as B
from .detectors import DETECTORS, CaseIndex, finding
from .rules import RuleSet
from .lexicons import DEFAULT_RULES_DIR

DEFAULT_SCHEMA = os.path.normpath(os.path.join(DEFAULT_RULES_DIR, "..", "schema", "paired-review-bundle.v2.schema.json"))


class Validator:
    def __init__(self, ruleset=None, schema_path=None):
        self.rs = ruleset or RuleSet()
        with open(schema_path or DEFAULT_SCHEMA, encoding="utf-8") as f:
            self.schema = json.load(f)

    def validate(self, case, bundle, raw_text=None):
        """Return {"findings": [...], "aggregate": ACCEPT|HUMAN_REVIEW|BLOCK, "activation": {...}, "perRule": {...}}"""
        activation = self.rs.activation(case)
        ctx = {"lex": self.rs.lex, "index": CaseIndex(case), "schema": self.schema, "ruleset": self.rs}
        findings = []
        if not isinstance(bundle, dict):
            findings.append(finding("hrgene.paired_review_bundle_completeness", "json_parsed", "critical", "$", "model output is not a JSON object", {"raw": (raw_text or "")[:200]}))
        else:
            lifted = B.lift_string_items(bundle)   # bare-string claims become sourceless claim objects for every rule but the schema check
            for rule_id, fn in DETECTORS:
                findings.extend(fn(case, bundle if rule_id == "hrgene.paired_review_bundle_completeness" else lifted, ctx))
        per_rule = {}
        for r in self.rs.rules:
            fs = [f for f in findings if f["rule"] == r["ruleId"]]
            per_rule[r["ruleId"]] = {
                "active": activation[r["ruleId"]]["active"],
                "fail": sum(1 for f in fs if f["status"] == "FAIL"),
                "unresolved": sum(1 for f in fs if f["status"] == "UNRESOLVED"),
                "value": "FAIL" if any(f["status"] == "FAIL" for f in fs) else ("UNRESOLVED" if fs else "PASS"),
            }
        crit = any(f["status"] == "FAIL" and f["severity"] == "critical" for f in findings)
        anyf = any(f["status"] in ("FAIL", "UNRESOLVED") for f in findings)
        aggregate = "BLOCK" if crit else ("HUMAN_REVIEW" if anyf else "ACCEPT")
        return {"rulesetDigest": self.rs.digest, "activation": activation, "findings": findings, "perRule": per_rule, "aggregate": aggregate}
