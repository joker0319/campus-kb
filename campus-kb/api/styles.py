"""公众号文体模板：新闻 / 喜讯 / 致辞。

模板只约束「结构骨架 + 语气要点」，不碰素材与出处规则——事实仍然只能来自
检索到的 A# 素材块，引用核对照旧。这里不放任何具体事实，避免与语料冲突。

结构取自本项目语料里的真实成稿：
  - 新闻：《全国合作大学齐聚…》导语五要素 → 分环节小节 → 意义收束
  - 喜讯：《喜讯丨港城莞41位学者入选…》来源背景 → 数字成果 → 名单 → 表态 → 榜单说明
  - 致辞：《于吉红院士…奠基仪式致辞》称呼问候 → 里程碑意义 → 回顾与优势 → 规划与致谢 → 祝愿
"""

from __future__ import annotations

# style id → 模板。auto 不在表内，由 resolve_style 按选题判定。
STYLES: dict[str, dict] = {
    "news": {
        "id": "news",
        "name": "新闻动态",
        "summary": "会议、活动、来访、签约、合作等事件报道",
        "titleRule": "事件主体 + 动作或成果，不加感叹号堆砌，一般不超过 22 字",
        "leadHint": "导语 100 字以内，一段说清时间、地点、主体、事件、主题或规模",
        "structure": [
            "现场与主题：主办方、出席层级、会议或活动的主题与规模",
            "关键发言：每位发言者单独一段，写明身份与核心观点，不混成一段",
            "成果与共识：达成的合作、发布的计划、形成的机制",
            "意义与展望：一段收束，落到具体方向，不空喊口号",
        ],
        "tone": "第三人称客观报道，不抒情、不用「我们」，不替受访者下判断",
        "length": "800–1200 字，3–4 节",
        "avoid": "不写成通稿套话；不虚构未在素材中出现的姓名、职务、数据",
    },
    "celebration": {
        "id": "celebration",
        "name": "喜讯捷报",
        "summary": "获奖、入选、获批、立项、排名等好消息",
        "titleRule": "「喜讯丨」+ 主体 + 具体成果，尽量带数字或名次",
        "leadHint": "导语 60 字以内，直接点出最硬的数字或名次，不要铺垫",
        "structure": [
            "来源与背景：谁发布、什么榜单或赛事、第几届或哪一版",
            "本校成果：用具体数字说清入选或获奖规模、学科或领域分布",
            "明细（有名单时）：分项列出，并说明排序规则",
            "意义与表态：这件事说明什么，学校接下来会做什么",
            "背景说明：榜单口径、统计方法、主办方（有素材才写）",
        ],
        "tone": "克制，以事实和数字说话，形容词只留必要的一个",
        "length": "600–900 字，2–3 节（名单可单列一节）",
        "avoid": "不夸大成「历史性突破」「里程碑」；数字必须来自素材，不确定就不写",
    },
    "speech": {
        "id": "speech",
        "name": "致辞讲稿",
        "summary": "奠基、典礼、论坛、签约等场合的致辞与讲话",
        "titleRule": "场合 + 致辞，如「在××仪式上的致辞」",
        "leadHint": "称呼与问候，如「尊敬的各位领导、各位嘉宾：大家好！」，不加长段铺垫",
        "structure": [
            "开场：说明代表谁发言，点出这个场合的意义",
            "回顾与基础：本校或本项目的历程、优势、已有成果",
            "规划与愿景：合作方向、学科布局、具体举措",
            "致谢：按层级致谢主办方、协作单位、社会各界",
        ],
        "tone": "第一人称，庄重得体；可引一句古诗文，全篇不超过一处",
        "length": "800–1200 字，3–4 个主体段",
        "avoid": "不用新闻报道的第三人称口吻；不编造出席人姓名与职务",
    },
}

DEFAULT_STYLE = "news"

# keyword 命中即归入该文体；顺序即优先级（致辞最明确，先判）
_AUTO_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "speech",
        ("致辞", "讲话", "发言", "演讲", "寄语", "致辞稿", "开幕词", "闭幕词"),
    ),
    (
        "celebration",
        (
            "喜讯", "获奖", "荣获", "入选", "获批", "立项", "中标", "夺冠", "冠军",
            "一等奖", "特等奖", "金奖", "榜单", "排名", "晋升", "突破",
        ),
    ),
)


def style_ids() -> list[str]:
    """可显式指定的文体 id（不含 auto）。"""
    return list(STYLES)


def resolve_style(style: str | None, topic: str) -> dict:
    """把请求里的 style 归一成模板。

    显式指定优先；auto 或未知值按选题关键词判定，判不出来落新闻——
    新闻是最通用的骨架，写偏了也比空着强，前端仍可手动切。
    """
    key = (style or "auto").strip().lower()
    if key in STYLES:
        return STYLES[key]
    if key != "auto":
        # 未知值不报错：前端版本不一致时按 auto 处理，避免整个请求 422
        key = "auto"
    for sid, hints in _AUTO_HINTS:
        if any(h in topic for h in hints):
            return STYLES[sid]
    return STYLES[DEFAULT_STYLE]


def style_block(spec: dict) -> str:
    """模板 → 注入 system prompt 的文体约束段。"""
    lines = [
        f"【文体】{spec['name']}——{spec['summary']}",
        f"标题要求：{spec['titleRule']}",
        f"导语要求：{spec['leadHint']}",
        "结构要求（sections 按此顺序组织，每节一个 heading）：",
    ]
    for i, item in enumerate(spec["structure"], 1):
        lines.append(f"  {i}. {item}")
    lines.append(
        "小节 heading 必须是文章自己的小标题（如「共话在地国际化」「数字里的科研实力」），"
        "不要照抄上面的结构项名称，也不要带「现场与主题：」这类分类前缀。"
    )
    lines.append(f"语气：{spec['tone']}")
    lines.append(f"篇幅：{spec['length']}")
    lines.append(f"避免：{spec['avoid']}")
    lines.append("素材支撑不足的环节写「（素材不足，待补充）」，不要为了凑结构编内容。")
    return "\n".join(lines)


def style_meta(spec: dict, requested: str | None) -> dict:
    """回给前端的文体信息：实际用了哪套、是否自动判定。"""
    return {
        "id": spec["id"],
        "name": spec["name"],
        "auto": (requested or "auto").strip().lower() not in STYLES,
    }
