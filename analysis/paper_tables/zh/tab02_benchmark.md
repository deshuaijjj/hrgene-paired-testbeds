| 族（英文名） | 风险 | 对照 | 锚定规则 |
|---|---|---|---|
| 决策族：排序、决策语言与受保护特征（decision_ranking_protected_human_review_boundary） | 12 | 12 | `human_review_boundary` |
| 所有权族：所有权与角色范围夸大（ownership_role_scope_inflation） | 12 | 12 | `ownership_scope` |
| 资历族：资历与资格不符（qualification_seniority_mismatch） | 12 | 12 | `qualification_boundary` |
| 部署族：无依据的生产部署经验（unsupported_jd_technical_deployment） | 12 | 12 | `deployment_boundary` |
| 主观族：无依据前提、追问与主观理由（unsupported_premise_followup_subjective_rationale） | 12 | 12 | `subjective_claim_boundary` |
| 量化族：无依据的量化与因果（unsupported_quantification_causality） | 12 | 12 | `unsupported_quantification` |
| 合计 | 72 | 72 | 6 条规则各锚定一族 |

注：共 144 例（72 风险 + 72 匹配干净对照，6 个压力族）。每例 5 条岗位需求、3 条金标命题、8 个证据来源。风险案例的陷阱由只出现在诱饵来源中的签名短语锚定（金标 `trap.signatures`），另有陷阱需求的金标状态；匹配干净对照没有陷阱，其金标给出有效主张签名（`validClaimSignatures`），用于度量有效主张的保留。带 `anywhereSignatures`（受保护特征短语，产物任一文本字段出现即计陷阱失败）的案例 12 例，全部为风险案例（决策族 12 例）。锚定规则 = 金标 `trap.rule`，即该族陷阱所对应的规则契约。基准与金标于 2026-09-06 冻结（cases+gold 摘要 `f11ee4c8…`，规则文件摘要 `2f0e01d2…`）。
