#!/usr/bin/env python3
"""把自有微信公众号文章抓成 corpus 可检索的纯文本。

适用边界：只处理自己运营的公众号。内容是自己的，抓取、复用、入库都不涉及
他人权利。对外部账号的文章，本工具不适用。

为什么不直接存 HTML：公众号正文样式全部内联散落在上百层 <section> 上，
拿到手是坨不可复用的 HTML，且图片带 referer 防盗链。语料只需要干净的文字
和可溯源的元数据，所以这里做三件事：

1. 从 #js_content 提取段落文本，按块级元素切段；
2. 图片替换成 [图N] 占位并单独下载到本地（可关）；
3. 元数据（标题/公众号/发布时间/原文链接）写进 wechat-sources.json。

输出位置对齐 search.py 的扫描约定（corpus/text/*.txt，glob 直接可见），
无需改动检索代码。

用法：
    python tools/fetch_wechat.py https://mp.weixin.qq.com/s/xxxx
    python tools/fetch_wechat.py --urls urls.txt        # 一行一个链接
    python tools/fetch_wechat.py URL --no-images        # 不下载图片
    python tools/fetch_wechat.py URL --force            # 允许覆盖已抓过的
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx

KB_ROOT = Path(__file__).resolve().parent.parent
CORPUS = KB_ROOT / "corpus"
TEXT_DIR = CORPUS / "text"
IMAGE_DIR = CORPUS / "images"
SOURCES = CORPUS / "wechat-sources.json"
OCR_BIN = Path(__file__).resolve().parent / "bin" / "ocr"

# 图片型推文判定：正文文字少、图片多，说明文字被做进了图片里。
# 这类推文不 OCR 就入库，等于往语料库里塞空壳——检索时一个字都命中不了。
IMAGE_ONLY_CHARS = 400
IMAGE_ONLY_MIN_IMAGES = 4

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
IMAGE_HEADERS = {**HEADERS, "Referer": "https://mp.weixin.qq.com/"}

# 块级标签：遇到就断段。公众号正文的段落靠 <p> 和 <section> 堆出来。
BLOCK_TAGS = {
    "p", "div", "section", "br", "li", "ul", "ol", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "tr", "figure", "figcaption", "hr",
}

# 正文里的模板噪音：关注引导、二维码提示。只在短段落上生效，避免误杀真内容。
NOISE = [
    re.compile(r"^点击(上方)?(蓝字|标题).{0,12}关注"),
    re.compile(r"^(长按|扫描|扫一扫).{0,10}二维码"),
    re.compile(r"^微信号[:：]\s*\S+$"),
    re.compile(r"^[（(]?点击(查看|阅读)原文[)）]?$"),
]
NOISE_MAX_LEN = 40


def clean_text(raw: str) -> str:
    """把一段原始文本压成一行：去零宽字符、不间断空格、多余空白。"""
    text = raw.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t\r\n]+", " ", text)
    return text.strip()


def is_noise(text: str) -> bool:
    if len(text) > NOISE_MAX_LEN:
        return False
    return any(p.search(text) for p in NOISE)


class BodyParser(HTMLParser):
    """从 #js_content 里抽段落和图片。

    用深度计数判断何时离开正文容器——非贪婪正则会在一堆嵌套 div 上提前截断，
    所以老老实实数开闭标签。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0          # 正文容器内的 div 嵌套深度；0 表示还没进去
        self._skip = 0           # script/style 内部文本
        self._buf: list[str] = []
        self.paragraphs: list[str] = []
        self.images: list[str] = []
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrib = {k: (v or "") for k, v in attrs}

        if tag == "div" and attrib.get("id") == "js_content":
            self._depth = 1
            self.found = True
            return
        if self._depth == 0:
            return

        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag == "div":
            self._depth += 1

        if tag == "img":
            src = attrib.get("data-src") or attrib.get("src")
            if src.startswith("http"):
                self._flush()
                self.images.append(src)
                self.paragraphs.append(f"[图{len(self.images)}]")
            return

        if tag in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self._depth == 0:
            return
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self._flush()
                return
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._depth == 0 or self._skip:
            return
        self._buf.append(data)

    def _flush(self) -> None:
        text = clean_text("".join(self._buf))
        self._buf.clear()
        if text and not is_noise(text):
            self.paragraphs.append(text)

    def result(self) -> list[str]:
        self._flush()
        return self.paragraphs


