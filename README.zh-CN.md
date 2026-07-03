# apple-news-24h

[English](README.md) | **简体中文**

一个 Codex skill 和独立 Python 抓取器，用于生成最近 24 小时 Apple 软硬件新闻简报。

该 skill 会从指定中英文科技媒体发现候选文章，进入详情页核验发布时间，将时间统一转换到 UTC 后判断 24 小时窗口，并按事件级归并多源报道，最终输出中文双板块简报：`软件与系统` 和 `硬件与产品`。

## 状态

本项目仍处于实验阶段。新闻网站结构、RSS 可用性和页面时间字段都可能变化，过滤规则也需要持续维护。建议把输出视为结构化简报草稿，发布前仍进行人工审阅。

## 最新更新

### 1.18.0 - 2026-07-03

- 改进第三方转接头、MagSafe 手机壳、参考时间线、讲解视频、安装准备指南、公开采购回应和第三方浏览器/安全报道的弱相关过滤，避免仅把 Apple 设备或平台作为背景的内容进入必收事件。
- 改进 iCloud+ 权益、Apple 价格和股价反应、iPhone 生产计划回应、折叠 iPhone 产量目标，以及 iPhone 基带与 NAND/存储泄密细节的事件边界。
- 新增 iPhone 摄影奖处理，使跨源奖项报道保持可收录、可正确合并，并归类为硬件/产品生态新闻。
- 修复折叠 iPhone 1000 万台生产/订单报道的跨源合并，使共享同一产量目标的来源可合并，同时与面板份额、价格和更宽泛路线图背景保持分离。
- 更新兜底策略说明和回归测试，覆盖弱第三方噪音、教程排除、iPhone 摄影奖、价格/股价/生产拆分、基带与 NAND 泄密，以及折叠 iPhone 生产订单合并。

## 它会做什么

- 收集 Apple 相关的软件、系统、服务、硬件、配件、健康、研究、法律和公司动作新闻。
- 优先使用 RSS/Atom，再按配置尝试来源页面和兜底发现。
- 尽可能进入文章详情页读取精确发布时间。
- 将文章时间统一转换到 UTC 后执行 24 小时窗口判断。
- 将多家媒体报道的同一实质事件归并成一条。
- 标注事件类型和相关性层级，保留宽抓取范围下的弱 Apple 关联候选，但避免它们污染最终简报。
- 抽取关键数字、列表、功能名、国家/地区、条款、资格条件和上线限制，用于生成更完整的摘要。
- 支持 Markdown 和 JSON 输出。

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
python3 -m py_compile scripts/apple_news_24h.py
```

实时 smoke test 依赖网络和第三方站点可用性，因此不放入默认 CI。

## 法律和归属

本项目与 Apple Inc. 无关联，未获得 Apple 认可或赞助。Apple、iPhone、iPad、Mac、Apple Watch、AirPods、Vision Pro 和其他 Apple 产品名称均为 Apple Inc. 的商标。

抓取器访问公开可用的 feed 和网页。使用者需自行遵守来源网站条款、robots 策略、频率限制、版权规则和适用法律。不要发布缓存源网页或长篇逐字引用文章内容。

## License

MIT。见 `LICENSE`。
