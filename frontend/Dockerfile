# SmartHire AI — frontend
#
# NOT what render.yaml uses. Render serves this as a native Static Site: free,
# CDN-backed, and nothing to keep running. Paying for a container to hand out
# files an edge network would serve better would be the wrong call there.
#
# This exists so the frontend is portable to somewhere without a static-site
# product — a VPS behind nginx, a Kubernetes cluster, a corporate host that
# only takes images. If you deploy on Render, ignore this file.
#
# VITE_API_URL is baked in at BUILD time, not read at runtime. Vite substitutes
# import.meta.env.* into the bundle during the build, so one image cannot be
# promoted from staging to production — each environment needs its own build
# with its own --build-arg. That is a property of Vite, not a choice made here,
# and it is worth knowing before someone tries to reuse a tag.

# ---------- build ----------
FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# ---------- serve ----------
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html

# A single-page app: every route is served by index.html, or a refresh on
# /candidate#history returns 404 from nginx before React ever sees it.
RUN printf '%s\n' \
    'server {' \
    '  listen 80;' \
    '  root /usr/share/nginx/html;' \
    '  index index.html;' \
    '  location / {' \
    '    try_files $uri $uri/ /index.html;' \
    '  }' \
    '}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
