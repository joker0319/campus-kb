"""公众号抓取工具的解析逻辑测试。

不联网：用构造的 HTML 和 OCR 行验证解析规则，真实抓取靠手工验证。
"""

from tools.fetch_wechat import (
    BodyParser,
    collect_urls,
    extract_links,
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


class TestExtractLinks:
    """从任意粘贴文本抽链接。拿不到后台登录态时，用户只能一篇篇复制，格式很脏。"""

    def test_粘连无分隔的相邻链接都要抽出(self) -> None:
        # 用户真实贴过的形态：两条链接首尾直接相连，中间没有任何分隔符。
        # 曾因整体正则贪婪吞掉下一条的 "https" 而只抽到前两条。
        text = (
            "https://mp.weixin.qq.com/s/AAA111 https://mp.weixin.qq.com/s/BBB222"
            "https://mp.weixin.qq.com/s/CCC333https://mp.weixin.qq.com/s/DDD444"
        )
        assert extract_links(text) == [
            "https://mp.weixin.qq.com/s/AAA111",
            "https://mp.weixin.qq.com/s/BBB222",
            "https://mp.weixin.qq.com/s/CCC333",
            "https://mp.weixin.qq.com/s/DDD444",
        ]

    def test_分享卡片只取链接丢掉标题(self) -> None:
        text = (
            "香港城市大学东莞\n"
            "港城莞获1000万元捐赠设立未来智能中心\n"
            "https://mp.weixin.qq.com/s/WSNtMlJFpM37fbgyUtRTpw"
        )
        assert extract_links(text) == ["https://mp.weixin.qq.com/s/WSNtMlJFpM37fbgyUtRTpw"]

    def test_追踪参数被剥离以便和已入库记录对上(self) -> None:
        text = "https://mp.weixin.qq.com/s/AAA111?scene=1&srcid=1124abc#rd"
        assert extract_links(text) == ["https://mp.weixin.qq.com/s/AAA111"]

    def test_长链保留完整查询参数(self) -> None:
        # 长链的 __biz/mid/idx/sn 是定位文章的唯一凭据，不能像短链那样截断
        text = "http://mp.weixin.qq.com/s?__biz=MzA5&mid=2650&idx=1&sn=abc123"
        got = extract_links(text)
        assert got == ["https://mp.weixin.qq.com/s?__biz=MzA5&mid=2650&idx=1&sn=abc123"]

    def test_链接后紧跟中文时在中文处截断(self) -> None:
        text = "https://mp.weixin.qq.com/s/AAA111这是标题文字"
        assert extract_links(text) == ["https://mp.weixin.qq.com/s/AAA111"]

    def test_全角括号包裹的链接(self) -> None:
        text = "（https://mp.weixin.qq.com/s/AAA111）"
        assert extract_links(text) == ["https://mp.weixin.qq.com/s/AAA111"]

    def test_忽略视频号与外站链接(self) -> None:
        text = "https://channels.weixin.qq.com/xxx https://www.cityu.edu.cn/news"
        assert extract_links(text) == []

    def test_空文本返回空列表(self) -> None:
        assert extract_links("") == []
        assert extract_links("这是一段没有任何链接的文字") == []


class TestCollectUrls:
    """链接来源汇总：命令行参数、清单文件、stdin、累积收件箱。"""

    def _args(self, **kw: object) -> object:
        import argparse

        base: dict[str, object] = {"url": [], "urls": None, "paste": False, "inbox": None}
        base.update(kw)
        return argparse.Namespace(**base)

    def test_同一篇文章的不同参数形态只抓一次(self) -> None:
        args = self._args(
            url=[
                "https://mp.weixin.qq.com/s/AAA111?scene=1",
                "https://mp.weixin.qq.com/s/AAA111#rd",
            ]
        )
        assert collect_urls(args) == ["https://mp.weixin.qq.com/s/AAA111"]

    def test_清单文件里混入标题和注释也能读(self, tmp_path: object) -> None:
        from pathlib import Path

        f = Path(str(tmp_path)) / "urls.txt"
        f.write_text(
            "# 第一批\n港城莞获1000万元捐赠\nhttps://mp.weixin.qq.com/s/AAA111\n",
            encoding="utf-8",
        )
        args = self._args(urls=str(f))
        assert collect_urls(args) == ["https://mp.weixin.qq.com/s/AAA111"]

    def test_不给任何输入时回落到收件箱(self, tmp_path: object) -> None:
        from pathlib import Path

        from tools import fetch_wechat

        inbox = Path(str(tmp_path)) / "inbox.txt"
        inbox.write_text("https://mp.weixin.qq.com/s/AAA111\n", encoding="utf-8")
        old = fetch_wechat.INBOX
        fetch_wechat.INBOX = inbox
        try:
            assert collect_urls(self._args()) == ["https://mp.weixin.qq.com/s/AAA111"]
        finally:
            fetch_wechat.INBOX = old

    def test_文本里没有链接时明确报错(self) -> None:
        import pytest

        with pytest.raises(SystemExit):
            collect_urls(self._args(url=["这不是链接"]))
