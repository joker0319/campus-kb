#!/bin/sh
# 首次申请 Let's Encrypt 证书，并把 web 从 HTTP 引导模式切到 HTTPS。
#
# 用法（在服务器项目根目录）：
#   ./deploy/init-tls.sh              # 正式证书
#   ./deploy/init-tls.sh --staging    # 先用测试证书验证（不受频率限制）
#   ./deploy/init-tls.sh --force      # 已有证书时强制重签
#
# 前置条件：根目录 .env 已填 CAMPUS_DOMAIN / CAMPUS_TLS_EMAIL，且域名 A 记录已指向服务器。
set -eu

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "[campus] 缺少根目录 .env，请先 cp .env.example .env 并填写" >&2
  exit 1
fi

# 让 .env 中的变量对 compose 与后续判断生效
set -a
. ./.env
set +a

domain="${CAMPUS_DOMAIN:-}"
email="${CAMPUS_TLS_EMAIL:-}"
if [ -z "$domain" ] || [ -z "$email" ]; then
  echo "[campus] 请在 .env 中填写 CAMPUS_DOMAIN 与 CAMPUS_TLS_EMAIL" >&2
  exit 1
fi
case "$domain" in
  https://*|http://*|*/*|*:* )
    echo "[campus] CAMPUS_DOMAIN 只能是裸域名，不能带协议、路径或端口：$domain" >&2
    exit 1
    ;;
esac

extra=""
for arg in "$@"; do
  case "$arg" in
    --staging) extra="$extra --staging" ;;
    --force)   extra="$extra --force-renewal" ;;
    * ) echo "[campus] 未知参数：$arg（支持 --staging / --force）" >&2; exit 1 ;;
  esac
done

compose() {
  docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"
}

# 域名解析预检：有 dig 就查，避免解析未生效时空跑一轮 ACME
if command -v dig >/dev/null 2>&1; then
  resolved="$(dig +short "$domain" A | head -n 1)"
  if [ -z "$resolved" ]; then
    echo "[campus] 域名 $domain 还没有 A 记录，请先把 DNS 指向服务器再执行" >&2
    exit 1
  fi
  echo "[campus] $domain -> $resolved"
fi

# 先以 HTTP 引导模式启动 web，开放 /.well-known/acme-challenge/
echo "[campus] 启动 web（HTTP 引导模式）…"
compose up -d web

# 等 80 端口就绪；返回 404 也说明 nginx 已在服务 ACME 路径
ready=0
i=0
while [ "$i" -lt 30 ]; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1/.well-known/acme-challenge/__ping__" || true)"
  if [ -n "$code" ] && [ "$code" != "000" ]; then
    ready=1
    break
  fi
  i=$((i + 1))
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  echo "[campus] web 的 80 端口未就绪，检查 docker compose logs web" >&2
  exit 1
fi

# 已有证书则跳过申请（除非显式 --force）
if [ -z "$extra" ] && compose run --rm certbot certificates 2>/dev/null | grep -q "Certificate Name: $domain"; then
  echo "[campus] 证书 $domain 已存在，跳过申请（需要重签请加 --force）"
else
  echo "[campus] 申请证书：$domain"
  # compose run 会覆盖 certbot 服务的续期循环 command，直接执行 certonly
  # shellcheck disable=SC2086
  compose run --rm certbot certonly \
    --webroot -w /var/www/certbot \
    -d "$domain" \
    --email "$email" \
    --agree-tos --no-eff-email \
    $extra
fi

# 重启 web：entrypoint 检测到证书后自动渲染 HTTPS 配置
compose up -d --force-recreate web
echo "[campus] 完成。访问 https://$domain/ 验证；证书由 certbot 容器每 12 小时自动续期。"
