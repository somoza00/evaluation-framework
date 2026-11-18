# Pinado por digest — ver backend/Dockerfile e .github/dependabot.yml.
# node 24 (LTS, v24.19.0) é o MESMO major do `node-version` do CI e do CD
# (.github/workflows/ci.yml e cd.yml): o que é validado (`npm ci` + `npm run
# build`) tem de rodar no mesmo runtime que a imagem entrega. O node 20
# anterior (v20.20.2) atendia o requisito do vite 8 (^20.19), mas está EOL
# desde abr/2026.
#
# Isso já divergiu uma vez: o Dependabot subiu a base para `node:26-slim` no
# PR #62 e o merge passou, deixando a IMAGEM em 26 enquanto CI e CD seguiam
# em 24 — build local num Node, build de produção em outro. A regra `ignore`
# em .github/dependabot.yml impede a repetição; ao subir o CI/CD, suba esta
# base junto (e o digest com ela).
FROM node:24-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03
WORKDIR /app
COPY package*.json ./
# `npm ci` (não `npm install`): o package-lock.json está commitado e é o que o
# CI/CD usam (`npm ci` falha se o lock estiver dessincronizado do package.json).
# Com `npm install`, a imagem podia resolver versões diferentes das do CI — ou
# reescrever o lock — e o build passava enquanto o CI quebrava, ou vice-versa.
RUN npm ci
COPY . .
RUN chown -R node:node /app
USER node
EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
