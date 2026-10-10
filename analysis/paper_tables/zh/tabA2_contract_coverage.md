| 项目 | 数量 | 明细 |
|---|---|---|
| 声明的校验器检查（非 requiresGold） | 23 | 各规则 `validationTarget.checks` 中不带 requiresGold 的 id |
| 仅评分的金标检查（requiresGold） | 6 | 校验器不运行，只在评分时计算 |
| 实现的 code | 32 | 静态解析 detectors.py / validator.py 或在三个模型的校验报告中观测到 |
| 声明但无同名实现 | 3 | `no_subjective_terms_on_supported_side`（改名实现为 `subjective_term_on_supported_side`）；`production_term_licensed`（改名实现为 `nonproduction_rewritten_as_production`、`production_not_stated_by_sources`）；`subjective_sources_not_cited_as_support`（改名实现为 `subjective_source_cited_as_support`） |
| 实现但未声明：改名对应 | 6 | `nonproduction_rewritten_as_production` → `production_term_licensed`；`participation_upgraded_to_ownership` → `ownership_family_licensed`；`production_not_stated_by_sources` → `production_term_licensed`；`subjective_source_cited_as_support` → `subjective_sources_not_cited_as_support`；`subjective_term_on_supported_side` → `no_subjective_terms_on_supported_side`；`years_exceed_sources` → `qualification_family_licensed` |
| 实现但未声明：无对应 | 6 | `evidence_text_not_verbatim`、`gap_requirement_id_valid`、`requirement_ownership_unlicensed`、`requirement_production_unlicensed`、`requirement_qualification_unlicensed`、`requirement_years_unlicensed` |
| 发出严重度与契约 JSON 不同 | 3 | `causal_term_licensed`（发出 noncritical，契约 critical）；`evidence_text_not_verbatim`（发出 noncritical，契约 critical）；`witness_in_source`（发出 noncritical，契约 critical） |
| 严格反事实：被清除案例中依赖未声明检查 | gpt-oss:20b 7/15；qwen3:8b 12/23；qwen3:30b-a3b 2/14 | gpt-oss:20b: 10897267, 1ede8320, 224edb6d, 77e480fa, a582153d, c24d277e, c9eaf71c；qwen3:8b: 1ede8320, 3c94aef2, 5699692c, 5d769a54, 6193c2b5, 6fef8cc7, 77e480fa, 859049ac, 90eba559, 996edb13, ad32e172, b4fc09ab；qwen3:30b-a3b: 859049ac, ac25cb4a |
| 宽松反事实（改名对应视为已声明） | gpt-oss:20b 0/15；qwen3:8b 3/23；qwen3:30b-a3b 0/14 | gpt-oss:20b: none；qwen3:8b: 5699692c, 6fef8cc7, ad32e172；qwen3:30b-a3b: none |

注：按 code 名称精确匹配契约声明与实现。改名对应是人工指定的对应关系（setup_facts.py 的 counterpartMap），即实现以不同名称覆盖了一个声明的检查。无对应的 6 个 code 中，四个需求级许可检查（`requirement_*_unlicensed`）是 2026-09-05 依据开发样板（C0 试点）迭代检测器时加入的（RECORDS.md）。被清除案例 = C2 落陷阱而 C4 未落的风险案例（分母即各模型的清除数）。严格反事实：只保留 code 属于声明集合的 finding，用冻结修复器对冻结 C2 产物重新修复，修复后仍落陷阱即记为依赖未声明检查；宽松反事实把改名对应视为已声明；两者都不模拟再生成（受限校验器下仍为 BLOCK、本应触发再生成的案例：严格 0/0/0，按三模型顺序）。校验器与检测器不读取契约文件的字段；二者的一致性由规则夹具与变异注入测试维护，而非由编译保证。
