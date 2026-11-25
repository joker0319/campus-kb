# 前端：node 构建静态产物，nginx 托管并反代 /api（含 SSE）。
FROM node:22-alpine AS build

WORKDIR /app
COPY campus-portal/web/package.json campus-portal/web/package-lock.json ./
RUN npm ci
COPY campus-portal/web/ ./
RUN npm run build

FROM nginx:1.27-alpine

# htpasswd 由启动脚本按环境变量生成；nginx 不内置 apache2-utils
RUN apk add --no-cache apache2-utils

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/api_proxy.conf /etc/nginx/api_proxy.conf
COPY deploy/entrypoint.sh /docker-entrypoint.d/20-campus-auth.sh
RUN chmod +x /docker-entrypoint.d/20-campus-auth.sh

COPY --from=build /app/dist/ /usr/share/nginx/html/

EXPOSE 80
