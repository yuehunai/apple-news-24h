# apple-news-24h

[English](README.md) | **简体中文**

一个 Codex skill 和独立 Python 抓取器，用于生成最近 24 小时 Apple 软硬件新闻简报。

抓取器从指定中英文科技媒体发现候选文章，在可取得详情时核验发布时间，将时间统一转换到 UTC 后判断窗口，并按报道的具体动作归并多源内容。它输出结构化证据和覆盖检查脚手架；skill 根据这些结果撰写中文双板块简报：`软件与系统` 和 `硬件与产品`。

## 状态

本项目仍处于实验阶段。新闻网站结构、RSS 可用性和页面时间字段都可能变化，过滤规则也需要持续维护。建议把输出视为结构化简报草稿，发布前仍进行人工审阅。

## 最新更新

### 2.0.0 - 2026-10-10

- 重构 `1.77.0` 流水线，分离共享模型、采集与证据工具、绑定来源的主张投影，统一事件配对与协调裁决，移除输出装配中相互竞争的分组和相关性判断。
- 改进按报道主体、具体动作和对象进行的跨语言归组，在混合文章及后续报道中保留版本、地区、阶段、方向和统计期间边界。
- 新增 `source_evidence`、带来源归属的事实出处和可见的未处理片段去向，通过每源事实准备和事件事实计划保留重要数字、枚举、条件及归因；无法取得全文时，为仅有发现摘要的来源增加明确复核标记。
- 改进简短报道、当前披露及 Apple 相关法律和公司动作的候选准入与来源发现，保留九个主来源、UTC 时间窗口校验和采集预算。
- 改进现有第一方功能、平台互通和 Apple 设备实测的相关性及栏目判断，防止回顾、教程、第三方推荐和竞品背景覆盖实际报道动作。
- 新增基于 POSIX 的缓存与输出资源互斥，保留受保护的启动清理；复用来源准备结果及有界正则编译缓存，在不减少来源和事实覆盖的前提下降低重复处理。
- 更新 skill 的结构化结果消费、针对性证据复核和分批成稿流程，保留有依据的事实及来源链接，去除无必要的句末审稿总结。
- 新增固定输入回放与同窗比较工具，离线测试由 1,529 项扩展至 2,317 项并通过；保持标准库运行、现有 CLI、双栏简报和 skill 仅显式调用。

## 它会做什么

- 收集 Apple 相关的软件、系统、服务、硬件、配件、健康、研究、法律和公司动作新闻。
- 优先使用 RSS/Atom，再按配置尝试来源页面和兜底发现。
- 尽可能进入文章详情页读取精确发布时间。
- 将文章时间统一转换到 UTC 后执行 24 小时窗口判断。
- 将多家媒体报道的同一实质事件归并成一条。
- 标注事件类型和相关性层级，保留宽抓取范围下的弱 Apple 关联候选，但避免它们污染最终简报。
- 抽取关键数字、列表、功能名、国家/地区、条款、资格条件、上线限制，以及有来源位置的非数值机制与条件，用于生成更完整的摘要。
- 支持 Markdown 和 JSON 输出。

## 架构

抓取器将采集、来源证据、事件判断和输出装配分开。一个来源可以支持多个独立动作；每个投影主张保留自己的局部证据，尚未分配的重要内容继续提供给复核流程。

- `skills/scripts/apple_news_24h.py` 是 CLI 与流程协调入口，准备每个来源的事实，并根据已经裁决的事件和事实计划装配 JSON 与 Markdown。
- `skills/scripts/apple_news_core/collection.py` 维护来源定义、HTTP/缓存工具、资源锁和候选准入辅助函数；`article_processing.py` 负责文章文本清洗与来源证据准备。
- `models.py` 定义共享数据。`event_identity.py` 将具体主体和动作绑定到本源证据；`article_projector.py` 拆出有证据支持的主张，并保留未分配的来源内容。
- `event_matcher.py` 提供统一配对裁决；`event_reconciler.py` 形成事件组，确定相关性、栏目与带来源归属的事实计划。输出装配消费这些结果，不再运行第二套分组或相关性规则。
- `tests/` 覆盖发现、时间解析、缓存管理、事件边界、事实归属与输出。固定输入回放和实时采集验证分别解决不同问题；已保存页面不能证明当前发现范围或网络健康。

## 它不会做什么

- 这不是 Apple 官方项目。
- 不提供投资、法律、医疗或购买建议。
- 当来源阻断请求、RSS 延迟或页面结构变化时，不保证完整覆盖。
- 不应用于转载完整文章或缓存的源网页内容。

## 作为 Codex Skill 安装

克隆仓库，并将其中的 `skills` 目录软链接到 Codex skills 目录：

```bash
git clone https://github.com/yuehunai/apple-news-24h apple-news-24h
mkdir -p "$CODEX_HOME/skills"
ln -s "$PWD/apple-news-24h/skills" "$CODEX_HOME/skills/apple-news-24h"
```

如果没有设置 `CODEX_HOME`，Codex 通常使用 `~/.codex`：

```bash
git clone https://github.com/yuehunai/apple-news-24h apple-news-24h
mkdir -p ~/.codex/skills
ln -s "$PWD/apple-news-24h/skills" ~/.codex/skills/apple-news-24h
```

