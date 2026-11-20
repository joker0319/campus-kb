"""请求 / 响应模型。

字段用 camelCase（ruleId / ruleCount），与前端 types.ts 的 Issue 对齐，
省掉前端一层字段名转换。
"""

from pydantic import BaseModel, Field

# 引擎原始严重级别（checker.py）：error / warn / info。
# 前端只有 error | warning 两档，映射关系：warn→warning，info→warning（但 counts 保留原始分档）。
Severity = str


class RuleOut(BaseModel):
    id: str
    category: str
    severity: str
    type: str
    desc: str
    suggestion: str = ""
    source: str
    file: str


class RulesResponse(BaseModel):
    total: int
    skipped: list[str] = Field(default_factory=list)
    rules: list[RuleOut]


class ReviewRequest(BaseModel):
    content: str = Field(min_length=1, max_length=200_000, description="稿件正文（纯文本）")
    mode: str = Field(
        default="submission",
        pattern="^(submission|archive)$",
        description="submission=投稿校验（默认，全量规则）；archive=档案检索（跳过投稿格式规则）",
    )


class Finding(BaseModel):
    key: str = Field(description="稳定 key：ruleId@line，同规则同行多次命中时追加 -2/-3 去重")
    ruleId: str
    severity: Severity
    line: int
    message: str
    excerpt: str
    suggestion: str = ""
    hit: str = Field(default="", description="精确命中文本（原文子串），供前端给任意稿件标红；行级规则为整行")


class Counts(BaseModel):
    total: int
    error: int
    warn: int
    info: int


class ReviewResponse(BaseModel):
    findings: list[Finding]
    counts: Counts
    ruleCount: int
