# 校园投稿质量门（campus-kb）

把媒体传讯处的三份规范文档，从「存着的 Word/PDF」变成「机器能执行的门槛」。

## 已验证的结果

| 场景 | 结果 |
| --- | --- |
| `samples/bad-draft.md`（埋了 12 处典型错误） | 命中 17 项：错误 11 / 警告 6 |
| `samples/good-draft.md`（完全合规） | 命中 0 项，零误报 |
| `University of Macau` 专有名词 | 正确跳过，未被 `Macau → Macao` 误伤 |

## 用法

```bash
python3 checker.py samples/bad-draft.md                  # 终端输出
python3 checker.py samples/bad-draft.md --md out.md      # 生成 Markdown 报告
python3 checker.py samples/bad-draft.md --json           # 供其他系统调用
```

退出码：有 `error` 返回 1，可直接接 CI 或投稿平台的前置校验。

## HTTP API（2026-11-18 起）

同一引擎的 FastAPI 封装，供校稿台前端调用：

```bash
uv sync                                                   # 安装依赖
uv run uvicorn api.main:app --reload --port 8000          # 启动
uv run pytest                                             # 61 个用例，含 bad 17 / good 0 基线断言
```

| 接口 | 说明 |
| --- | --- |
| `GET /api/health` | 存活检查 |
| `GET /api/rules` | 19 条规则 + 出处（total / skipped / rules[]） |
| `POST /api/review` | `{ content, mode? }` → `{ findings[], counts, ruleCount }`；`mode=submission`（默认）全量规则，`mode=archive` 跳过投稿格式规则；finding.key 为 `ruleId@line`，同规则同行多次命中追加 `-2/-3` |
| `GET /api/search?q=` | 语料库全文检索：关键词（空格分隔 AND）→ `{ total, scanned, results[{file,line,excerpt,hits}] }` |
| `POST /api/review-file` | 上传 `.docx` → `{ filename, text, findings[], counts, ruleCount, report }`；段落/表格文本提取后复用同一套规则，report 为 Markdown 报告 |
| `POST /api/chat` | `{ message, history? }` → `{ answer, sources[], model }`；单轮 RAG 问答（保留兼容）。未配置密钥 503，上游失败 502 |
| `POST /api/agent` | `{ message, history? }` → `{ answer, steps[], usedTools[], model, truncated? }`；DeepSeek Function Calling 自选 `search_rules` / `search_archive` / `review_draft`，工具在后端确定性执行后回灌。`steps` 为工具轨迹（工具名/参数/结构化结果），校验结论以规则引擎为准；循环上限 4 步 |

AI 配置：复制 `.env.example` 为 `.env`，填入 `DEEPSEEK_API_KEY`（可选 `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL`）。`.env` 已 gitignore，不会入库。未配置时仅 `/api/chat` 与 `/api/agent` 不可用，其他接口不受影响。

severity 说明：引擎分 `error / warn / info` 三档；前端两档映射为 `warn、info → warning`，`counts` 保留原始分档。决策见 `campus-portal/docs/adr-002-python-backend.md`。

真实语料校准（corpus/text/ 26 份）：PUNCT-001 对时间（22:00）、比值（1:1）、千分位（1,000）
数字间半角标点豁免；archive 模式扫全部档案时只剩内容规则命中（38 处，全是真问题）。

## 公众号文章入库（2026-11-23 起）

自有公众号的历史推文是语料里最有价值的一块：口径、惯用表述、活动记录都在里面，
且天然适合做 RAG 的资料源。`tools/fetch_wechat.py` 把文章转成和 `corpus/text/`
同格式的纯文本，`search.py` 用 `glob("*.txt")` 扫目录，**入库即被检索，无需改代码**。

```bash
# 单篇
python tools/fetch_wechat.py https://mp.weixin.qq.com/s/xxxx

# 批量（一行一个链接）
python tools/fetch_wechat.py --urls urls.txt

# 图片型推文必须加 --ocr
python tools/fetch_wechat.py --ocr https://mp.weixin.qq.com/s/xxxx
```

产出三样东西：

| 产出 | 位置 | 说明 |
| --- | --- | --- |
| 正文 | `corpus/text/<标题>_<日期>_WX.txt` | 与现有语料同格式；`_WX` 后缀标记来源 |
| 图片 | `corpus/images/<标题>/图N.jpg` | 公众号 CDN 有 referer 防盗链，直链外站显示不出来，必须落本地 |
| 元数据 | `corpus/wechat-sources.json` | 标题、公众号、发布时间、原文链接、字数、是否 OCR，用于溯源与去重 |

### 全量抓取整个公众号

公众号没有公开的文章列表 API，但后台「已发表」页面本身带登录态。`tools/collect_links.js`
在页面里直接调同源接口翻页，登录态由浏览器自己携带——不需要把 cookie 交给任何外部程序，
也不依赖会失效的第三方采集服务。

1. 浏览器打开公众号后台「内容与互动 → 已发表」；
2. F12 → Console（Chrome 首次需手动输入 `allow pasting` 回车解锁粘贴）；
3. 粘贴 `tools/collect_links.js` 全文，回车；
4. 脚本自动翻页，过滤已删文章、视频号与空链接，最后下载 `urls.txt`；
5. 交给抓取脚本：

```bash
python tools/fetch_wechat.py --ocr --urls urls.txt --drop-images
```

脚本兼容新旧两套后台接口（`appmsgpublish` / `appmsg`），一个不通会自动换另一个；
解析逻辑有独立测试：`node --test tools/collect_links.test.js`。

全量抓取要注意的四件事：

