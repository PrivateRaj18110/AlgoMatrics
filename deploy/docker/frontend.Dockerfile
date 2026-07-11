FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend .
RUN npm run build

# Ops dashboard (served under /ops by the same nginx).
FROM node:22-alpine AS ops-builder
WORKDIR /app
COPY ops/frontend/package.json ops/frontend/package-lock.json* ./
RUN npm ci || npm install
COPY ops/frontend .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
RUN rm /etc/nginx/conf.d/default.conf
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=ops-builder /app/dist /usr/share/nginx/html/ops
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD wget -q -O /dev/null http://localhost:8080/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