def _meta(page: str, pattern: str) -> str:
    m = re.search(pattern, page, re.S)
    return htmllib.unescape(m.group(1)).strip() if m else ""


def parse_meta(page: str) -> dict[str, str]:
    """标题/公众号/发布时间。公众号页面的这几处结构多年没变，正则足够稳。"""
    title = _meta(page, r'<meta\s+property="og:title"\s+content="([^"]*)"')
    if not title:
        title = _meta(page, r"var\s+msg_title\s*=\s*'([^']*)'")

    site = _meta(page, r'<meta\s+property="og:site_name"\s+content="([^"]*)"')
    if not site:
        site = _meta(page, r'id="js_name"[^>]*>\s*([^<]+?)\s*<')

    published = _meta(page, r'id="publish_time"[^>]*>\s*([^<]+?)\s*<')
    if not published:
        ts = _meta(page, r"var\s+ct\s*=\s*\"(\d{9,11})\"")
        if ts.isdigit():
            published = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone().strftime(
                "%Y-%m-%d"
            )

    return {"title": title, "site": site, "published": published}


def safe_filename(title: str, published: str) -> str:
    """对齐现有语料命名：标题 + 日期后缀，去掉文件系统非法字符。"""
    stem = re.sub(r'[\\/:*?"<>|]', "", title)
    stem = re.sub(r"\s+", "", stem)[:40] or "untitled"
    stamp = re.sub(r"\D", "", published)[:8] or datetime.now().strftime("%Y%m%d")
    return f"{stem}_{stamp}_WX.txt"


def render(title: str, paragraphs: list[str]) -> str:
    """标题 + 空行 + 段落，段间单换行——和 corpus/text 里现有 txt 一致。"""
    body = "\n".join(paragraphs)
    return f"{title}\n\n{body}\n"


