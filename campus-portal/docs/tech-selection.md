# 技术选型决策（ADR-001）

> 决策时间：2026-11-11
> 约束条件：学校内网部署 / 2-3 人小组维护 / 要求结构完整可扩展

## 一、决策摘要

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 前端 | React 19 + Vite + TypeScript | 小组分工，构建快，不强绑框架 |
| 前端状态/请求 | TanStack Query + Zustand | 服务端状态与客户端状态分离，避免 Redux 样板 |
| 前端 UI | Tailwind CSS + shadcn/ui | 组件可控可改，内网无 CDN 依赖 |
| 后端 | NestJS 11 + TypeScript | 模块化清晰，DI 便于替换实现，鉴权/拦截器生态成熟 |
| ORM | Prisma 6 | 迁移管理成熟，类型生成可靠；复杂检索用 `$queryRaw` 兜底 |
| 主库 | PostgreSQL 16 | 关系模型 + 全文检索 + 向量，一个库解决 |
| 向量 | pgvector | 免维护向量库，避免双写一致性 |
| 队列 | BullMQ + Redis 7 | 解析/OCR/生成任务异步化，失败可重试 |
| 文件存储 | MinIO | 内网自建 S3 兼容，后期可平滑迁云 |
| 文档解析 | Python 服务（PyMuPDF + PaddleOCR） | 中文 OCR 与版面分析 Python 生态最强 |
| 规则引擎 | TypeScript 重写（源：campus-kb） | 逻辑仅正则 + JSON，与主栈统一，少一种运行时 |
| 本地推理 | Ollama + Qwen2.5-14B-Instruct | 内网无法出网时的兜底方案 |
| 部署 | Docker Compose（单机 / 双机） | 内网无 K8s，Compose 足够；先单机后拆分 |

**放弃前后端同构（Next.js 全栈）**：小组分工与后端能力展示的价值高于少写一套部署。

## 二、内网环境的三个硬约束

这三件事必须在写第一行业务代码前定掉，否则后期返工代价极大。

### 1. LLM 能否出网（影响最大）

内网服务器通常禁止外联。三种情况对应三套产品设计：

| 情况 | 方案 | 影响 |
| --- | --- | --- |
| 能申请到出口白名单（仅允许指定 API 域名） | 调用云端模型 API | 功能完整，成本按量 |
| 完全不能出网，但有 GPU（≥12GB 显存） | Ollama + Qwen2.5-14B-Instruct 量化版 | 能改写润色，抽取精度下降约 10-15% |
| 完全不能出网，只有 CPU | **放弃在线生成**，只做规则校验 + 检索 | 仍覆盖 80% 痛点，见下 |

**关键判断**：即使只有 CPU，`campus-kb` 的 19 条规则校验和全文检索也已经是完整可用的产品。**生成是加分项，不是地基**。不要为了生成去赌一个不稳定的部署环境。

### 2. 依赖如何离线安装

- npm 包：提前配置内网 registry 镜像（Verdaccio / Nexus），或 `npm pack` 打离线包
- Docker 镜像：`docker save` / `docker load` 离线导入，镜像清单固化在 `infra/images.txt`
- Python 包：`pip download -d wheelhouse` + 本地索引
- OCR 模型、向量模型文件需单独下载并随镜像打包（PaddleOCR 模型约 200MB）

**这件事要在 P0 阶段验证一次**，不要等到部署时才发现装不上。

### 3. 统一身份认证

学校内网通常有 CAS / LDAP / OAuth2。三种接入方式：

- **有 CAS**：后端接 `passport-cas`，前端跳转登录，最小改动
- **有 LDAP**：`ldapts` 直连，账号密码登录
- **都没有**：自建账号体系 + 管理员开通，但权限模型要设计得更细

需要确认：**是否已有统一身份，协议是什么**。这决定登录模块是 2 天还是 2 周。

## 三、部署架构

