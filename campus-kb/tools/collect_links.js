/**
 * 微信公众号「已发表内容」全量链接采集（浏览器控制台脚本）
 *
 * 为什么不爬页面 DOM：后台列表是接口异步渲染的，DOM 结构随版本变动；
 * 直接在页面里 fetch 同源接口，登录态由浏览器自动携带，也不用把 cookie 交给任何外部程序。
 *
 * 用法：
 *   1. 浏览器打开公众号后台「内容与互动 → 已发表」
 *   2. F12 → Console（Chrome 首次需手动输入 allow pasting 回车）
 *   3. 粘贴本文件全部内容，回车
 *   4. 等它翻完页，会自动下载 urls.txt（一行一个链接），并打印带标题日期的表格
 *   5. 把 urls.txt 交给 fetch_wechat.py：python tools/fetch_wechat.py --ocr --urls urls.txt
 *
 * 只对你自己的号使用：脚本调的是当前登录账号的已发表列表。
 */

var PAGE_SIZE = 20;
var DELAY_MS = 700;
var MAX_PAGES = 500;

function pad2(n) {
  return String(n).padStart(2, '0');
}

function toDate(ts) {
  if (!ts) return '';
  var n = typeof ts === 'number' ? ts : parseInt(String(ts), 10);
  if (!n || isNaN(n)) return '';
  var d = new Date(n * 1000);
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
}

/** 只保留真正的文章页，过滤视频号 / 小程序 / 空链接 */
function isArticleLink(url) {
  return typeof url === 'string' && url.indexOf('mp.weixin.qq.com/s') !== -1;
}

