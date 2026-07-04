# WhatsApp Web sidecar runtime
FROM node:20-slim

RUN apt-get update && apt-get install -y \
    chromium \
    fonts-noto-color-emoji \
    fonts-noto-cjk \
    ca-certificates \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

COPY package.json .
RUN npm install

COPY wa_sidecar.js .

VOLUME /app/.wwebjs_auth

EXPOSE 3333

CMD ["node", "wa_sidecar.js"]
