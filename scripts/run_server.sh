#!/usr/bin/env bash
# Simple helper to run the backend server from project root
cd "$(dirname "$0")/.."
python3 backend/server.py
