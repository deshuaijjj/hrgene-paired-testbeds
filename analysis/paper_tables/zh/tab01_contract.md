| 字段 | 含义 | 本规则取值（简短） |
|---|---|---|
| ruleId | 规则标识；校验器按 ruleId 注册对应的手写检测器（共 9 个） | `hrgene.ownership_scope` |
| title / version / kind | 名称、版本与规则类型（描述性元数据） | Ownership scope / 2.0.0 / conditional_trigger |
| severity | 规则级严重度；渲染为 C2 契约块的 severity 字段；校验器发出的 finding 严重度由检测器代码写定，不读取本字段 | critical |
| activation | 激活条件；rules.py 据此判定该规则是否对本例渲染（C1、C2） | any_of；scopes jobDescription, requirements, evidence；predicates ownership |
| obligation.prose | C1 散文规则的全文 | 51 词：“Do not expand the candidate's ownership, leadership, decisio…” |
| obligation.mustDo | C2 契约块的 must 条目 | 2 条：“Use the same level of ownership wording as the cited source.”等 |
| obligation.mustNot | C2 契约块的 mustNot 条目 | 1 条：“Upgrade participation into leadership, ownership, management…” |
| obligation.route | C2 契约块的 route：证据不足时的路由去向 | “If a job requirement asks for ownership that the sources do…” |
| validationTarget.reads | 声明检查读取的产物字段 | 3 条路径（optimizedCv、supportedClaims、需求证据文本） |
| validationTarget.checks | 声明的检查集合；非 requiresGold 的 id 渲染为 C2 的 checkedBy；requiresGold 的检查只在评分时计算 | `ownership_family_licensed`；`gold_trap_signature_absent`（requiresGold，仅评分） |
| validationTarget.witness | 违规时 finding 应记录的证据 | “the ownership term, its family, the claim path and the cited…” |
| handling.onFail | 违规处理级别；渲染为 C2 契约块的 onViolation | block |
| handling.repair | 声明的修复动作；运行时不读取（修复器按规则手写） | `route_claim_to_unsupported`（附 reason 与 requiredFollowUp） |
| handling.maxRegenerations | 声明的再生成上限；运行时不读取（流水线写定至多一次再生成） | 1 |
| provenance | 规则来源说明；运行时不读取 | 3 项：source / v1 / changedInV2 |

注：契约取自 `rules/canonical-rules.v2.json` 的 `hrgene.ownership_scope` 条目（表后代码块为该条目原文；tab1_contract.py 加注的 `_annotation` 键已去掉）。词数按空白切分：散文义务 51 词；mustDo + mustNot + route 66 词；本规则渲染后的整个 C2 块 91 词（含 severity、applies、checkedBy、onViolation；渲染实例为案例 `0bdc120c`）。「运行时不读取」指 `runtime/hrgene/*.py` 中没有读取该键的代码（setup_facts.py 静态检查：maxRegenerations, provenance, repair）；契约文件只被 rules.py 用于激活判定与 prompt 渲染，detectors.py 与 validator.py 不读取契约字段。本规则声明的校验器检查为 `ownership_family_licensed`，校验器实际可发出的 code 为 `ownership_family_licensed`、`participation_upgraded_to_ownership`、`requirement_ownership_unlicensed`（未声明者为实现侧追加的检查，全体规则的差异见表 A2）。

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
  "checks": [{"id": "ownership_family_licensed", "description": "each ownership family term (LEAD, OWN, MANAGE, INDEPENDENT, APPROVE, END_TO_END) used on the supported side occurs, as the same family, in at least one cited source"}, {"id": "gold_trap_signature_absent", "requiresGold": true}],
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
