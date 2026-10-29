FROM alpine:3.20

RUN apk add --no-cache curl tzdata

# supercronic: a cron built for containers. It runs unprivileged, passes this container's
# environment (API_URL, CRON_CLIENT_SECRET, ...) to its jobs and logs their output to stdout.
# Pinned release, checked against the SHA1SUM published on its release page
# (https://github.com/aptible/supercronic/releases), linux-amd64 build.
ARG SUPERCRONIC_VERSION=v0.2.49
ARG SUPERCRONIC_SHA1SUM=e63c11a9726b775a6a11801e81af4f3fb926aa68
RUN curl -fsSL --retry 5 --retry-all-errors -o /usr/local/bin/supercronic \
        "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    && echo "${SUPERCRONIC_SHA1SUM}  /usr/local/bin/supercronic" | sha1sum -c - \
    && chmod 0555 /usr/local/bin/supercronic

# The schedule is in Europe/Bucharest (compose sets TZ too; supercronic honours it).
ENV TZ=Europe/Bucharest

# Root-owned and read-only for the job user.
COPY crontab /cron/crontab
COPY run.sh /cron/run.sh
RUN chmod 0444 /cron/crontab && chmod 0555 /cron/run.sh

# An unprivileged user (uid 10001, like the api image): no shell, no home.
RUN addgroup -S -g 10001 app && adduser -S -D -H -u 10001 -G app -s /sbin/nologin app
USER 10001

HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD ["pgrep", "supercronic"]

# In the foreground as PID 1 (it reaps the jobs' children); job output goes straight to the
# container log (docker compose logs cron).
CMD ["supercronic", "-passthrough-logs", "/cron/crontab"]
