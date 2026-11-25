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
