# apple-news-24h

[English](README.md) | **简体中文**

一个 Codex skill 和独立 Python 抓取器，用于生成最近 24 小时 Apple 软硬件新闻简报。

该 skill 会从指定中英文科技媒体发现候选文章，进入详情页核验发布时间，将时间统一转换到 UTC 后判断 24 小时窗口，并按事件级归并多源报道，最终输出中文双板块简报：`软件与系统` 和 `硬件与产品`。

## 状态

本项目仍处于实验阶段。新闻网站结构、RSS 可用性和页面时间字段都可能变化，过滤规则也需要持续维护。建议把输出视为结构化简报草稿，发布前仍进行人工审阅。

## 最新更新

### 1.60.0 - 2026-08-22

- 新增聚类前主张投影，仅在多标题第一方服务页面中的每个子事件都具有局部命名主体、具体动作和支持事实时才执行拆分，使独立 Apple TV 内容保持分离，并避免从背景文字生成虚假子事件。
- 将结构化协调器设为文章相关性与分类的权威判定层，为硬件组件、配色、零售包装、平台上线、供应商动作和量化市场报告增加变更对象身份，避免聚合摘要重新分类或桥接无关事件。
- 改进同源不同报道、第三方 Apple 平台工具、地区市场数据、当前产品里程碑、历史上手文章，以及 Apple Pay、AirPods、MacBook Pro、Apple Watch 和组织调整等直接动作的事件边界。
- 移除主抓取器中重复的事件组级相关性重分类路径及旧辅助函数，减少相互冲突的后处理，同时保留宽召回发现分组作为结构化协调器的候选方案。
- 更新手动兜底规则，并将回归测试由 1,124 项增加到 1,152 项；并发联网验证保持逐来源发现数量完全一致并覆盖全部 59 个来源 URL，运行时间由 55.3 秒降至 51.7 秒，纯净子代理验证无聚类警告，42 个主事件和延后事件 ID 均完成唯一落账。

## 它会做什么

- 收集 Apple 相关的软件、系统、服务、硬件、配件、健康、研究、法律和公司动作新闻。
- 优先使用 RSS/Atom，再按配置尝试来源页面和兜底发现。
- 尽可能进入文章详情页读取精确发布时间。
- 将文章时间统一转换到 UTC 后执行 24 小时窗口判断。
- 将多家媒体报道的同一实质事件归并成一条。
- 标注事件类型和相关性层级，保留宽抓取范围下的弱 Apple 关联候选，但避免它们污染最终简报。
- 抽取关键数字、列表、功能名、国家/地区、条款、资格条件和上线限制，用于生成更完整的摘要。
- 支持 Markdown 和 JSON 输出。

## 架构

- `scripts/apple_news_24h.py` 负责来源发现、页面抓取、时间核验、文章提取、事件编排及 Markdown/JSON 渲染。
- `scripts/apple_news_core/article_projector.py` 仅在每个子事件都具有局部命名主体、具体动作和支持事实时，将一个来源页面投影为多个可独立报道的第一方内容主张，从而同时避免服务事件混聚和由背景文字生成虚假子事件。
- `scripts/apple_news_core/event_identity.py` 将文章标题和导语转换为结构化事件身份，覆盖产品、组件、参与方、动作、地区、法律案件、内容形态和命名主体。正文只作为受约束的辅助证据，避免相关文章和背景段落重新定义事件。
- `scripts/apple_news_core/event_matcher.py` 使用保守的产品、组件、动作、地区、法律案件和主体兼容性规则比较事件身份。将该决策层保持为纯函数，使同事件聚类可以独立测试，也更便于维护。
- `scripts/apple_news_core/event_reconciler.py` 保留已接受的种子聚类，应用明确动作边界，并通过精确跨来源事件签名归并报道，避免泛相似度或传递桥接重新打开已经确定的事件组。
- `tests/test_event_identity_architecture.py` 及截至 `tests/test_20260822_authoritative_event_pipeline.py` 的按日期命名协调测试，为身份提取、匹配、结构化断言归并、动作归属、主张投影、变更对象边界、种子证据和相关性分层提供聚焦回归覆盖；现有抓取器测试则继续端到端验证发现、解析、聚类、渲染和来源清理。

## 它不会做什么

- 这不是 Apple 官方项目。
- 不提供投资、法律、医疗或购买建议。
- 当来源阻断请求、RSS 延迟或页面结构变化时，不保证完整覆盖。
- 不应用于转载完整文章或缓存的源网页内容。

