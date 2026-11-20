# ADR-002：后端采用 Python（FastAPI），规则引擎不再迁移 TS

> 决策时间：2026-11-18
> 状态：已采纳（修订 ADR-001 中的规则引擎迁移决定）
> 约束：2-3 人小组维护 / 解析必须依赖 Python 生态

## 一、决策

1. 后端为 **Python（FastAPI）**，直接封装既有 `campus-kb/checker.py`，规则引擎**不迁移** TypeScript；
2. 后续的文档解析（PyMuPDF / PaddleOCR）并入同一服务，`campus-kb` 保持「校验 + 解析」单一 Python 服务；
3. 前端不变（React + TS），通过 `openapi-typescript` 由 OpenAPI 生成类型，保持端到端类型安全；
4. ADR-001 中「规则引擎 TypeScript 重写（源：campus-kb）」与 `packages/rules/` 规划**作废**。

## 二、理由

| 论点 | 说明 |
| --- | --- |
| 引擎已验证，重写零收益 | bad 17 / good 0 的回归基线已在手；跨语言迁移正则（全角、Unicode 边界）只会引入风险 |
| Python 运行时本来躲不掉 | 解析（PyMuPDF/PaddleOCR）没有可用的 TS/Go 替代；既然必须有 Python，TS 重写「统一栈」的理由不成立 |
| 运行时更少 | ADR-001 隐含 NestJS API + Python 解析两个服务；合并后是「一个 FastAPI 服务 + 静态 React 构建」 |
| 文本规则是 Python 主场 | `re`、Unicode 处理、后续分词兜底，Python 生态最顺 |
| Go 已否决 | RE2 不支持环视/反向引用，19 条规则需算法级重写；解析仍依赖 Python，全维度劣势 |

## 三、代价与对策

- 两套工具链（npm + uv）：CI 分开跑，各自 `check`/`pytest`；
- 团队 TS 背景：API 层刻意做薄（约 150 行），复杂度留在 checker.py 的纯函数里；
- 类型不同步：OpenAPI 生成前端类型，接口变更在 CI 中暴露。

## 四、契约（首版已实现）

- `GET  /api/health` — 存活检查
- `GET  /api/rules` — 19 条规则 + 出处（total / skipped / rules[]）
- `POST /api/review` — `{ content }` → `{ findings[], counts, ruleCount }`
  - finding：`key`（`ruleId@line`，同规则同行命中追加 `-2/-3`）、`ruleId`、`severity`（error/warn/info，前端映射 warn|info → warning）、`line`、`message`、`excerpt`、`suggestion`

回归护栏：`campus-kb/tests/test_api.py` 中 bad-draft 17 / good-draft 0 的基线断言，任何导致数字变化的改动必须先解释。

## 五、落地顺序

1. ✅ `POST /api/review`、`GET /api/rules`、`GET /api/health`（2026-11-18）
2. 前端 `data/content.ts` 换接真实接口（OpenAPI 生成类型）
3. `POST /api/parse`：docx/PDF 解析（PyMuPDF 先行，OCR 视硬件条件）
4. 导出带批注 docx
