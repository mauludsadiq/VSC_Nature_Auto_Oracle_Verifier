FROM python:3.9-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN python3 -m pip install --upgrade pip \
  && if [ -f requirements.txt ]; then python3 -m pip install -r requirements.txt; fi \
  && if [ -f requirements-dev.txt ]; then python3 -m pip install -r requirements-dev.txt; fi \
  && if [ -f pyproject.toml ]; then python3 -m pip install .; fi

EXPOSE 8000

CMD ["bash","-lc","scripts/smoke_api.sh"]
