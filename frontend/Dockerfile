# Pinado por digest — ver backend/Dockerfile e .github/dependabot.yml.
# node 24 (LTS, v24.19.0) alinhado com o node-version do CI; o node 20
# anterior (v20.20.2) atendia o requisito do vite 8 (^20.19), mas está
# EOL desde abr/2026 — e o upgrade do Dependabot para 26 divergiria do CI.
FROM node:26-slim@sha256:c0753125a3789977aefe869cbebccf70e3cfd7ea84ca48547458f02e4f1d7146
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN chown -R node:node /app
USER node
EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
