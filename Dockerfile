FROM python:3.12-alpine

WORKDIR /app

RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
RUN chown -R appuser:appgroup /app

USER appuser

CMD ["python", "bot.py"]
