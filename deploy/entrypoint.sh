#!/bin/sh
# nginx 官方镜像会自动执行 /docker-entrypoint.d/*.sh。
# 密码只在容器启动时从环境变量写入临时文件，不进镜像、不进仓库。
set -eu

if [ -z "${CAMPUS_BASIC_USER:-}" ] || [ -z "${CAMPUS_BASIC_PASSWORD:-}" ]; then
  echo "[campus] 未设置 CAMPUS_BASIC_USER / CAMPUS_BASIC_PASSWORD，拒绝以无鉴权状态启动" >&2
  exit 1
fi

htpasswd -bBc /etc/nginx/.htpasswd "$CAMPUS_BASIC_USER" "$CAMPUS_BASIC_PASSWORD"
# nginx worker 以 nginx 用户运行，需能读密码文件
chown root:nginx /etc/nginx/.htpasswd
chmod 640 /etc/nginx/.htpasswd
echo "[campus] Basic Auth 已启用，用户：$CAMPUS_BASIC_USER"

# 生产模式：按证书是否存在选择 HTTP 引导配置或 HTTPS 配置。
# 证书未就绪时先跑 HTTP（保留 ACME webroot），申请完重启 web 即自动切换。
if [ "${CAMPUS_TLS_MODE:-off}" = "on" ]; then
  domain="${CAMPUS_DOMAIN:-}"
  if [ -z "$domain" ]; then
    echo "[campus] TLS 模式必须设置 CAMPUS_DOMAIN" >&2
    exit 1
  fi

  hsts=""
  if [ -f "/etc/letsencrypt/live/$domain/fullchain.pem" ]; then
    sed "s|__DOMAIN__|$domain|g" /etc/nginx/nginx-tls.template > /etc/nginx/conf.d/default.conf
    hsts='add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;'
    echo "[campus] HTTPS 已启用：$domain"
  else
    sed "s|__DOMAIN__|$domain|g" /etc/nginx/nginx-bootstrap.template > /etc/nginx/conf.d/default.conf
    echo "[campus] 证书未就绪，以 HTTP 引导模式运行（ACME 校验可用）：$domain"
  fi

  # nginx 的 add_header 在 location 级不继承 server 级，按模式渲染避免 HSTS 被覆盖
  sed "s|__HSTS__|$hsts|g" /etc/nginx/locations.conf > /etc/nginx/locations.rendered

  # certbot 每 12h 检查续期，nginx 每 6h 重载一次以加载新证书（幂等）。
  ( while :; do sleep 6h; nginx -s reload >/dev/null 2>&1 || true; done ) &
fi
