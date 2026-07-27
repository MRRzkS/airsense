FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines env at build time, so the backend URLs are build args rather
# than runtime configuration.
ARG VITE_API_URL
ARG VITE_SIMULATOR_URL
ENV VITE_API_URL=$VITE_API_URL \
    VITE_SIMULATOR_URL=$VITE_SIMULATOR_URL

RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