- **断点续跑**：`wechat-sources.json` 现在逐篇落盘，中断后重跑只补没抓的，不会从头再来；
- **磁盘**：长图型每篇图片约 20MB，上百篇就是 2GB 以上，`--drop-images` 在 OCR 落盘后清图；
- **限速**：默认每篇间隔 1.5 秒，几百篇建议分批跑，避免触发风控；
- **先编译 OCR**（见下），否则长图型推文会被直接拒绝入库。

### 两类推文，处理方式不同

1. **文字排版型**：正文在 HTML 里，直接提取。从 `#js_content` 取段落，
   剔掉「点击蓝字关注」这类模板噪音，图片转 `[图N]` 占位。
2. **长图型**（文字做在图片里，HTML 只有 `<img>`）：**必须加 `--ocr`**。
   不加会被直接拒绝入库——否则语料里只多一个搜不到任何内容的空壳。

OCR 用 macOS 自带的 Vision 框架（`tools/ocr.swift`），离线、中文质量好、不引三方依赖：

```bash
swiftc -O tools/ocr.swift -o tools/bin/ocr    # 首次需要编译，产物已 gitignore
```

对切片长图走 `--stitch`：公众号长图常被切成几十片，文字恰好落在接缝处会被腰斩，
逐张识别会出现「\态调整」这种缺字。按累积高度拼接后整组识别能大幅减少这类问题
（分组边界处仍可能有个别缺字，语料用于检索，不影响召回）。

### 已知边界

- 只处理**自己运营的公众号**。他人文章只能人工参考，内容和视觉设计都不能整篇搬。
- 后台列表接口是微信的非公开接口，**可能随版本改版**。脚本已在接口不返回预期结构时
  明确报错而不是静默返回空列表；真改版了需要重新适配（`tools/collect_links.js` 里的 `parsePublished`）。
- 检索仍是关键词 / 子串匹配，不是语义检索：换个说法（「挂牌那天」vs「奠基仪式」）
  就召回不到。这是 README 结尾「下一步」要解决的核心短板。
- OCR 有少量错字（形近字、接缝缺字），适合做检索语料，不适合直接引用出版。

## 目录

```
campus-kb/
├── checker.py              # 校验引擎，新增规则不用改代码
├── api/                    # FastAPI 薄封装（main.py + schemas.py + docx_io.py + deepseek.py + agent.py + search.py）
├── tools/                  # 本地工具：文章抓取（fetch_wechat.py）+ 列表采集（collect_links.js）+ Vision OCR（ocr.swift）
├── tests/                  # API 契约与基线回归（pytest）
├── rules/                  # 规则库，全部来自规范原文
│   ├── naming.json         # 校名（首次全称、全角括号、英文空格）
│   ├── title.json          # 头衔职务对照
│   ├── sovereignty.json    # 港澳台与领土主权
│   ├── punctuation.json    # 数字与标点
│   ├── english.json        # 英式拼写、序数词
│   ├── submission.json     # 投稿字段与流程
│   ├── rank.json           # 排名数据一致性
│   └── layout.json         # 排版模板配置（生成用，非校验）
├── samples/                # 正反样例
├── corpus/                 # 真实档案语料（2021 奠基仪式等，仅存本地，不入 git）
└── reports/                # 生成的报告
```

`corpus/` 存放媒体传讯处的真实历史档案（新闻通稿、致辞讲稿、执行物料、对外报告等五类 32 份，
清单见 `corpus/INDEX.md`），以及用 `tools/fetch_wechat.py` 抓取的自有公众号推文（当前 24 篇，
约 5 万字，检索时扫描 50 份文本）。
因含真实人名与内部信息被 `.gitignore` 排除，仅作本地用途：拿真实稿件跑引擎测误报/漏报，
并作为 Agent 档案检索的资料源。

## 规则覆盖（19 条）

| 类别 | 规则 | 依据 |
| --- | --- | --- |
| 校名 | NAME-001~003 | 手册 一、学校名称 |
| 头衔 | TITLE-001~002 | 手册 二、头衔与职称 |
| 港澳台 | SOEV-001~004 | 手册 三、港澳台与领土主权 |
| 标点数字 | PUNCT-001~003 | 手册 三、数字与标点符号 |
| 英文 | ENG-001~002 | 手册 三、英文使用规范 |
| 投稿 | SUB-001~004 | 投稿须知 A75 |
| 数据 | RANK-001 | 手册 三、排名相关 |

新增一条规则 = 在对应 JSON 里加一个对象，不改 Python。

## 校验时发现的原文问题

规则跑起来第一件事，是把规范文档自己的毛病抖出来了：

1. **QS 排名自相矛盾**：中文版「2027 年 QS 第 63 位」，英文版同一段写 `52rd`（还拼错了，应为 52nd）。
2. **版本号不一致**：文件名 `20260618`，封面写 `2026.05`。
3. **存在 `(2)` 副本**：说明同一份手册已有多版在流转，没有唯一现行版。

这三条建议先由媒体传讯处确认权威值，再写进 `rank.json`，否则工具会一直报冲突。

## 已知限制

- 只做**文本规则**，不判断内容事实是否属实、图片是否合规（这两类仍需人工）。
- 中文分词靠正则，遇到长句中的职务简称（如「段校长」）可能漏判，目前靠人名 + 窗口匹配兜底。
- `layout.json` 只是排版参数，尚未接入文档生成。

## 下一步

1. **P1 生成**：按 `layout.json` + 报送模板，输入要点直接产出符合字体的初稿。
2. **P2 入库**：把原始 Word/PDF 解析后入 WorkBuddy 资料库，支持「这条规范怎么写的」问答并带出处。
3. **P3 闭环**：投稿平台审核不通过的原因回流，自动补充规则。
