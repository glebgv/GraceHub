#!/bin/bash

if [ "$ENV_MODE" = "dev" ]; then
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
else
  docker compose -f docker-compose.yml up -d --build
fi
