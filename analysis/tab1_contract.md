# Table 1 — one rule contract and its two renderings

Definitions. The excerpt is the `hrgene.ownership_scope` entry of `rules/canonical-rules.v2.json` with its six contract fields (activation, obligation, validationTarget, handling, severity, provenance) copied verbatim; the only addition is the `_annotation` key on `requiresGold` checks. The renderings are the output of the frozen `RuleSet.render_prose` (C1) and `RuleSet.render_contract` (C2) for one case chosen by a fixed rule (first sorted caseId of the ownership family with controlStatus positive_risk); both are verified to be verbatim substrings of the request that was sent. Word counts are whitespace-split tokens: *prose* = `obligation.prose`; *duty text* = `mustDo` + `mustNot` + `route`; *block* = the whole rendered C2 block for this rule, including `severity`, `applies`, `checkedBy` and `onViolation`. *Implemented codes* are the code strings the validator can emit for this rule (static parse of `detectors.py`, see `setup_facts.md`).

## Contract excerpt (rule file)

```json
{
 "ruleId": "hrgene.ownership_scope",
 "title": "Ownership scope",
 "version": "2.0.0",
 "kind": "conditional_trigger",
 "severity": "critical",
 "activation": {
  "type": "any_of",
  "scopes": ["jobDescription", "requirements", "evidence"],
  "predicates": ["ownership"]
 },
 "obligation": {
  "prose": "Do not expand the candidate's ownership, leadership, decision authority, team scope, or personal responsibility beyond what the cited source states. 'Participated in', 'assisted', 'supported', or 'contributed to' must not become 'led', 'owned', 'managed', 'independently delivered', or 'end-to-end'. Preserve the collaboration, approval, and responsibility boundaries stated in the sources in both artifacts.",
  "mustDo": ["Use the same level of ownership wording as the cited source.", "Keep stated approval and hand-off boundaries (who confirmed, who approved) in the claim."],
  "mustNot": ["Upgrade participation into leadership, ownership, management, sole responsibility, approval authority or end-to-end delivery."],
  "route": "If a job requirement asks for ownership that the sources do not establish, mark the requirement partial_evidence or insufficient_evidence and ask what the candidate personally decided, controlled or approved."
 },
 "validationTarget": {
  "reads": ["optimizedCv.*[].text", "hiringEvidencePacket.supportedClaims[].claim", "hiringEvidencePacket.requirementEvidenceMap[].evidence[].text"],
  "checks": [{"id": "ownership_family_licensed", "description": "each ownership family term (LEAD, OWN, MANAGE, INDEPENDENT, APPROVE, END_TO_END) used on the supported side occurs, as the same family, in at least one cited source"}, {"id": "gold_trap_signature_absent", "requiresGold": true, "_annotation": "scoring only"}],
  "witness": "the ownership term, its family, the claim path and the cited sourceIds"
 },
 "handling": {
  "onFail": "block",
  "repair": [{"action": "route_claim_to_unsupported", "reason": "The cited sources do not establish this level of ownership or authority.", "requiredFollowUp": "Ask which decisions, resources and approvals the candidate personally controlled."}],
  "maxRegenerations": 1
 },
 "provenance": {
  "source": "HR review rule: scope inflation of 'participated' into 'led'",
  "v1": "hrgene.ownership_scope.v1 / preserve_ownership_scope",
  "changedInV2": "family-level term licensing makes the detector executable"
 }
}
```

`_annotation`: added by this script, not part of the rule file: requiresGold checks are never run by the validator (detectors.py never reads gold) and are excluded from the C2 prompt's checkedBy list (rules.py); the corresponding gold-anchored test is computed only at scoring time (scoring.py, trap signature on the supported side). Gold-only check(s) of this rule: `gold_trap_signature_absent`.

Declared validator check(s): `ownership_family_licensed`. Implemented codes for this rule: `ownership_family_licensed`, `participation_upgraded_to_ownership`, `requirement_ownership_unlicensed` (codes not in the declared list are undeclared implementation checks).

## Rendering for case `0bdc120c-2fdd-43ad-a217-fdd50f2cfdba` (9 of 9 rules active; this rule active because `ownership` fired)

C1 (prose), header line and this rule's line as sent:

```text
Review rules. Follow every rule below when writing the optimized CV and the evidence packet.
…
3. Do not expand the candidate's ownership, leadership, decision authority, team scope, or personal responsibility beyond what the cited source states. 'Participated in', 'assisted', 'supported', or 'contributed to' must not become 'led', 'owned', 'managed', 'independently delivered', or 'end-to-end'. Preserve the collaboration, approval, and responsibility boundaries stated in the sources in both artifacts.
```

C2 (contract block), header line and this rule's block as sent (inside `{"rulesetDigest": …, "rules": [ … ]}`):

```text
Review rule contracts. Each block is a rule that an independent validator will check on your output; a violated rule with onViolation=block sends the output back for repair.
…
{
 "rule": "hrgene.ownership_scope",
 "severity": "critical",
 "applies": "when the materials involve ownership",
 "must": [
  "Use the same level of ownership wording as the cited source.",
  "Keep stated approval and hand-off boundaries (who confirmed, who approved) in the claim."
 ],
 "mustNot": [
  "Upgrade participation into leadership, ownership, management, sole responsibility, approval authority or end-to-end delivery."
 ],
 "route": "If a job requirement asks for ownership that the sources do not establish, mark the requirement partial_evidence or insufficient_evidence and ask what the candidate personally decided, controlled or approved.",
 "checkedBy": [
  "ownership_family_licensed"
 ],
 "onViolation": "block"
}
```

Word counts for this rule: prose 51; duty text 66; rendered block 91.

Verification: C1 rules section is a substring of the sent C1 system message: True; C1 rule line is in the sent message: True; C2 contract section is a substring of the sent C2 system message: True; C2 rule block is in the sent message: True.

