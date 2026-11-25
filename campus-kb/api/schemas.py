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


class ReviewFileResponse(BaseModel):
    """docx 文件校验结果：提取文本 + 命中 + 可下载的 Markdown 报告。"""

    filename: str
    text: str
    findings: list[Finding]
    counts: Counts
    ruleCount: int
    report: str


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000, description="用户本轮提问")
    history: list[ChatMessage] = Field(default_factory=list, description="最近若干轮对话")


class ChatSource(BaseModel):
    ref: str = Field(description="片段编号，如 S1 / A1，供模型回答引用")
    kind: str = Field(description="rule=规范 / archive=档案")
    title: str
    detail: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    model: str


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000, description="用户本轮提问")
    history: list[ChatMessage] = Field(default_factory=list, description="最近若干轮对话")


class AgentStep(BaseModel):
    """一次工具调用及其结构化结果，供前端展示 Agent 的执行轨迹。"""

    tool: str
    args: dict
    result: dict
    callId: str = ""


class AgentResponse(BaseModel):
    answer: str
    steps: list[AgentStep]
    model: str
    usedTools: list[str]
    truncated: bool = False


class ComposeRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=400, description="文章选题或写作要求")
    style: str = Field(
        default="auto",
        description="文体：auto（按选题判定）/ news 新闻动态 / celebration 喜讯捷报 / speech 致辞讲稿",
    )


class ComposeArticle(BaseModel):
    title: str
    lead: str
    sections: list[dict]
    imageSuggestions: list[dict]


class ComposeSource(BaseModel):
    ref: str
    kind: str
    text: str
    file: str
    line: int


class ComposeCitationReport(BaseModel):
    cited: list[ComposeSource]
    uncitedParagraphs: int
    invalidCites: list[str]
    paragraphCount: int
    grounded: bool


class ComposeReview(BaseModel):
    counts: dict
    findings: list[dict]


class ComposeFigure(BaseModel):
    """从往期推文里挑出的真实配图（不是模型编的配图建议）。"""

    id: str
    url: str
    caption: str
    kind: str = Field(description="scene 实景 / crowd 合影 / chart 图表截图 / poster 海报长图")
    width: int
    height: int
    sourceTitle: str = Field(description="图片来源的往期推文标题")
    sourcePublished: str
    sectionIndex: int = Field(description="建议插在第几节（0 起）")
    sectionHeading: str
    score: float
    weak: bool = Field(description="true 表示只靠来源文章相关、图注对不上，需人工确认")


class ComposeResponse(BaseModel):
    topic: str
    article: ComposeArticle
    markdown: str
    html: str = Field(default="", description="可直接粘进公众号编辑器的内联样式 HTML 片段")
    sources: list[ComposeSource]
    rules: list[dict]
    meta: dict
    citations: ComposeCitationReport
    review: ComposeReview
    style: dict
    figures: list[ComposeFigure] = Field(default_factory=list)
    model: str


class ReviseRequest(BaseModel):
    """改稿请求：前端把上一版成稿连同素材编号一起回传，服务端无状态。

    sources / rules 必须原样带回，否则正文里的 [A#] 会失去指向。
    """

    topic: str = Field(default="", max_length=400, description="原选题，用于回显")
    instruction: str = Field(min_length=1, max_length=300, description="这次的修改要求")
    article: dict = Field(description="当前草稿结构（title/lead/sections/imageSuggestions）")
    sources: list[ComposeSource] = Field(default_factory=list)
    rules: list[dict] = Field(default_factory=list)
    style: str = Field(
        default="auto",
        description="沿用成稿时的文体 id（news / celebration / speech），避免改稿跑文体",
    )


class ReviseResponse(ComposeResponse):
    instruction: str


class PipelineRequest(ComposeRequest):
    """一键流水线请求：比普通成稿多一个「是否自动修订」开关。"""

    autoRevise: bool = Field(
        default=True, description="发前检查有 error 时是否自动修订一轮"
    )
