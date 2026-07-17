FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend .
RUN npm run build

# Ops dashboard (served under /ops by the same nginx). Built in LIVE mode by
# default: the SPA calls the ops-api at /ops/api, which serves live AlgoMatrics
# platform data when the ops-api has ALGOMATRICS_* creds (else its own mock).
# Override with --build-arg VITE_USE_MOCK=true to ship the bundled frontend mock.
FROM node:22-alpine AS ops-builder
WORKDIR /app
ARG VITE_API_BASE_URL=/ops/api
ARG VITE_USE_MOCK=false
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_USE_MOCK=$VITE_USE_MOCK
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
