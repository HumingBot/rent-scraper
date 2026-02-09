#!/bin/bash
# Helper script to stop GitHub bot and start local bot

echo "Checking for GitHub Actions bot runs..."
gh run list --limit 5

echo ""
echo "To stop a running GitHub bot, use:"
echo "  gh run cancel <run-id>"
echo ""
echo "Waiting 60 seconds for any remote bot sessions to timeout..."
sleep 60

echo "Starting local bot..."
python3 bot_main.py
