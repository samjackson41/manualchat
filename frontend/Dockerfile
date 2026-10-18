# ManualChat frontend — Next.js dev server with hot reload.
# Source is bind-mounted at run time; node_modules is preserved via an
# anonymous volume in docker-compose.yml.

FROM node:22-slim

WORKDIR /app

# Install dependencies first (layer-cached), then the source.
COPY package.json package-lock.json ./
# Persist npm's download cache across builds so a changed lockfile re-installs
# from cached tarballs instead of fetching them again.
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY . .

# Run as the image's `node` user (uid 1000), the developer's uid, so files the
# dev server writes into the bind-mounted source stay writable on the host.
RUN chown -R node:node /app

USER node

EXPOSE 3000

CMD ["npm", "run", "dev"]