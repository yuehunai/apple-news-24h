# 固定输入回放与同期比较

`replay_compare.py` 是维护用比较工具，不是产品调用入口。只用标准库，调用现有生产函数并记录行为，每棵代码树启动独立进程，固定 `PYTHONHASHSEED=0`；保留生产默认预算、并发和重试，使用 24 小时窗口及 `Asia/Singapore`。

## 使用

将以下路径替换为完整基线/候选代码树、已冻结证据目录及仓库外的新输出目录；`--at` 使用证据对应的带时区时间：

```sh
python3 candidate/tests/replay_compare.py \
  --baseline baseline --candidate candidate \
  --evidence evidence/frozen-run --at "$REPLAY_AT" \
  --output runs/new-comparison
```

输出目录必须不存在或为空，且不能与证据目录重叠（包括符号链接别名）。省略 `--candidate` 只建立基线。按问题选择范围：

| `--scope` | 用途及限制 |
| --- | --- |
| `full`（默认） | 用保存的解码响应执行发现及后续流程；缺失请求证据即失败，不能替代联网验证。 |
| `saved-details` | 从证据目录 `latest.json` 的正文/deferred 来源中，按 URL 去重选取有正文缓存的候选；继续执行当前详情选择、提取、投影与事件装配。不复用旧事件结论，不能证明历史遗漏候选或来源发现覆盖。 |
| `live` | 两棵代码树在同一固定时间窗并发联网，工具为其分配独立缓存和输出。必须提供 `--candidate`，不接受 `--evidence` 或历史基线产物。 |

离线证据目录包含 `cache/*.json`（URL、状态和解码文本）；可用 `requests.json` 记录 URL 请求尝试及原始 sequence。运行前逐文件核验冻结清单，之后只读使用。工具记录已有 `sha256.json`、`manifest.json`、`requests.json` 的指纹，但不会替调用者核验缓存清单的每一项。旧 `latest.json` 在 `saved-details` 中只提供候选索引，不是期望答案。

离线回放封锁网络；未知 URL 或请求次数耗尽会失败。有请求历史时按每次 fetch 的重试预算消耗记录；没有历史时只承认每 URL 一次保存的成功，不虚构失败或重复成功。同 URL 多次成功需要逐次文本证据，当前工具会拒绝此类输入。解码文本回放不验证字节解码、真实网络恢复或端到端网络速度。

## 读结果

- `manifest.json`：时间、范围、参数、输入索引及代码指纹。
- `behavior.json`：发现/详情选择、提取及回退、原始时间和置信度、文章、事件分区、事实及公开 JSON。仅规范化运行缓存路径，以及 live 模式的脚手架输出路径；标题、数字、顺序、tier/category 和公开 ID 参与比较。
- `comparison.json`：各进程退出码、差异区块、来源证据引用校验。来源证据字段会单独验证并移出其余行为的相等比较：`articles[*].evidence`、事件文章的 `evidence`、`result.source_evidence` 及正文/deferred 来源的 `evidence_id`。因此 `equal: true` 不代表两侧原文证据逐字相同，须结合证据校验及问题相关来源审阅。
- `responses.json`：回放请求消耗与未消耗记录；live 模式说明真实传输取证范围。缺失回放证据会留下 `failure.json`；未完成行为输出时保留 `partial_trace.json`。
- `timing.json`：采集、文章处理、事件处理、输出的 wall/CPU，包含取证开销。加 `--postprocess-repeat 3` 可对同一份聚类前文章深拷贝，重复聚类和事件序列化，记录中位数及结果哈希；这不代表联网性能。

总入口非零退出既可能是行为差异，也可能是工作进程失败；先看 `comparison.json` 和对应日志，不能把缺失响应算作通过。相等只说明所选范围内记录一致，正确性仍需来源依据和回归测试。

## 复用基线与后处理诊断

离线比较可加 `--baseline-artifact <已有基线工作进程输出目录>` 和 `--baseline-behavior-sha256 <核验过的behavior.json指纹>`，并提供 `--candidate`。工具检查固定时间、范围和原 manifest 记录的输入索引指纹，只重跑候选；`--baseline` 仍传原代码树路径。

`article-preparation.json` 按聚类前文章顺序保存实际准备快照，未记录项为 `null`，不改变生产输出。普通 dataclass/JSON 还原会丢失这些私有准备数据；需要比较还原后性能时，可调用工具内 `restore_article_preparation_metadata`，它核对来源、URL、标题、摘要及有序事实后恢复快照，不匹配则正常重算，不能从 `event_kind` 猜建。此类性能报告需注明 sidecar 是否存在及实际恢复数量。
