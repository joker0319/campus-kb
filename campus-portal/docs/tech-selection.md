# 技术选型（ADR-001）

> 决策时间：2026-11-11 ｜ 修订：2026-11-18，后端语言经 [ADR-002](adr-002-python-backend.md) 改定 Python
> 约束：2-3 人小组维护，要求结构完整可扩展

## 一、决策

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 前端 | React 19 + Vite + TypeScript | 小组分工，构建快，不强绑框架 |
| UI | CSS Modules（Tailwind 仅规划） | 设计值是精调 px，utility 会变成一堆 arbitrary value |
| 后端 | **Python + FastAPI**（修订自 NestJS） | 复用已验证的规则引擎，见 ADR-002 |
| 规则引擎 | Python（`campus-kb/checker.py`） | 正则 + JSON，新增规则不改代码 |
| 主库 | PostgreSQL 16（规划） | 关系模型 + 全文检索 + 向量，一个库解决 |
| 文件存储 | MinIO（规划） | S3 兼容，后期可平滑迁云 |
| 文档解析 | PyMuPDF / PaddleOCR（规划） | 中文 OCR 与版面分析生态最强 |

## 二、架构（现行）

```
┌──────────────┐      ┌─────────────────────────┐
│ web 静态构建  │ ──→  │ FastAPI（校验 + 解析）   │ ──→ PostgreSQL（规划）
│ React + TS   │ JSON │ rules/*.json + checker  │
└──────────────┘      └─────────────────────────┘
```

校验无并发瓶颈，规则全部为纯函数；引入队列/worker 的时机由解析与生成任务触发，不预先搭建。

## 三、仓库结构（实际）

```
campus-kb/          规则引擎 + FastAPI API + pytest 基线
campus-portal/web   React 前端（首页 + 校稿台）
campus-portal/docs  ADR
```

未采用原计划的 pnpm monorepo 多包结构：当前规模下两个目录足够，规模上来再拆。

## 四、数据模型要点（P1 前定稿）

```
User ─┬─ Role（通讯员 / 复审 / 终审 / 管理员）
Asset ─┬─ FileObject（多版本）
Rule ─┬─ RuleSet（版本化，对应手册不同版本）
       └─ Finding（校验结果，可回放）
Submission ─┬─ ReviewRecord（三审三校流水）
```

两条铁律：

1. **一切内容带 `valid_from` / `valid_until`**：手册本身有多版并存问题，模型层必须先解决；
2. **规则要版本化**：手册已改过版（2026.05 → 20260618），历史稿件的校验结论必须可追溯。

## 五、分期

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 规则引擎、API、前端界面 | ✅ 完成 |
| P1 | 前端接接口、docx 解析、导出批注 docx | 进行中 |
| P2 | 投稿流程：表单、三审三校、版本管理 | 未开始 |
| P3 | 带出处的规范问答、初稿生成 | 未开始 |

## 六、被否决的方案

| 方案 | 否决原因 |
| --- | --- |
| Next.js 全栈单体 | 前后端分离便于分工；重任务需要独立服务 |
| MongoDB / MySQL | 强关系模型；向量检索成熟度不如 pgvector |
| Elasticsearch | 万级文档用不上，多一个组件多一份运维 |
| Supabase / Firebase | 学校数据不落公有云托管服务 |
| 微服务 + K8s | 单机部署，K8s 纯负担 |
| Go 后端 | 正则引擎限制 + 解析生态缺失，见 ADR-002 |
