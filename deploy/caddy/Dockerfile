ARG BASE_IMAGE=fasta-web:denbi
FROM ${BASE_IMAGE}
RUN /usr/sbin/setcap -r /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
