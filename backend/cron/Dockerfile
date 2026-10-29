FROM alpine:3.20

RUN apk add --no-cache curl tzdata

COPY crontab /etc/crontabs/root
COPY run.sh /cron/run.sh
RUN chmod 0555 /cron/run.sh

HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD ["pgrep", "crond"]

# busybox crond, in the foreground; jobs inherit this container's environment.
# Root on purpose: busybox crond must switch to the crontab's owner for every job and cannot
# run its jobs unprivileged (tested: as a non-root user it starts but never runs a job). The
# container holds no data and no listening port, its only secret is the cron client's, and
# compose adds no-new-privileges. Moving to an unprivileged scheduler (supercronic) is open.
# nosemgrep: dockerfile.security.missing-user.missing-user
CMD ["crond", "-f", "-l", "8"]
