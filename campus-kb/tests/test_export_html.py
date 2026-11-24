"""公众号排版 HTML 导出：内联样式、无内部编号、配图占位。"""

from __future__ import annotations

from api import export_html


def _article(**over: object) -> dict:
    base = {
        "title": "2026级新生报到指引",
        "lead": "8月11日起线上报到。",
        "sections": [
            {
                "heading": "线上先报到",
                "paragraphs": [
                    {"text": "新生需在8月11日至19日登录迎新系统。", "cites": ["A1"]},
                    {"text": "（素材不足，待补充）", "cites": []},
                ],
            }
        ],
        "imageSuggestions": [],
    }
    base.update(over)
    return base


class TestLayout:
    def test_renders_title_lead_and_section(self) -> None:
        html = export_html.article_to_html(_article())
        assert "2026级新生报到指引" in html
        assert "8月11日起线上报到。" in html
        assert "线上先报到" in html
        assert "新生需在8月11日至19日登录迎新系统。" in html

    def test_styles_are_inline_only(self) -> None:
        """公众号编辑器会剥掉 class 与 <style>，所以版式必须全写在 style="" 里。"""
        html = export_html.article_to_html(_article())
        assert "<style" not in html
        assert "class=" not in html
        assert 'style="margin:0 0 18px' in html

    def test_drops_internal_citation_numbers(self) -> None:
        html = export_html.article_to_html(_article())
        assert "A1" not in html
        assert "[" not in html

    def test_skips_pending_paragraph_and_whole_empty_section(self) -> None:
        article = _article(
            sections=[
                {"heading": "空节", "paragraphs": [{"text": "（素材不足，待补充）", "cites": []}]},
                {"heading": "有内容", "paragraphs": [{"text": "正文一句。", "cites": []}]},
            ]
        )
        html = export_html.article_to_html(article)
        assert "待补充" not in html
        assert "空节" not in html
        assert "有内容" in html

    def test_escapes_markup_in_text(self) -> None:
        article = _article(sections=[{"heading": "标题", "paragraphs": [{"text": "a<b>&c", "cites": []}]}])
        html = export_html.article_to_html(article)
        assert "a&lt;b&gt;&amp;c" in html
        assert "<b>" not in html

    def test_empty_article_does_not_crash(self) -> None:
        html = export_html.article_to_html({})
        assert html.strip().startswith("<section")
        assert "</section>" in html


class TestFigurePlaceholder:
    def test_figure_block_carries_caption_and_size(self) -> None:
        figs = [
            {
                "sectionIndex": 0,
                "caption": "新生在报到现场排队交谈",
                "width": 1080,
                "height": 720,
            }
        ]
        html = export_html.article_to_html(_article(), figs)
        assert "配图占位" in html
        assert "请替换为对应现场照片" in html
        assert "新生在报到现场排队交谈" in html
        assert "1080×720" in html
        # 只给占位，不嵌真实图片
        assert "<img" not in html

    def test_figure_goes_to_its_own_section(self) -> None:
        article = _article(
            sections=[
                {"heading": "第一节", "paragraphs": [{"text": "甲。", "cites": []}]},
                {"heading": "第二节", "paragraphs": [{"text": "乙。", "cites": []}]},
            ]
        )
        figs = [{"sectionIndex": 1, "caption": "第二节的图", "width": 800, "height": 600}]
        html = export_html.article_to_html(article, figs)
        assert html.index("第二节的图") > html.index("第二节")
        assert html.index("第二节的图") > html.index("乙。")

    def test_unknown_section_index_is_ignored(self) -> None:
        figs = [{"sectionIndex": 9, "caption": "孤图", "width": 800, "height": 600}]
        html = export_html.article_to_html(_article(), figs)
        assert "孤图" not in html
