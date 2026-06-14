# Noscia web (Vite dev server) — dev container for `docker compose up`.
# Build context is the REPO ROOT: this is a pnpm workspace, so the lockfile and
# workspace manifest live at the root, not in web/. Source is bind-mounted at
# runtime (with node_modules kept in an anonymous volume) so HMR works like
# `pnpm dev` does on the host.
# syntax=docker/dockerfile:1

FROM node:24-slim

RUN corepack enable && corepack prepare pnpm@11.5.1 --activate
WORKDIR /repo

# Install deps from the workspace lockfile (cached unless manifests change).
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY web/package.json web/package.json
RUN pnpm install --frozen-lockfile

# App source (overlaid by the bind-mount at runtime).
COPY web web

WORKDIR /repo/web
EXPOSE 5180
CMD ["pnpm", "dev", "--host"]
