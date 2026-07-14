FROM node:22-alpine AS builder

WORKDIR /workspace/apps/web
RUN corepack enable

COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY apps/web ./

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN pnpm build && pnpm prune --prod

FROM node:22-alpine AS runner

ENV NODE_ENV=production

WORKDIR /workspace/apps/web
RUN corepack enable

COPY --from=builder /workspace/apps/web/package.json ./
COPY --from=builder /workspace/apps/web/pnpm-lock.yaml ./
COPY --from=builder /workspace/apps/web/pnpm-workspace.yaml ./
COPY --from=builder /workspace/apps/web/node_modules ./node_modules
COPY --from=builder /workspace/apps/web/.next ./.next

EXPOSE 3000

CMD ["pnpm", "exec", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
