# RiskControl Analyst — web application (static build served by nginx)
# Build from the repository root:  docker build -f apps/web/Dockerfile .
FROM node:22-alpine AS build

WORKDIR /app

RUN corepack disable || true

COPY apps/web/package.json apps/web/package-lock.json* /app/
RUN npm install --no-fund --no-audit

COPY apps/web /app
# The browser talks to this origin only; nginx proxies /api to the API service,
# so no absolute API URL is baked into the bundle.
RUN npm run build

FROM nginx:1.27-alpine

# Templates in /etc/nginx/templates are rendered with envsubst at start-up.
COPY apps/web/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

ENV RCA_API_UPSTREAM=http://api:8000
EXPOSE 80
