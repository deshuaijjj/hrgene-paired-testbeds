| 模型 | 量化 | 参数量 | digest | think | 其余解码参数 | Ollama |
|---|---|---|---|---|---|---|
| gpt-oss:20b | MXFP4 | 20.9B | `17052f91a42e` | low | temperature 0，seed 1，num_ctx 16384，num_predict 6000，每条件每例 1 次 | 0.33.0 |
| qwen3:8b | Q4_K_M | 8.2B | `500a1f067a9f` | false | temperature 0，seed 1，num_ctx 16384，num_predict 6000，每条件每例 1 次 | 0.33.0 |
| qwen3:30b-a3b | Q4_K_M | 30.5B | `ad815644918f` | false | temperature 0，seed 1，num_ctx 16384，num_predict 6000，每条件每例 1 次 | 0.33.0 |

注：digest 为 Ollama 报告的模型 digest 前 12 位十六进制；各模型在 C0、C1、C2、C5 运行（及 gpt-oss:20b 的 C4 再生成）中的 digest、模型名与 seed 逐输出一致（例如 gpt-oss:20b C2 144/144 份输出，不一致 0 处）。think 为 Ollama 的推理开关：gpt-oss:20b 为 `low`，两个 qwen 模型为 `false`，这是模型间的配置差异。解码参数由请求 options 给定，覆盖模型文件的默认采样参数（gpt-oss:20b 默认 `temperature 1`；qwen 默认 `repeat_penalty 1 stop "<|im_start|>" stop "<|im_end|>" temperature 0.6 top_k 20 top_p 0.95`）。硬件：Mac Studio（Apple M2 Max，32 GB），Ollama 0.33.0。
