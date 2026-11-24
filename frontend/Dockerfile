FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG PILOT_API_BASE_URL=http://127.0.0.1:18097
ARG PUBLIC_JOBS_API_BASE_URL=http://127.0.0.1:18097
ARG APP_URL=http://127.0.0.1:3000
ENV PILOT_API_BASE_URL=$PILOT_API_BASE_URL
ENV PUBLIC_JOBS_API_BASE_URL=$PUBLIC_JOBS_API_BASE_URL
ENV APP_URL=$APP_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 1001 nodejs && adduser -u 1001 -G nodejs -D nextjs
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]