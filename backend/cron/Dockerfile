FROM alpine:3.20

RUN apk add --no-cache curl tzdata

COPY crontab /etc/crontabs/root
COPY run.sh /cron/run.sh
RUN chmod +x /cron/run.sh

# busybox crond, in the foreground; jobs inherit this container's environment
CMD ["crond", "-f", "-l", "8"]