function normalizeLink(url) {
  return url.replace(/^http:\/\//, 'https://');
}

/** 解析「已发表」接口（/cgi-bin/appmsgpublish）的一页 */
function parsePublished(json) {
  var pp = (json && json.publish_page) || {};
  var articles = [];
  var list = pp.publish_list || [];
  for (var i = 0; i < list.length; i++) {
    var info = list[i] && list[i].publish_info;
    if (typeof info === 'string') {
      try {
        info = JSON.parse(info);
      } catch (e) {
        continue;
      }
    }
    var sent = (info && (info.sent_list || info.appmsgex)) || [];
    for (var j = 0; j < sent.length; j++) {
      var a = sent[j];
      if (!a || a.is_deleted || !isArticleLink(a.link)) continue;
      articles.push({
        title: String(a.title || '').trim(),
        url: normalizeLink(a.link),
        date: toDate(a.create_time),
        digest: a.digest || '',
      });
    }
  }
  return {
    articles: articles,
    total: typeof pp.total_count === 'number' ? pp.total_count : null,
  };
}

/** 解析旧版图文素材接口（/cgi-bin/appmsg）的一页，作兜底 */
function parseLegacy(json) {
  var list = (json && json.app_msg_list) || [];
  var articles = [];
  for (var i = 0; i < list.length; i++) {
    var a = list[i];
    if (!a || a.is_deleted || !isArticleLink(a.link)) continue;
    articles.push({
      title: String(a.title || '').trim(),
      url: normalizeLink(a.link),
      date: toDate(a.create_time),
      digest: a.digest || '',
    });
  }
  return {
    articles: articles,
    total: json && typeof json.app_msg_cnt === 'number' ? json.app_msg_cnt : null,
  };
}

function getToken() {
  var fromUrl = new URLSearchParams(location.search).get('token');
  if (fromUrl) return fromUrl;
  try {
    if (window.wx && window.wx.commonData && window.wx.commonData.t) {
      return String(window.wx.commonData.t);
    }
  } catch (e) {
    /* 不同版本后台的挂载位置不同，取不到就走正则 */
  }
  var m = document.documentElement.innerHTML.match(/token['"\s:=]+(\d{6,})/);
  return m ? m[1] : '';
}

function buildUrl(kind, begin, token) {
  var qs;
  if (kind === 'appmsgpublish') {
    qs = new URLSearchParams({
      sub: 'list',
      search_field: 'null',
      begin: String(begin),
      count: String(PAGE_SIZE),
      query: '',
      fakeid: '',
      type: '101_1',
      free_publish_type: '1',
      sub_action: 'list_ex',
      token: token,
      lang: 'zh_CN',
      f: 'json',
      ajax: '1',
    });
  } else {
    qs = new URLSearchParams({
      action: 'list_ex',
      begin: String(begin),
      count: String(PAGE_SIZE),
      fakeid: '',
      type: '9',
      query: '',
      token: token,
      lang: 'zh_CN',
      f: 'json',
      ajax: '1',
    });
  }
  return '/cgi-bin/' + kind + '?' + qs.toString();
}

function sleep(ms) {
  return new Promise(function (r) {
    setTimeout(r, ms);
  });
}

async function fetchJson(kind, begin, token) {
  var resp = await fetch(buildUrl(kind, begin, token), { credentials: 'include' });
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  var text = await resp.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error('返回的不是 JSON（登录态可能已失效）：' + text.slice(0, 100));
  }
}

function download(filename, content) {
  var blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function () {
    URL.revokeObjectURL(a.href);
  }, 2000);
}

async function run() {
  var token = getToken();
  if (!token) {
    console.error(
      '[采集] 拿不到 token。请确认当前页面是公众号后台（地址栏里应含 token=xxxxxxxx），再重试。',
    );
    return;
  }
  console.log('[采集] token 已取到，开始翻页…');

  // 两个接口都试一遍首页，用能返回数据且 ret=0 的那个
  var kind = null;
  for (var k of ['appmsgpublish', 'appmsg']) {
    try {
      var probe = await fetchJson(k, 0, token);
      var ret = probe && probe.base_resp ? probe.base_resp.ret : 0;
      if (ret === 0 && (probe.publish_page || probe.app_msg_list)) {
        kind = k;
        console.log('[采集] 使用接口 ' + k);
        break;
      }
      console.warn('[采集] 接口 ' + k + ' 不可用（ret=' + ret + '）');
    } catch (e) {
      console.warn('[采集] 接口 ' + k + ' 探测失败：' + e.message);
    }
  }
  if (!kind) {
    console.error('[采集] 两个接口都没通。多半是登录态过期，刷新页面重新登录后台再试。');
    return;
  }

  var parser = kind === 'appmsgpublish' ? parsePublished : parseLegacy;
  var seen = new Map();
  var total = null;

  for (var page = 0; page < MAX_PAGES; page++) {
    var begin = page * PAGE_SIZE;
    var json;
    try {
      json = await fetchJson(kind, begin, token);
    } catch (e) {
      console.error('[采集] 第 ' + (page + 1) + ' 页失败：' + e.message);
      break;
    }
    var base = json && json.base_resp;
    if (base && base.ret !== 0) {
      console.error('[采集] 接口报错 ret=' + base.ret + '，停止。已采到 ' + seen.size + ' 篇。');
      break;
    }

    var parsed = parser(json);
    if (typeof parsed.total === 'number') total = parsed.total;
    for (var i = 0; i < parsed.articles.length; i++) {
      var a = parsed.articles[i];
      if (!seen.has(a.url)) seen.set(a.url, a);
    }

    var shown = seen.size + ' 篇';
    console.log(
      '[采集] 第 ' + (page + 1) + ' 页：新增 ' + parsed.articles.length + '，累计 ' + shown +
        (total ? ' / 约 ' + total : ''),
    );

    if (parsed.articles.length === 0) break;
    if (total && begin + PAGE_SIZE >= total) break;
    await sleep(DELAY_MS);
  }

  var rows = Array.from(seen.values()).sort(function (a, b) {
    return String(b.date).localeCompare(String(a.date));
  });

  if (!rows.length) {
    console.warn('[采集] 没采到任何链接。若后台确实有文章，可能是接口改版，需要重新适配。');
    return;
  }

  console.table(rows.slice(0, 30));
  console.log('[采集] 共 ' + rows.length + ' 篇（前 30 条见上表）');

  var lines = ['# 微信公众号已发表文章链接（采集于 ' + new Date().toLocaleString() + '）'];
  for (var r = 0; r < rows.length; r++) lines.push(rows[r].url);
  download('urls.txt', lines.join('\n') + '\n');

  var meta = rows.map(function (x) {
    return { title: x.title, url: x.url, date: x.date };
  });
  download('articles.json', JSON.stringify(meta, null, 2));

  console.log('[采集] 已下载 urls.txt 与 articles.json。');
  console.log(
    '[采集] 下一步：python tools/fetch_wechat.py --ocr --urls urls.txt',
  );
}

var __wxCollect = {
  parsePublished: parsePublished,
  parseLegacy: parseLegacy,
  toDate: toDate,
  isArticleLink: isArticleLink,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = __wxCollect;
}
if (typeof window !== 'undefined' && typeof document !== 'undefined' && typeof fetch === 'function') {
  run();
}
