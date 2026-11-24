# campus-kb · 知识库与校验引擎（项目后端模块）

> 本目录是「RAG 知识库 + Agent 内容助手 → 生成公众号文章」项目的**后端模块**：语料、检索、规则引擎与 FastAPI 都在这里。稿件规范校验是项目的其中一项功能，规则引擎即为该功能的实现。

把媒体传讯处的规范、档案与往期推文沉淀为可检索语料；同时把三份规范文档变成「机器能执行的门槛」。

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
uv run pytest                                             # 155 个用例，含 bad 17 / good 0 基线、文章生成 19 项、文体模板 14 项、配图推荐 16 项、语义检索 15 项
```

| 接口 | 说明 |
| --- | --- |
| `GET /api/health` | 存活检查 |
| `GET /api/rules` | 19 条规则 + 出处（total / skipped / rules[]） |
| `POST /api/review` | `{ content, mode? }` → `{ findings[], counts, ruleCount }`；`mode=submission`（默认）全量规则，`mode=archive` 跳过投稿格式规则；finding.key 为 `ruleId@line`，同规则同行多次命中追加 `-2/-3` |
| `GET /api/search?q=&mode=` | 语料库混合检索（BM25 + 本地语义向量，RRF 融合）；`mode` 见下节 → `{ total, scanned, mode, retrieval, results[{file,line,endLine,excerpt,hits,score,similarity,matchedBy}] }` |
| `POST /api/review-file` | 上传 `.docx` → `{ filename, text, findings[], counts, ruleCount, report }`；段落/表格文本提取后复用同一套规则，report 为 Markdown 报告 |
| `POST /api/chat` | `{ message, history? }` → `{ answer, sources[], model }`；单轮 RAG 问答（保留兼容）。未配置密钥 503，上游失败 502 |
| `POST /api/agent` | `{ message, history? }` → `{ answer, steps[], usedTools[], model, truncated? }`；DeepSeek Function Calling 自选 `search_rules` / `search_archive` / `review_draft`，工具在后端确定性执行后回灌。`steps` 为工具轨迹（工具名/参数/结构化结果），校验结论以规则引擎为准；循环上限 4 步 |
| `POST /api/compose` | `{ topic, style? }` → `{ article, markdown, sources[], citations, review, ... }`；文章生成主线：检索素材编号 → DeepSeek JSON 成稿（每段带 `[A#]` 引用）→ 后端校验出处（`grounded` / 无出处段 / 无效引用）+ `archive` 模式发前规范检查。无依据段落明确标注，不臆测 |
| `GET /api/figure/{id}` | → 图片二进制；成稿返回的 `figures[].url` 就指向这里。索引缺失或文件被删返回 404，前端显示占位 |
| `GET /api/figures/stats` | → `{ total, kinds }`，确认配图库状态 |
| `POST /api/compose/revise` | `{ topic, instruction, article, sources[], rules[], style? }` → 同 compose 结构 + `instruction`；改稿：前端把上一版草稿与 `A#` 素材原样回传，服务端无状态、**不重新检索**（否则正文引用会指向别处），只按指令改被点名的部分，改完重跑引用核对 + `archive` 发前检查；模型输出不可解析时保留原稿 |

AI 配置：复制 `.env.example` 为 `.env`，填入 `DEEPSEEK_API_KEY`（可选 `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL`）。`.env` 已 gitignore，不会入库。未配置时仅 `/api/chat`、`/api/agent`、`/api/compose`、`/api/compose/revise` 不可用，其他接口不受影响。

## 文体模板（api/styles.py）

三套模板：`news` 新闻动态 / `celebration` 喜讯捷报 / `speech` 致辞讲稿。
每套含标题规则、导语要求、结构骨架（喂给模型组织 `sections`）、语气、篇幅、避免项。
**模板只约束结构，不写任何具体事实**——模板里出现数字或人名就会和素材打架。

结构从本项目语料真实成稿提炼：合作大学联盟会议报道（导语五要素 → 分环节 → 意义收束）、
41 位学者入选榜单喜讯（来源背景 → 数字成果 → 名单 → 表态 → 榜单说明）、
奠基仪式致辞（称呼问候 → 里程碑 → 回顾优势 → 规划致谢 → 祝愿）。

`style` 缺省 `auto`：按选题关键词路由，致辞类优先判定，其次喜讯类，其余落新闻；
显式指定永远优先（选题里有「喜讯」也按用户点的新闻写）；未知值按 `auto` 处理，不返回 422。
文体块同时注入成稿与改稿的 system prompt——改稿不带文体，模型容易把致辞改成新闻腔。

## 配图推荐（api/figures.py）

成稿只给「建议配什么图」不够用——文章要真能发出去得有照片。语料里 24 篇推文已经
把原图整篇扒下来了（657 张），这里把它们变成可检索的图库。

```bash
uv run python tools/build_figure_index.py    # 过滤碎图 + 按字节去重 → 177 张真配图
uv run python tools/make_contact_sheets.py   # 拼 20 张九宫格
# 逐格标注（一句话描述 + 图像性质）→ corpus/images/captions.raw.json
uv run python tools/apply_captions.py        # 回填进 INDEX.json
```

- 过滤阈值：宽 ≥600、高 ≥400、体积 ≥40KB，去动图。公众号正文里混着 1080x92 分隔线、
  1KB 的 400x400 占位块、表情动图，不滤掉会被当成配图推出去；657 → 177（另去重 116 张）；
- 标注分 8 类：`scene` 实景 50 / `portrait` 肖像 41 / `crowd` 合影 29 / `poster` 海报 24 /
  `chart` 图表 17 / `slide` 长图分段 11 / `qr` 二维码 3 / `icon` logo 2，可推 120 张；
- **肖像不推**：真实师生单人照涉及肖像权，系统不替编辑做决定；`slide`（招生长图的
  「PART 1/2/3」）、`qr`、`icon` 永不推；
- 打分 = `(0.7 × 图注相关度 + 0.3 × 来源文章相关度) × 性质权重`（实景 1.0 / 合影 0.9 /
  图表 0.75 / 海报 0.65）。图注与段落至少共享 **2 个 2-gram** 才算真命中——只共享
  「全国」这种常见词会把同篇推文里无关的合影认成相关图；只靠来源标题蹭到分的标 `weak`，
  整节没有任何真命中时才补一张并标注「关联度一般，请确认」；
- 全篇不重复用同一张；分数低于 0.5 宁可不配图。

索引 `corpus/images/INDEX.json` 与图片本体都在 `corpus/`（含真实师生影像，已 gitignore），
只在本机存在：换机器要重跑建库脚本，标注需重新做。

## 语义检索（api/rag.py）

`GET /api/search` 默认走混合召回：语料按段落分块（带文件名 + 起止行号），
稀疏路 BM25（中文字符 2-gram）+ 稠密路本地 ONNX 向量，按 RRF 名次融合。
`mode` 可选 `hybrid`（默认）/ `keyword`（仅 BM25）/ `semantic`（仅向量）/
`strict`（旧的逐行 AND，留作回归对照）。响应的 `retrieval` 字段说明本次是否
真的启用了语义路；每项结果的 `matchedBy` 标明是哪一路召回。

稠密路用 `fastembed` + `BAAI/bge-small-zh-v1.5`（512 维），**本地推理、不调外部
embedding API、不需要额外密钥**；模型首次使用从 `HF_ENDPOINT`（默认 hf-mirror.com）
下载约 95MB 到本机缓存，之后 0.25s 加载。向量索引按语料版本戳缓存在
`corpus/.index/`（已 gitignore），语料一变自动重建；首次建索引约 30s，之后每次
检索 0.03–0.06s。模型下载失败或设 `CAMPUS_EMBEDDING=off` 时自动降级纯 BM25，
接口不受影响。可选配置见 `.env.example`：`CAMPUS_EMBEDDING`、
`CAMPUS_EMBEDDING_MODEL`、`HF_ENDPOINT`、`CAMPUS_INDEX_DIR`。
单测默认关模型并用假向量注入，不依赖这 95MB 下载。

severity 说明：引擎分 `error / warn / info` 三档；前端两档映射为 `warn、info → warning`，`counts` 保留原始分档。决策见 `campus-portal/docs/adr-002-python-backend.md`。

真实语料校准（corpus/text/ 26 份）：PUNCT-001 对时间（22:00）、比值（1:1）、千分位（1,000）
数字间半角标点豁免；archive 模式扫全部档案时只剩内容规则命中（38 处，全是真问题）。

## 公众号文章入库（2026-11-23 起）

自有公众号的历史推文是语料里最有价值的一块：口径、惯用表述、活动记录都在里面，
且天然适合做 RAG 的资料源。`tools/fetch_wechat.py` 把文章转成和 `corpus/text/`
同格式的纯文本，`search.py` 用 `glob("*.txt")` 扫目录，**入库即被检索，无需改代码**；语料文件版本戳变化会让向量索引自动重建，新推文同样无需重启。

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

### 拿不到后台登录态时：逐篇累积

后台进不去就只能一篇篇复制链接。为此工具不要求整齐的清单格式，任意文本都能解析：
从整段粘贴里扫出所有 `mp.weixin.qq.com/s` 链接，标题、分享卡片、粘连无分隔、
带 `?scene=1#rd` 追踪参数的都能正确处理；短链会归一成规范形态，
所以同一篇从不同入口复制多次也只抓一遍。

```bash
# 方式一：直接粘贴（Ctrl-D / Cmd-D 结束输入）
python tools/fetch_wechat.py --paste --ocr --drop-images

# 方式二：攒进收件箱，攒几条抓一次；不带任何参数时默认就读它
python tools/fetch_wechat.py --ocr --drop-images
```

`inbox.txt` 已 gitignore，不用清理——已入库的链接会自动跳过，留在里面当记录。
粘连漏抽是这里最容易踩的坑：整体正则贪婪匹配会吞掉下一条链接的 `https`，
实测 4 条只抽到 2 条，所以改成了前缀与正文分开扫描，并由测试锁住。

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
├── api/                    # FastAPI 薄封装（main.py + schemas.py + docx_io.py + deepseek.py + agent.py + compose.py 成稿/改稿 + styles.py 文体模板 + figures.py 配图推荐 + search.py + rag.py 混合检索）
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

## 权威口径裁决

规范原本有多版并存、自身数据打架，2026-11-24 由媒体传讯处一次性裁决，记录在 [`authority.json`](authority.json)——规则引擎、Agent 系统提示、文章生成共用这一份，不再各处硬编码：

| 争议 | 裁决 |
| --- | --- |
| QS 排名中英不一致（中文「第 63 位」/ 英文 `52rd`） | **2027 年 QS 世界大学排名为第 52 位**；63 为旧版错误值，`52rd` 序数词拼错（应为 `52nd`）。语料中两篇官方推文亦记为第 52 位 |
| 版本号不一致（文件名 `20260618` / 封面 `2026.05`） | 以 **20260618** 为准，`2026.05` 废止 |
| 带 `(2)` 的副本在流转 | **副本一律忽略**，不作为依据 |

规则引擎据此从「只报冲突、等人拍板」升级为「偏离权威值即判错」：文内 QS 排名写成 63，或同一届次出现多个数值，`RANK-001` 直接给出应为第 52 位的结论（见 `rank.json` 的 `suggestion`）。`rules/*.json` 的出处已统一标注 20260618。原始规范文件仍不在仓库内。

## 已知限制

- 规则只做**文本规则**，不判断内容事实是否属实、图片是否合规（这两类仍需人工）。
- 中文分词靠正则，遇到长句中的职务简称（如「段校长」）可能漏判，目前靠人名 + 窗口匹配兜底。
- 配图库只在本地：图片与索引都在 `corpus/`（真实师生影像，不入库），换机器需重跑建库 + 重新标注。
- 配图推荐靠图注文字匹配，图库没覆盖的主题（如新活动）会返回空——设计上宁可空着，不拿不相关的图凑数。

## 下一步

1. **排版导出**：公众号编辑器只认内联样式，现在是 Markdown。按往期推文的版式产出一份可直接粘贴的
   HTML（段落缩进、行距、小标题样式、图片占位），把「复制到后台还要手动排版」这一步省掉。
2. **图注可用性**：现在 177 张图的描述是一次性标注的，新增推文要靠人工再过一遍；
   可以把拼图 + 视觉识别做成半自动流程。
3. **多稿对比**：同选题跑 2–3 版挑一版，或让编辑在两条改稿路径里选。
