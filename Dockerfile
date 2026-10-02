FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production REQUIRE_LOGIN=true COOKIE_SECURE=true
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser static ./static
COPY --chown=appuser:appuser models ./models
COPY --chown=appuser:appuser resources ./resources
COPY --chown=appuser:appuser serve.py ./serve.py
USER appuser
EXPOSE 10000
CMD ["python", "serve.py"]