def load_sources() -> list[dict[str, str]]:
    if not SOURCES.exists():
        return []
    try:
        data = json.loads(SOURCES.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data.get("articles", [])


def save_sources(articles: list[dict[str, str]]) -> None:
    SOURCES.parent.mkdir(parents=True, exist_ok=True)
    SOURCES.write_text(
        json.dumps({"articles": articles}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def download_images(
    client: httpx.Client, urls: list[str], folder: Path
) -> tuple[int, int]:
    """图片单独落盘：公众号 CDN 带 referer 校验，外站直链会全部裂开。"""
    if not urls:
        return 0, 0
    folder.mkdir(parents=True, exist_ok=True)
    ok = failed = 0
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
               "image/webp": ".webp", "image/bmp": ".bmp"}
    for idx, url in enumerate(urls, 1):
        # 已经下过就不再重复拉：长图推文动辄 20MB，批量重跑时省得住
        cached = list(folder.glob(f"图{idx}.*"))
        if cached:
            ok += 1
            continue
        try:
            resp = client.get(url, headers=IMAGE_HEADERS, timeout=30)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").split(";")[0].strip()
            ext = ext_map.get(ctype, ".jpg")
            (folder / f"图{idx}{ext}").write_bytes(resp.content)
            ok += 1
        except (httpx.HTTPError, OSError) as exc:
            print(f"    ! 图{idx} 下载失败：{exc}", file=sys.stderr)
            failed += 1
    return ok, failed


def strip_decor(text: str) -> str:
    """去掉 OCR 从设计稿里带出来的装饰符号（项目符号、分隔斜杠、引导线）。"""
    return text.strip(" \u3000•·/|\\-_*#—－~`'\"()（）【】")


# OCR 会把设计稿上的日历、页码、纯符号装饰当成文字。这类短碎片对检索是纯噪音。
OCR_NOISE = [
    re.compile(r"^(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\.?$", re.I),
    re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\.?$", re.I),
    re.compile(r"^[◎○●◇◆□■▲△※※＊*·•\-—~_=+]{1,4}[\d:：]{0,2}$"),
]

# 公众号推文里的信息卡字段（地点/时间/预约方式…）。这些行常不留句号，
# 若放任累加会拼成几百字的巨段，检索命中后片段定位不准——Agent 会因此
# 漏掉段落开头的关键信息。所以遇到新字段就断段。
FIELD_START = re.compile(
    r"^[^，。、；：！？“”]{0,6}"
    r"(地点|地址|位置|时间|开放时间|咨询时间|预约方式|预约|报名|对象|费用|"
    r"电话|热线|联系方式|主办单位|主办|承办|协办|来源|编辑|责编|审核|"
    r"摄影|文字|排版|设计|出品|监制)[:：]"
)

# 单段上限：超过就强制断开，避免出现检索片段装不下的超长段。
MAX_PARA_CHARS = 150


def lines_to_paragraphs(lines: list[str]) -> list[str]:
    """把 OCR 的逐行输出还原成段落。

    OCR 是按视觉行返回的，一句中文常被图片排版折成两三行，所以不能一行一段。
    策略：攒行直到句末标点；短行且不以续接标点结尾的，当小标题独立成段。
    """
    paras: list[str] = []
    buf = ""
    for raw in lines:
        line = strip_decor(clean_text(raw))
        if not line or len(line) <= 2:
            continue
        # 纯数字/日期装饰（日历、页码、序号栏）
        if re.fullmatch(r"[\d\s.．、%+\-]{1,6}", line):
            continue
        if any(p.match(line) for p in OCR_NOISE):
            continue
        # 信息卡新字段（地点：/开放时间：…）：先结掉上一段，别让它们黏成巨段
        if FIELD_START.match(line) and buf:
            paras.append(buf)
            buf = ""
        # 短行且既不是半句、也不是完整句子，才当小标题。
        # 漏掉「完整句子」这个条件，会把「于是拖延，拖延又加重焦虑。」拆成标题。
        if (
            len(line) <= 14
            and not line.endswith(("，", "、", "：", "—", "…"))
            and not line.endswith(("。", "！", "？", "；"))
        ):
            if buf:
                paras.append(buf)
                buf = ""
            paras.append(line)
            continue
        buf += line
        if line.endswith(("。", "！", "？", "；")):
            paras.append(buf)
            buf = ""
        elif len(buf) >= MAX_PARA_CHARS:
            # 超长单行（OCR 把整块文字识别成一行）硬切，避免片段装不下
            while len(buf) > MAX_PARA_CHARS:
                paras.append(buf[:MAX_PARA_CHARS])
                buf = buf[MAX_PARA_CHARS:]
    if buf:
        paras.append(buf)
    return paras


def ocr_images(folder: Path, expected: int) -> list[str]:
    """调 Vision OCR 识别整篇图片，返回段落。

    走 --stitch 而不是逐张：切片长图的文字常被切在接缝处，逐张识别会缺字。
    """
    if not OCR_BIN.exists():
        raise RuntimeError(
            "OCR 工具未编译。先执行：swiftc -O tools/ocr.swift -o tools/bin/ocr"
        )
    files = [p for p in folder.iterdir() if re.search(r"图\d+", p.stem)]
    files.sort(key=lambda p: int(re.search(r"图(\d+)", p.stem).group(1)))
    if not files:
        raise RuntimeError("没有已下载的图片，无法 OCR")
    if len(files) < expected:
        print(f"    ! 只找到 {len(files)}/{expected} 张图，识别内容可能不完整", file=sys.stderr)

    try:
        proc = subprocess.run(
            [str(OCR_BIN), "--stitch", *map(str, files)],
            capture_output=True, text=True, timeout=600, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("OCR 超时（图片过多或过大）") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"OCR 失败：{proc.stderr.strip()[:200]}")

    lines = [
        line for line in proc.stdout.splitlines()
        if line.strip() and not line.startswith("###GROUP:")
    ]
    return lines_to_paragraphs(lines)


def fetch_one(
    client: httpx.Client,
    url: str,
    *,
    with_images: bool,
    with_ocr: bool,
    force: bool,
    known: list[dict[str, str]],
    drop_images: bool = False,
) -> dict[str, str] | None:
    existing = next((a for a in known if a.get("url") == url), None)
    if existing and not force:
        print(f"  跳过（已抓过）：{existing.get('title', url)[:30]}")
        return None

    resp = client.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    page = resp.text

    if "环境异常" in page or "去验证" in page:
        raise RuntimeError("被微信风控拦截，稍后重试或换网络环境")

    parser = BodyParser()
    parser.feed(page)
    if not parser.found:
        raise RuntimeError("页面里没找到 #js_content，可能不是文章页或已被删除")

    paragraphs = parser.result()
    html_chars = sum(len(p) for p in paragraphs if not p.startswith("[图"))
    image_only = (
        html_chars < IMAGE_ONLY_CHARS and len(parser.images) >= IMAGE_ONLY_MIN_IMAGES
    )

    # 图片型推文如果没有 OCR 就入库，等于往语料库塞空壳：检索时一个字都命中不了。
    # 所以这里直接拒绝，而不是写一个只有 [图N] 占位的文件。
    if image_only and not with_ocr:
        raise RuntimeError(
            f"图片型推文（正文仅 {html_chars} 字、{len(parser.images)} 张图），文字做在图片里了。"
            "加 --ocr 从图片识别文字后再入库"
        )

    meta = parse_meta(page)
    title = meta["title"] or (paragraphs[0][:40] if paragraphs else "untitled")
    filename = safe_filename(title, meta["published"])
    folder = IMAGE_DIR / Path(filename).stem

    if parser.images and (with_images or with_ocr):
        ok, failed = download_images(client, parser.images, folder)
        print(
            f"  图片 {ok} 张已存 images/{folder.name}/"
            + (f"，{failed} 张失败" if failed else "")
        )

    if image_only:
        print("  图片型推文，开始 OCR…")
        paragraphs = ocr_images(folder, len(parser.images))

    if not paragraphs:
        raise RuntimeError("正文为空，未写入文件")

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    (TEXT_DIR / filename).write_text(render(title, paragraphs), encoding="utf-8")

    chars = sum(len(p) for p in paragraphs)
    origin = "OCR" if image_only else "HTML"
    print(f"  正文 {len(paragraphs)} 段 / {chars} 字（来源 {origin}）→ text/{filename}")

    # 全量入库时图片只是中间产物：文字已经进了 txt，留着每篇要多占十几 MB。
    if drop_images and folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
        print(f"  已清理 images/{folder.name}/（文本已落盘）")

    return {
        "url": url,
        "title": title,
        "site": meta["site"],
        "published": meta["published"],
        "file": filename,
        "chars": str(chars),
        "images": str(len(parser.images)),
        "ocr": "1" if image_only else "0",
        "fetched": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
    }


def collect_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.url or [])
    if args.urls:
        path = Path(args.urls)
        if not path.exists():
            sys.exit(f"链接清单不存在：{path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    # 去重但保序
    seen: set[str] = set()
    unique = [u for u in urls if not (u in seen or seen.add(u))]
    if not unique:
        sys.exit("没有可抓取的链接。用法见 --help")
    return unique


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="抓取自有公众号文章，转成 corpus/text 可检索的纯文本"
    )
    ap.add_argument("url", nargs="*", help="文章链接，可多个")
    ap.add_argument("--urls", help="链接清单文件，一行一个")
    ap.add_argument("--no-images", action="store_true", help="不下载图片")
    ap.add_argument(
        "--ocr", action="store_true",
        help="对图片型推文用 Vision OCR 提取文字（需先编译 tools/bin/ocr）",
    )
    ap.add_argument("--force", action="store_true", help="覆盖已抓过的同链接")
    ap.add_argument(
        "--drop-images", action="store_true",
        help="文本落盘后删除该篇图片目录（全量入库省磁盘；OCR 已在落盘前完成）",
    )
    ap.add_argument("--interval", type=float, default=1.5, help="多篇之间的间隔秒数")
    args = ap.parse_args(argv)

    if args.ocr and args.no_images:
        ap.error("--ocr 需要图片，不能和 --no-images 同时使用")

    urls = collect_urls(args)
    known = load_sources()
    added: list[dict[str, str]] = []
    failures: list[tuple[str, str]] = []

    with httpx.Client() as client:
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {url}")
            try:
                entry = fetch_one(
                    client, url,
                    with_images=not args.no_images,
                    with_ocr=args.ocr,
                    force=args.force,
                    known=known,
                    drop_images=args.drop_images,
                )
                if entry:
                    added.append(entry)
                    # --force 重抓时替换旧记录，避免同一链接出现两条
                    known = [a for a in known if a.get("url") != entry["url"]]
                    known.append(entry)
                    # 全量抓几百篇时中途中断很常见，逐篇落盘才能保证重跑只补没抓完的
                    save_sources(known)
            except (httpx.HTTPError, RuntimeError, OSError) as exc:
                print(f"  ✗ 失败：{exc}", file=sys.stderr)
                failures.append((url, str(exc)))
            if i < len(urls):
                time.sleep(args.interval)

    if added:
        print(f"\n入库 {len(added)} 篇，元数据见 {SOURCES.relative_to(KB_ROOT)}")
        print("可直接检索：GET /api/search?q=关键词")
    if failures:
        print(f"\n{len(failures)} 篇失败：", file=sys.stderr)
        for url, err in failures:
            print(f"  {url}\n    {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
