FROM python:3.12-slim
WORKDIR /app
COPY aire aire
COPY fixtures fixtures
RUN mkdir /data && chown 65532:65532 /data
ENV AIRE_DB=/data/aire.db PYTHONDONTWRITEBYTECODE=1
USER 65532:65532
EXPOSE 8080
CMD ["sh", "-ec", "python -m aire collect && exec python -m aire serve --host 0.0.0.0"]
