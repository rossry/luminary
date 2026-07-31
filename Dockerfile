# Luminary test server (docs/deploy.md Path 2).
# Serves on 0.0.0.0:8080 inside the container; publish loopback-only and put
# an authenticating proxy or tailnet in front (see docs/deploy.md security
# model — pattern upload executes code in-process by design).

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME /data/store
EXPOSE 8080

CMD ["python", "-m", "luminary.cli", "--store", "/data/store", \
     "serve", "--host", "0.0.0.0", "--port", "8080", "--seed-demo"]
