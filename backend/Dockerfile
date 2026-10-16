FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY policy ./policy
RUN useradd --system --uid 10001 cdiab && chown -R cdiab /srv
USER cdiab
EXPOSE 8000
# Put this behind HTTPS (your platform's load balancer / reverse proxy). Configure everything through environment variables.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