也可以把本仓库地址交给 Codex，让 Codex 自动安装：

```text
https://github.com/yuehunai/apple-news-24h
```

安装后显式调用，或通过自动化直接调用：

```text
$apple-news-24h
```

该 skill 在 `skills/agents/openai.yaml` 中禁用了隐式触发，因此普通 Apple、科技或新闻对话不会自动调用它。

## CLI 使用

请在 macOS 或 Linux 上使用 Python 3.9 或更高版本运行抓取器。它只使用标准库；资源锁依赖 POSIX `fcntl`，目前不支持原生 Windows。CLI 输出简报所需的结构化材料，不会调用语言模型撰写最终中文段落。

Markdown 输出：

```bash
python3 skills/scripts/apple_news_24h.py --hours 24 --timezone auto --format markdown
```

JSON 输出：

```bash
python3 skills/scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json
```

JSON 会将进入简报的项目放在 `events` 中。第三方应用、竞品对比等未描述 Apple 直接动作的弱 Apple 关联候选，可能保留在 `deferred_events` 中供审查。事件对象可包含 `event_kind`、`relevance_tier`、`relevance_reason`、`regions` 和 `merge_warnings`。

JSON 还提供用于归属与覆盖核验的证据：

| 字段 | 用途 |
| --- | --- |
| `source_evidence` | 捕获的来源单元与发表证据，通过 `evidence_id` 引用。 |
| `fact_sources[].origins` | 事件事实的来源依据；可定位时包含具体单元区间。 |
| `evidence_dispositions` | 已投影或未处理的来源内容去向。 |
| `final_brief_queue` | 需要作出处置的事件候选和未处理片段。`capture_status: discovery-only` 标记未取得全文的来源，不会因此提升相关性。 |

必审标记要求作出判断，并不代表自动纳入简报。`required_final_brief_titles`、`final_brief_markdown` 及相邻的 `*.brief.md` 是覆盖检查脚手架，并非最终成稿。正文应依据有来源支持的摘要与事实，核对独立动作、重要限定及每条新闻对应的来源链接。

2.0.0 保持现有 CLI 和相关性层级，并向 JSON 增加证据字段。消费端应允许额外字段；归组规则修正可能改变事件成员、ID 和分类。

调试来源失败时启用 diagnostics：

```bash
python3 skills/scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json --include-diagnostics
```

常用参数：

- `--hours 24`：回看窗口。
- `--timezone auto`：自动检测系统时区；也可以传入 `America/Los_Angeles` 这类 IANA 时区。
- `--format markdown|json`：选择输出格式。
- `--cache-dir PATH`：保存当前运行成功抓取的 HTTP 响应用于检查。
- `--output PATH`：原子写入完整结果文件，并在 stdout 仅打印简短状态 JSON。
- `--include-diagnostics`：包含抓取失败、来源失败、已选详情页抓取失败、发现兜底计数和低置信时间解析提示。

默认缓存目录是 Python 平台临时目录下的 `apple-news-24h`。脚本每次启动时会清空该目录并写入 marker 文件和当前运行响应。旧缓存不能作为新闻时效判断的兜底来源。

共用缓存或输出资源的运行遇到锁冲突会立即失败。独立运行应使用不同的 `--cache-dir` 和 `--output` 路径，需保留的证据应放在受管缓存之外。

## 网络权限

抓取器需要实时网络访问 RSS、频道页和文章详情页。在沙盒化 agent 环境中，首次运行可能因 DNS 或网络权限被拦截。如果结果为空或异常稀疏，skill 会在取得所需网络批准后重跑同一命令，必要时再检查 diagnostics 或执行已记录的兜底流程。

网络权限不能阻止站点返回访问拦截或浏览器验证。标准库 HTTP 客户端不会执行验证页 JavaScript，因此部分来源可能只有发现摘要；应先核对捕获标记，再判断现有文本是否覆盖全文。

## 来源

主要来源包括 MacRumors、9to5Mac、AppleInsider、The Verge、Apple Newsroom、IT之家、爱范儿、快科技和 cnBeta。补充兜底来源包括新浪科技/财经、网易科技、36氪，以及必要时的其他主流中文科技页面。

来源 URL、默认时区、纳入规则、排除规则、事件归并规则和兜底策略见 `skills/references/news_policy.md`。

## 测试

运行离线测试：

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m unittest discover -s tests
```

运行语法检查：

```bash
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m compileall -q skills/scripts
```

可写的字节码缓存目录可避免默认缓存不可写时重复编译。固定输入回放和同窗联网比较见 [tests/REPLAY.md](tests/REPLAY.md)。回放不能证明来源当前可用；实时验证依赖网络和第三方站点，因此与 CI 分开。

## 法律和归属

本项目与 Apple Inc. 无关联，未获得 Apple 认可或赞助。Apple、iPhone、iPad、Mac、Apple Watch、AirPods、Vision Pro 和其他 Apple 产品名称均为 Apple Inc. 的商标。

抓取器访问公开可用的 feed 和网页。使用者需自行遵守来源网站条款、robots 策略、频率限制、版权规则和适用法律。不要发布缓存源网页或长篇逐字引用文章内容。

## License

MIT。见 `LICENSE`。
