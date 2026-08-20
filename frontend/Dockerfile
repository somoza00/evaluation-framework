# Pinado por digest — ver backend/Dockerfile e .github/dependabot.yml.
# node 24 (LTS, v24.19.0) alinhado com o node-version do CI; o node 20
# anterior (v20.20.2) atendia o requisito do vite 8 (^20.19), mas está
# EOL desde abr/2026 — e o upgrade do Dependabot para 26 divergiria do CI.
FROM node:24-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN chown -R node:node /app
USER node
EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
