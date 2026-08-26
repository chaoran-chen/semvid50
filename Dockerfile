# Builds the site and serves it with nginx. The DokuWiki import is not part of
# this: src/content/wiki/ and src/assets/ are committed, so the build needs
# nothing but this repository.

FROM node:22-slim AS build
WORKDIR /app

# Pagefind and sharp install a binary for the platform, and Pagefind publishes
# none for musl, which is why this stage is Debian rather than Alpine.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Only used for the absolute URLs in the sitemap.
ARG SITE_URL=https://example.com
RUN SITE_URL="$SITE_URL" npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
