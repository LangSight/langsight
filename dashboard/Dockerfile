# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: deps — install node_modules
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production=false

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: builder — build Next.js
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG LANGSIGHT_API_URL=http://localhost:8000
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
ENV LANGSIGHT_API_URL=${LANGSIGHT_API_URL}

RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: runtime — minimal image
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS runtime

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3002
ENV HOSTNAME=0.0.0.0

# Copy only what's needed to run
COPY --from=builder /app/public           ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static     ./.next/static

USER nextjs
EXPOSE 3002

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3002/login || exit 1

CMD ["node", "server.js"]
