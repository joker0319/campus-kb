/**
 * collect_links.js 的解析测试（node 内置 test runner，零依赖）
 * 运行：node --test tools/collect_links.test.js
 */

const test = require('node:test');
const assert = require('node:assert');
const { parsePublished, parseLegacy, toDate, isArticleLink } = require('./collect_links.js');

function sentItem(over) {
  return Object.assign(
    {
      appmsgid: 1,
      itemidx: 1,
      title: '标题',
      link: 'https://mp.weixin.qq.com/s/abc',
      create_time: 1619020800,
      digest: '摘要',
    },
    over,
  );
}

test('多图文一条消息展开成多篇', () => {
  const json = {
    publish_page: {
      total_count: 2,
      publish_list: [
        {
          publish_info: JSON.stringify({
            sent_list: [sentItem({}), sentItem({ itemidx: 2, link: 'https://mp.weixin.qq.com/s/def' })],
          }),
        },
      ],
    },
  };
  const r = parsePublished(json);
  assert.strictEqual(r.total, 2);
  assert.strictEqual(r.articles.length, 2);
});

test('publish_info 已是对象时也能解析', () => {
  const json = {
    publish_page: {
      publish_list: [{ publish_info: { appmsgex: [sentItem({ title: '对象形式' })] } }],
    },
  };
  const r = parsePublished(json);
  assert.strictEqual(r.articles.length, 1);
  assert.strictEqual(r.articles[0].title, '对象形式');
});

test('过滤已删除文章', () => {
  const json = {
    publish_page: {
      publish_list: [{ publish_info: JSON.stringify({ sent_list: [sentItem({ is_deleted: true })] }) }],
    },
  };
  assert.strictEqual(parsePublished(json).articles.length, 0);
});

test('过滤非文章链接（视频号、小程序）', () => {
  const json = {
    publish_page: {
      publish_list: [
        {
          publish_info: JSON.stringify({
            sent_list: [
              sentItem({ link: 'https://channels.weixin.qq.com/x' }),
              sentItem({ link: '' }),
              sentItem({ link: 'https://mp.weixin.qq.com/s/keep' }),
            ],
          }),
        },
      ],
    },
  };
  const r = parsePublished(json);
  assert.strictEqual(r.articles.length, 1);
  assert.strictEqual(r.articles[0].url, 'https://mp.weixin.qq.com/s/keep');
});

test('http 链接升级为 https', () => {
  const json = {
    publish_page: {
      publish_list: [
        {
          publish_info: JSON.stringify({
            sent_list: [sentItem({ link: 'http://mp.weixin.qq.com/s?__biz=A&mid=1&idx=1&sn=b' })],
          }),
        },
      ],
    },
  };
  assert.ok(parsePublished(json).articles[0].url.startsWith('https://'));
});

test('publish_info 是坏 JSON 时跳过而不是抛错', () => {
  const json = { publish_page: { publish_list: [{ publish_info: '{不是json' }] } };
  assert.strictEqual(parsePublished(json).articles.length, 0);
});

test('旧版接口兜底解析', () => {
  const json = {
    app_msg_cnt: 1,
    app_msg_list: [
      { title: '旧接口', link: 'https://mp.weixin.qq.com/s/legacy', create_time: 1700000000 },
    ],
  };
  const r = parseLegacy(json);
  assert.strictEqual(r.total, 1);
  assert.strictEqual(r.articles[0].title, '旧接口');
});

test('空响应不崩', () => {
  assert.deepStrictEqual(parsePublished({}).articles, []);
  assert.deepStrictEqual(parseLegacy(null).articles, []);
});

test('create_time 转成 YYYY-MM-DD', () => {
  assert.match(toDate(1619020800), /^\d{4}-\d{2}-\d{2}$/);
  assert.strictEqual(toDate(0), '');
  assert.strictEqual(toDate(undefined), '');
});

test('isArticleLink 只认文章页', () => {
  assert.ok(isArticleLink('https://mp.weixin.qq.com/s/abc'));
  assert.ok(isArticleLink('https://mp.weixin.qq.com/s?__biz=A'));
  assert.ok(!isArticleLink('https://mp.weixin.qq.com/cgi-bin/home'));
  assert.ok(!isArticleLink(null));
});
