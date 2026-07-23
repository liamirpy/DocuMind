FROM alpine:3.21

RUN apk add --no-cache \
    nginx \
    nginx-mod-stream \
    && mkdir -p /run/nginx

CMD ["nginx", "-g", "daemon off;"]
