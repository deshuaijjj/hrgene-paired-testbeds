| 条件 | 请求相对 C0 的差异 | prompt 中位词数 | 规则部分中位词数 | 是否含校验头部句 | 与 C0 逐字节相同的输出数（仅 C5） |
|---|---|---|---|---|---|
| C0 | 基线：JSON 模式（format = "json"），prompt 含完整的输出契约描述，不含规则 | 958.5 | — | 否（0/144） | — |
| C1 | system 消息加入散文规则部分（`render_prose` 渲染本例激活的规则）；144/144 条请求等于 C0 + 该渲染 | 1470.5 | 494 | 否（0/144） | — |
| C2 | system 消息加入契约规则部分（`render_contract`：must / mustNot / route，另加 applies、checkedBy、onViolation、severity 与顶层 rulesetDigest）及校验头部句；144/144 条请求等于 C0 + 该渲染 | 1760.5 | 762 | 是（144/144） | — |
| C3 | 无新请求：C2 产物加上离线校验报告 | — | — | — | — |
| C4 | 无新生成请求：对冻结 C2 产物校验、一次修复、至多一次再生成（再生成请求数 1、0、0，按 gpt-oss:20b、qwen3:8b、qwen3:30b-a3b） | — | — | — | — |
| C5 | 与 C0 只差 format 字段：值为产物 JSON Schema（`schema/paired-review-bundle.v2.schema.json`，约束解码）；另两个不同的键为条件标签与请求 id | 958.5 | — | 否（0/144） | gpt-oss:20b 0/144；qwen3:8b 119/144；qwen3:30b-a3b 132/144 |

注：词数 = system 与 user 消息按空白切分的词数，取每条件 144 条请求的中位数；规则部分词数 = 同一案例 C1 / C2 的 system 消息词数减去 C0 的。逐案配对的 C2 − C1 词数中位数为 268（范围 240–299）。校验头部句 = C2 规则部分的首句：“Review rule contracts. Each block is a rule that an independent validator will check on your output; a violated rule with onViolation=block sends the output back for repair.”，统计同时含「an independent validator will check」与「sends the output back for repair」的请求；C2 生成时并不执行校验，也不送回修复（C3 只是事后的离线校验）。C0 与 C5 的 144/144 条请求逐键比较，只有 condition, format, request_id 三个顶层键不同。逐字节相同 = 同一案例 C0 与 C5 输出的 content 字符串在 UTF-8 下完全相同（分母 144）。四个生成条件的请求文件对三个模型逐字节相同（requests sha256 前 12 位：C0 `413ef9c36e00`；C1 `05a0f21f2d1a`；C2 `9b0c6e29f8b3`；C5 `45cf0296e6a8`）。
