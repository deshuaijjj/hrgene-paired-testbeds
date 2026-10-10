| 族 | gpt-oss:20b | qwen3:8b | qwen3:30b-a3b |
|---|---|---|---|
| 决策族（decision_ranking_protected_human_review_boundary） | 5 → 0（清除 5） | 9 → 2（清除 7） | 12 → 0（清除 12） |
| 所有权族（ownership_role_scope_inflation） | 4 → 2（清除 2） | 11 → 4（清除 7） | 1 → 1（清除 0） |
| 资历族（qualification_seniority_mismatch） | 5 → 1（清除 4） | 6 → 4（清除 2） | 1 → 0（清除 1） |
| 部署族（unsupported_jd_technical_deployment） | 1 → 0（清除 1） | 7 → 0（清除 7） | 0 → 0（清除 0） |
| 主观族（unsupported_premise_followup_subjective_rationale） | 1 → 1（清除 0） | 1 → 1（清除 0） | 1 → 1（清除 0） |
| 量化族（unsupported_quantification_causality） | 3 → 0（清除 3） | 0 → 0（清除 0） | 2 → 1（清除 1） |
| 其余五族合计 | 14 → 4（清除 10） | 25 → 9（清除 16） | 5 → 3（清除 2） |
| 全部六族 | 19 → 4（清除 15） | 34 → 11（清除 23） | 17 → 3（清除 14） |

注：每格为该族风险案例在 C2 与 C4 下的陷阱失败数（两条件都可解析的配对案例，每族 12 例），括号内为 C2→C4 清除数；新增为 0 时不写。分族只描述、不作检验。决策族的陷阱可由 `anywhereSignatures`、决策语言或决策边界字段触发，落点可以在支持侧以外。决策族占全部清除的比例：gpt-oss:20b 5/15；qwen3:8b 7/23；qwen3:30b-a3b 12/14；其中清除动作含删除 interviewSignalRisks 条目的决策族案例：gpt-oss:20b 5/5；qwen3:8b 6/7；qwen3:30b-a3b 12/12。
