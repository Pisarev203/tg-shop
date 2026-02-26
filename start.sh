#!/usr/bin/env bash
set -e

# запускаем сайт в фоне
python -m uvicorn main:app --host 0.0.0.0 --port 5000 &

# запускаем бота (он будет работать постоянно)
python bot.py
