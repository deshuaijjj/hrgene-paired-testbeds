"""C3 / C4 post-processing over generated bundles.

C3: validate and attach the report (no repair).
C4: validate -> deterministic bounded repair -> re-validate; if the aggregate is still BLOCK, request ONE regeneration
    with the findings (the caller performs the model call), then validate -> repair -> re-validate the regenerated
    output and keep it if it is not worse. Every stage is recorded."""
import json

from .repair import Repairer
from .validator import Validator

ORDER = {"ACCEPT": 0, "HUMAN_REVIEW": 1, "BLOCK": 2}


def parse_output(text):
    """Parse a model output into a JSON object; tolerate code fences and leading/trailing prose."""
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(s[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def stage_c3(validator, case, raw_text):
    bundle = parse_output(raw_text)
    res = validator.validate(case, bundle, raw_text=raw_text if bundle is None else None)
    return {"parsed": bundle is not None, "validation": res, "aggregate": res["aggregate"]}


def stage_c4_repair(validator, case, raw_text):
    """First C4 stage: parse, validate, repair, re-validate. Returns a record with the repaired bundle and whether a
    regeneration is needed (aggregate still BLOCK, or the output could not be parsed)."""
    bundle = parse_output(raw_text)
    before = validator.validate(case, bundle, raw_text=raw_text if bundle is None else None)
    rec = {"parsed": bundle is not None, "before": before, "repairLog": [], "after": None, "bundle": None, "needsRegeneration": False}
    if bundle is None:
        rec["needsRegeneration"] = True
        return rec
    rep = Repairer(validator.rs, case)
    repaired, log = rep.repair(bundle, before["findings"])
    after = validator.validate(case, repaired)
    rec.update(repairLog=log, after=after, bundle=repaired, needsRegeneration=(after["aggregate"] == "BLOCK"))
    return rec


def stage_c4_finalize(validator, case, first, regen_raw_text=None):
    """Second C4 stage: if a regeneration was produced, parse/validate/repair it and keep the better of the two."""
    final = {"stages": ["repair"], "regenerated": False, "bundle": first["bundle"], "aggregate": first["after"]["aggregate"] if first["after"] else "BLOCK",
             "validation": first["after"], "repairLog": list(first["repairLog"]), "notRepairable": False}
    if regen_raw_text is None:
        final["notRepairable"] = final["aggregate"] == "BLOCK"
        return final
    second = stage_c4_repair(validator, case, regen_raw_text)
    final["stages"].append("regenerate+repair")
    final["regenerated"] = True
    cand_agg = second["after"]["aggregate"] if second["after"] else "BLOCK"
    if second["bundle"] is not None and ORDER[cand_agg] <= ORDER[final["aggregate"]]:
        final.update(bundle=second["bundle"], aggregate=cand_agg, validation=second["after"], repairLog=final["repairLog"] + second["repairLog"], kept="regenerated")
    else:
        final["kept"] = "first"
    final["notRepairable"] = final["aggregate"] == "BLOCK"
    return final


def repair_escalation(before, after):
    """'Repair non-escalation': True when the repair introduced no finding that was not present before (by rule+code+path)."""
    if not before or not after:
        return None
    b = {(f["rule"], f["code"]) for f in before["findings"] if f["status"] == "FAIL"}
    a = {(f["rule"], f["code"]) for f in after["findings"] if f["status"] == "FAIL"}
    return not (a - b)
