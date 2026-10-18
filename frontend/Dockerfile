# ManualChat frontend — Next.js dev server with hot reload.
# Source is bind-mounted at run time; node_modules is preserved via an
# anonymous volume in docker-compose.yml.

FROM node:20-slim

WORKDIR /app

# Install dependencies first (layer-cached), then the source.
COPY package.json package-lock.json ./
# Persist npm's download cache across builds so a changed lockfile re-installs
# from cached tarballs instead of fetching them again.
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]