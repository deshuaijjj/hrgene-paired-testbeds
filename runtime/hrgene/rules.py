"""Rule registry: load canonical-rules.v2.json, evaluate activation (tau), render obligations (d)."""
import hashlib
import json
import os

from .lexicons import Lexicons, DEFAULT_RULES_DIR
from . import textmatch as tm

CONDITIONS = ("C0", "C1", "C2", "C3", "C4", "C5")


class RuleSet:
    def __init__(self, path=None, lexicons=None):
        path = path or os.path.join(DEFAULT_RULES_DIR, "canonical-rules.v2.json")
        with open(path, "rb") as f:
            raw = f.read()
        self.path = path
        self.digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        self.raw = json.loads(raw.decode("utf-8"))
        self.rules = sorted(self.raw["rules"], key=lambda r: r["order"])
        self.by_id = {r["ruleId"]: r for r in self.rules}
        self.lex = lexicons or Lexicons(os.path.join(os.path.dirname(path), self.raw.get("lexicons", "lexicons.v2.json")))

    # ---- activation (tau) -------------------------------------------------
    def _scope_text(self, case, scope):
        rc = case.get("roleContext", {})
        if scope == "jobDescription":
            return [rc.get("jobDescription", "")]
        if scope == "requirements":
            return [r.get("text", "") for r in rc.get("requirements", [])]
        if scope == "evidence":
            return [e.get("text", "") for e in case.get("candidate", {}).get("evidence", [])]
        return []

    def _predicate(self, name, texts, case):
        if name == "numeric":
            return any(tm.numbers_in(t, self.lex) for t in texts)
        if name == "note_source":
            return any(e.get("sourceType") == "note" for e in case.get("candidate", {}).get("evidence", []))
        if name in self.lex.families:
            return any(tm.family_hits(t, self.lex, name) for t in texts)
        raise ValueError(f"unknown activation predicate {name}")

    def activation(self, case):
        """{ruleId: {"active": bool, "why": str}}"""
        out = {}
        for r in self.rules:
            act = r["activation"]
            if act["type"] == "always":
                out[r["ruleId"]] = {"active": True, "why": "always"}
                continue
            texts = []
            for sc in act.get("scopes", []):
                texts.extend(self._scope_text(case, sc))
            fired = [p for p in act.get("predicates", []) if self._predicate(p, texts, case)]
            out[r["ruleId"]] = {"active": bool(fired), "why": ",".join(fired) if fired else "no predicate fired"}
        return out

    def active_rules(self, case):
        a = self.activation(case)
        return [r for r in self.rules if a[r["ruleId"]]["active"]]

    # ---- obligation rendering (d) ------------------------------------------
    def render_prose(self, case, only_active=True):
        """C1: the obligations as plain numbered prose (same content as C2, no structure)."""
        rules = self.active_rules(case) if only_active else self.rules
        lines = ["Review rules. Follow every rule below when writing the optimized CV and the evidence packet."]
        for i, r in enumerate(rules, 1):
            lines.append(f"{i}. {r['obligation']['prose']}")
        return "\n".join(lines)

    def render_contract(self, case, only_active=True):
        """C2/C4: the obligations as structured contract blocks (JSON)."""
        rules = self.active_rules(case) if only_active else self.rules
        blocks = []
        for r in rules:
            o = r["obligation"]
            blocks.append({
                "rule": r["ruleId"],
                "severity": r["severity"],
                "applies": "always" if r["activation"]["type"] == "always" else "when the materials involve " + ", ".join(r["activation"].get("predicates", [])),
                "must": o["mustDo"],
                "mustNot": o["mustNot"],
                "route": o["route"],
                "checkedBy": [c["id"] for c in r["validationTarget"]["checks"] if not c.get("requiresGold")],
                "onViolation": r["handling"]["onFail"],
            })
        header = ("Review rule contracts. Each block is a rule that an independent validator will check on your output; "
                  "a violated rule with onViolation=block sends the output back for repair.")
        return header + "\n" + json.dumps({"rulesetDigest": self.digest, "rules": blocks}, ensure_ascii=False, indent=1)

    def summary_table(self):
        return [{"order": r["order"], "ruleId": r["ruleId"], "kind": r["kind"], "severity": r["severity"],
                 "activation": r["activation"]["type"], "onFail": r["handling"]["onFail"],
                 "checks": [c["id"] for c in r["validationTarget"]["checks"]]} for r in self.rules]
