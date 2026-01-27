#!/bin/sh

cd "$(git rev-parse --show-toplevel)" || exit 1

docker build -t vsc_oracle_verifier:dev .

docker run --rm -t vsc_oracle_verifier:dev python3 -c "import uvicorn; print('UVICORN_OK', uvicorn.__version__)"

docker run --rm -t vsc_oracle_verifier:dev