```
            ┌─────────────┐
   内网用户 →│  Nginx      │ TLS 终止 / 静态资源 / 反向代理
            └──────┬──────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
   ┌────▼───┐ ┌───▼────┐ ┌───▼────────┐
   │ web    │ │ api    │ │ worker     │
   │ React  │ │ NestJS │ │ BullMQ     │
   └────────┘ └───┬────┘ └───┬────────┘
                  │          │
      ┌───────────┼──────────┼──────────┐
      │           │          │          │
 ┌────▼────┐ ┌────▼────┐ ┌───▼────┐ ┌──▼──────┐
 │ PG 16   │ │ Redis 7 │ │ MinIO  │ │ parser  │
 │pgvector │ │         │ │        │ │ Python  │
 └─────────┘ └─────────┘ └────────┘ └────┬────┘
                                          │
                                     ┌────▼────┐
                                     │ Ollama  │ 可选
                                     └─────────┘
```

## 四、仓库结构（pnpm monorepo）

```
campus-portal/
├── apps/
│   ├── web/            React + Vite
│   ├── api/            NestJS（REST + OpenAPI）
│   ├── worker/         异步任务：解析派发、生成、批量校验
│   └── parser/         Python：PDF 解析 / OCR / 版面还原
├── packages/
│   ├── shared/         zod schema、DTO、常量（前后端共用）
│   ├── rules/          规则引擎（从 campus-kb 迁移为 TS）
│   └── sdk/            由 OpenAPI 生成的类型安全客户端
├── infra/
│   ├── docker-compose.yml
│   ├── images.txt      离线镜像清单
│   └── pg/init.sql     pgvector、中文分词、全文检索索引
└── docs/               ADR 与技术文档
```

**`campus-kb` 的归位**：规则 JSON 直接迁入 `packages/rules/rules/`，`checker.py` 的历史逻辑作为对照测试用例（bad-draft 命中 17 项、good-draft 命中 0 项必须在新实现里保持一致）。

## 五、数据模型要点

核心实体（P1 前必须定稿）：

```
User ─┬─ Role（通讯员 / 复审 / 终审 / 管理员）
      └─ Department
Asset（资源）─┬─ FileObject（对象存储引用，支持多版本）
              ├─ Tag / Category
              └─ Version（valid_from / valid_until / superseded_by）
Rule（规则）─┬─ RuleSet（版本化，对应手册的不同版本）
             └─ Finding（校验结果，可回放）
Submission（投稿）─┬─ ReviewRecord（三审三校流水）
                   └─ ChecklistResult（投稿须知自查结果）
```

**两条设计铁律**：

1. **一切内容都要有 `valid_from` / `valid_until`**：规范手册本身就有多版并存的现实问题，模型层必须先解决。
2. **规则要版本化**：手册从 2026.05 到 20260618 已经改过一次，规则变更必须可追溯，否则历史稿件的校验结论无法解释。

## 六、分阶段落地

| 阶段 | 内容 | 周期 | 验收标准 |
| --- | --- | --- | --- |
| P0 | 脚手架、Compose 起全栈、登录打通、离线依赖验证 | 2 周 | 内网机器上 `docker compose up` 能跑通登录 |
| P1 | 资源库核心：上传、分类、预览、全文检索、版本管理 | 3 周 | 现有 9 份文档迁入，按条款可检索 |
| P2 | 投稿流程：表单、三审三校、规则校验接入、图片规范提示 | 3 周 | 一篇稿子从提交到发布全流程可走通 |
| P3 | 检索增强：带出处的规范问答；初稿生成（视 LLM 条件） | 3 周 | 问答引用准确率 ≥ 90% |

P0 的离线验证不要跳过——这是内网项目最常见的翻车点。

## 七、被否决的方案

| 方案 | 否决原因 |
| --- | --- |
| Next.js 全栈单体 | 小组分工与后端展示价值更高；重任务仍需独立 worker |
| MongoDB | 投稿、审核、权限是强关系模型，文档库会持续用应用层补关系 |
| MySQL | 向量检索依赖插件，成熟度不如 pgvector |
| Elasticsearch | 数据量级（万级文档）用不上，多一个组件多一份运维 |
| Supabase / Firebase | 学校数据不得放公有云托管服务，IT 审批无法通过 |
| 微服务 + K8s | 内网单机部署，K8s 纯负担 |