## 作为 Codex Skill 安装

直接克隆到 Codex skills 目录：

```bash
git clone https://github.com/yuehunai/apple-news-24h "$CODEX_HOME/skills/apple-news-24h"
```

如果没有设置 `CODEX_HOME`，Codex 通常使用 `~/.codex`：

```bash
git clone https://github.com/yuehunai/apple-news-24h ~/.codex/skills/apple-news-24h
```

也可以把本仓库地址交给 Codex，让 Codex 自动安装：

```text
https://github.com/yuehunai/apple-news-24h
```

安装后显式调用，或通过自动化直接调用：

```text
$apple-news-24h
```

该 skill 在 `agents/openai.yaml` 中禁用了隐式触发，因此普通 Apple、科技或新闻对话不会自动调用它。

## CLI 使用

抓取器只使用 Python 标准库。

Markdown 输出：

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format markdown
```

JSON 输出：

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json
```

JSON 会将进入简报的项目放在 `events` 中。第三方应用、竞品对比等未描述 Apple 直接动作的弱 Apple 关联候选，可能保留在 `deferred_events` 中供审查。事件对象可包含 `event_kind`、`relevance_tier`、`relevance_reason`、`regions` 和 `merge_warnings`。

JSON 输出还可能包含 `final_brief_queue`、`required_final_brief_titles`、`final_brief_markdown`，并在使用 `--output` 时写入相邻的 `*.brief.md` 文件。这些字段是给自动化 agent 使用的覆盖校验清单；最终简报仍应根据完整 `events` 摘要、`key_facts` 和来源链接撰写。

调试来源失败时启用 diagnostics：

```bash
python3 scripts/apple_news_24h.py --hours 24 --timezone auto --format json --output latest.json --include-diagnostics
```

常用参数：

- `--hours 24`：回看窗口。
- `--timezone auto`：自动检测系统时区；也可以传入 `America/Los_Angeles` 这类 IANA 时区。
- `--format markdown|json`：选择输出格式。
- `--cache-dir PATH`：保存当前运行成功抓取的 HTTP 响应用于检查。
- `--output PATH`：原子写入完整结果文件，并在 stdout 仅打印简短状态 JSON。
- `--include-diagnostics`：包含抓取失败、来源失败、已选详情页抓取失败、发现兜底计数和低置信时间解析提示。

默认缓存目录是 Python 平台临时目录下的 `apple-news-24h`。脚本每次启动时会清空该目录并写入 marker 文件和当前运行响应。旧缓存不能作为新闻时效判断的兜底来源。

## 网络权限

抓取器需要实时网络访问 RSS、频道页和文章详情页。在沙盒化 agent 环境中，首次运行可能因 DNS 或网络权限被拦截。如果结果为空或异常稀疏，本 skill 会先用网络批准重跑同一命令。如果仍然失败，会查看 diagnostics 或走兜底发现流程。请确保您的沙盒网络设置至少为自动审查或更高权限。

## 来源

主要来源包括 MacRumors、9to5Mac、AppleInsider、The Verge、Apple Newsroom、IT之家、爱范儿、快科技和 cnBeta。补充兜底来源包括新浪科技/财经、网易科技、36氪，以及必要时的其他主流中文科技页面。

来源 URL、默认时区、纳入规则、排除规则、事件归并规则和兜底策略见 `references/news_policy.md`。

## 测试

运行离线测试：

```bash
python3 -m unittest discover -s tests
```

运行语法检查：

```bash
python3 -m py_compile scripts/apple_news_24h.py scripts/apple_news_core/event_identity.py scripts/apple_news_core/event_matcher.py scripts/apple_news_core/event_reconciler.py
```

实时 smoke test 依赖网络和第三方站点可用性，因此不放入默认 CI。

## 法律和归属

本项目与 Apple Inc. 无关联，未获得 Apple 认可或赞助。Apple、iPhone、iPad、Mac、Apple Watch、AirPods、Vision Pro 和其他 Apple 产品名称均为 Apple Inc. 的商标。

抓取器访问公开可用的 feed 和网页。使用者需自行遵守来源网站条款、robots 策略、频率限制、版权规则和适用法律。不要发布缓存源网页或长篇逐字引用文章内容。

## License

MIT。见 `LICENSE`。
