"""公众号抓取工具的解析逻辑测试。

不联网：用构造的 HTML 和 OCR 行验证解析规则，真实抓取靠手工验证。
"""

from tools.fetch_wechat import (
    BodyParser,
    lines_to_paragraphs,
    parse_meta,
    render,
    safe_filename,
    truncate_tail,
)

PAGE = """<html><head>
<meta property="og:title" content="港城大（东莞）举行奠基仪式" />
<meta property="og:site_name" content="香港城市大学东莞" />
</head><body>
<div class="rich_media_area">
  <h1 id="activity-name">港城大（东莞）举行奠基仪式</h1>
  <em id="publish_time" class="rich_media_meta">2021-04-22</em>
  <div class="rich_media_content" id="js_content" style="visibility:hidden">
    <p style="font-size:15px">点击上方蓝字关注我们</p>
    <section style="margin:0"><section style="padding:10px">
      <p style="line-height:1.75">4月22日上午，香港城市大学（东莞）</p>
      <p style="line-height:1.75">在松山湖科学城举行奠基仪式。&nbsp;</p>
      <p><img data-src="https://mmbiz.qpic.cn/mmbiz_jpg/abc/0?wx_fmt=jpeg"
              src="data:image/gif;base64,PLACEHOLDER" /></p>
      <section><strong>于吉红院士</strong>出席并致辞。</section>
      <script>var junk = "不该出现";</script>
      <p>长按识别二维码关注</p>
    </section></section>
  </div>
  <div class="recommend">本段在容器外，不该出现</div>
</div></body></html>"""


class TestBodyParser:
    def test_只提取正文容器内的文字(self) -> None:
        parser = BodyParser()
        parser.feed(PAGE)
        text = "\n".join(parser.result())

        assert parser.found is True
        assert "4月22日上午" in text
        assert "于吉红院士出席并致辞。" in text
        # 容器外的推荐位、script 里的变量都必须排除
        assert "本段在容器外" not in text
        assert "不该出现" not in text

    def test_剔除关注引导等模板噪音(self) -> None:
        parser = BodyParser()
        parser.feed(PAGE)
        text = "\n".join(parser.result())

        assert "点击上方蓝字" not in text
        assert "长按识别二维码" not in text

    def test_图片优先取_data_src_并转为占位符(self) -> None:
        parser = BodyParser()
        parser.feed(PAGE)

        assert parser.images == ["https://mmbiz.qpic.cn/mmbiz_jpg/abc/0?wx_fmt=jpeg"]
        assert "[图1]" in parser.result()

    def test_没有正文容器时标记未找到(self) -> None:
        parser = BodyParser()
        parser.feed("<html><body><div>普通页面</div></body></html>")
        assert parser.found is False

    def test_段落按块级元素切分(self) -> None:
        parser = BodyParser()
        parser.feed(PAGE)
        paras = parser.result()

        assert paras[0] == "4月22日上午，香港城市大学（东莞）"
        assert paras[1] == "在松山湖科学城举行奠基仪式。"


class TestLinesToParagraphs:
    def test_续行合并到句末标点(self) -> None:
        lines = ["学业压力多半来自整体感，", "于是拖延，拖延又加重焦虑。"]
        assert lines_to_paragraphs(lines) == ["学业压力多半来自整体感，于是拖延，拖延又加重焦虑。"]

    def test_短行独立成小标题(self) -> None:
        paras = lines_to_paragraphs(["学习压力", "把任务切成小块。"])
        assert paras == ["学习压力", "把任务切成小块。"]

    def test_剔除日历与页码噪音(self) -> None:
        lines = ["Mon.", "Tue.", "Sun.", "2021", "正文第一句。"]
        assert lines_to_paragraphs(lines) == ["正文第一句。"]

    def test_剔除纯符号装饰(self) -> None:
        assert lines_to_paragraphs(["◎2：", "|", "正文内容在这里。"]) == ["正文内容在这里。"]

    def test_信息卡字段各自成段(self) -> None:
        """地点/开放时间是相邻行，不能黏成一段——否则检索片段会截掉前半截。"""
        lines = [
            "地点：学生公寓4栋1楼：心理成长中心芦苇渡房间",
            "开放时间：个体咨询可约时段以系统显示为准",
            "移动端预约：企业微信工作台学生事务心理服务",
        ]
        paras = lines_to_paragraphs(lines)

        assert len(paras) == 3
        assert paras[0].startswith("地点：")
        assert paras[1].startswith("开放时间：")
        assert paras[2].startswith("移动端预约：")

    def test_超长段强制截断(self) -> None:
        long_line = "这是一句没有句号的很长的中文内容" * 12
        paras = lines_to_paragraphs([long_line])
        assert all(len(p) <= 150 for p in paras)
        assert len(paras) == 2


class TestMeta:
    def test_提取标题公众号与发布时间(self) -> None:
        meta = parse_meta(PAGE)
        assert meta["title"] == "港城大（东莞）举行奠基仪式"
        assert meta["site"] == "香港城市大学东莞"
        assert meta["published"] == "2021-04-22"

    def test_无_publish_time_时回退时间戳(self) -> None:
        page = '<meta property="og:title" content="标题"><script>var ct = "1618992000";</script>'
        meta = parse_meta(page)
        assert meta["published"].startswith("2021-")


class TestFilename:
    def test_去掉文件系统非法字符(self) -> None:
        name = safe_filename('标题/含:非法*字符?"<>|', "2021-04-22")
        assert name == "标题含非法字符_20210422_WX.txt"

    def test_超长标题截断(self) -> None:
        name = safe_filename("长" * 100, "2021-04-22")
        assert len(name) == 40 + len("_20210422_WX.txt")

    def test_无标题时兜底(self) -> None:
        assert safe_filename("", "").startswith("untitled_")


class TestRender:
    def test_输出格式与现有语料一致(self) -> None:
        text = render("标题", ["第一段", "第二段"])
        assert text == "标题\n\n第一段\n第二段\n"


class TestTruncateTail:
    """长图末尾的「推荐阅读」卡片会把别的文章标题 OCR 进来，必须截掉。"""

    def test_推荐阅读之后全部丢弃(self) -> None:
        paras = ["正文第一段。", "正文第二段。", "推荐阅读", "另一篇文章的标题", "点击关注"]
        assert truncate_tail(paras) == ["正文第一段。", "正文第二段。"]

    def test_带装饰符号的标记也能识别(self) -> None:
        paras = ["正文。", "· 往期回顾 ·", "旧文标题"]
        assert truncate_tail(paras) == ["正文。"]

    def test_英文关注引导(self) -> None:
        paras = ["正文。", "Follow us", "二维码"]
        assert truncate_tail(paras) == ["正文。"]

    def test_正文包含推荐阅读四字但不独立成行时不截断(self) -> None:
        paras = ["我们为师生推荐阅读书目，覆盖人文与科技。", "第二段。"]
        assert truncate_tail(paras) == paras

    def test_无标记时原样返回(self) -> None:
        paras = ["第一段。", "第二段。"]
        assert truncate_tail(paras) == paras

    def test_空列表(self) -> None:
        assert truncate_tail([]) == []
