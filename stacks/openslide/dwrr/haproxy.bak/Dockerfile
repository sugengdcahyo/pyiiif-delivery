FROM haproxy:alpine

USER root
RUN apk add --no-cache lua5.4 lua5.4-socket lua5.4-cjson
USER haproxy

# Copy haproxy.cfg & dwrr.lua
COPY haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg
COPY dwrr.lua /usr/local/etc/haproxy/dwrr.lua
