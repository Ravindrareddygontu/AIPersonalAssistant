#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Start the Slack bot to receive and process messages.

Supports two modes:
1. Socket Mode (recommended for development): Uses WebSocket, no public URL needed
2. Poller Mode (simple fallback): Polls for messages periodically

Usage:
    # Socket Mode (recommended):
    export SLACK_BOT_TOKEN="xoxb-your-token"
    export SLACK_APP_TOKEN="xapp-your-token"  # App-level token with connections:write
    python start_slack.py --mode=socket

    # Poller Mode (simpler):
    export SLACK_BOT_TOKEN="xoxb-your-token"
    export SLACK_CHANNEL_ID="D1234567890"
    python start_slack.py --mode=poller

    # HTTP Mode (production):
    # Configure webhook URLs in Slack app settings and run the main FastAPI app
    # Events URL: https://your-domain/api/slack/events
    # Slash command URL: https://your-domain/api/slack/command
"""

import os
import sys
import signal
import logging
import argparse

from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


def start_socket_mode():
    """Start the bot in Socket Mode using Slack Bolt."""
    if not os.environ.get('SLACK_BOT_TOKEN'):
        print("❌ Error: Set SLACK_BOT_TOKEN environment variable")
        print("   Get it from: https://api.slack.com/apps → Your App → OAuth & Permissions")
        sys.exit(1)

    if not os.environ.get('SLACK_APP_TOKEN'):
        print("❌ Error: Set SLACK_APP_TOKEN environment variable")
        print("   Get it from: https://api.slack.com/apps → Your App → Basic Information → App-Level Tokens")
        print("   Create a token with 'connections:write' scope")
        sys.exit(1)

    from backend.services.bots.slack import create_slack_bot

    bot = create_slack_bot()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n🛑 Stopping...")
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    print("🚀 Starting Slack Bot (Socket Mode)...")
    print(f"   Workspace: {bot.config.workspace}")
    print(f"   Model: {bot.config.model or 'default'}")
    print("\n💬 Mention the bot or send a DM to test!")
    print("   Use /auggie <command> for slash commands")
    print("   Press Ctrl+C to stop\n")

    bot.start_socket_mode(blocking=True)


def start_poller_mode():
    """Start the simple poller-based bot."""
    if not os.environ.get('SLACK_BOT_TOKEN'):
        print("❌ Error: Set SLACK_BOT_TOKEN environment variable")
        print("   Get it from: https://api.slack.com/apps → Your App → OAuth & Permissions")
        sys.exit(1)

    if not os.environ.get('SLACK_CHANNEL_ID'):
        print("❌ Error: Set SLACK_CHANNEL_ID environment variable")
        print("   To find it: Open Slack → Right-click the DM → View conversation details → Copy the ID at bottom")
        print("   Or: Open DM in browser, the URL will be like: slack.com/archives/D1234567890")
        sys.exit(1)

    from backend.services.bots.slack import SlackPoller

    poller = SlackPoller()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n🛑 Stopping...")
        poller.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    print("🚀 Starting Slack Poller...")
    print(f"   Channel: {poller.channel_id}")
    print(f"   Workspace: {poller.workspace}")
    print(f"   Poll interval: {poller.poll_interval}s")
    print("\n💬 Send a message in Slack to test!")
    print("   Press Ctrl+C to stop\n")

    poller.start(blocking=True)


def main():
    parser = argparse.ArgumentParser(description='Start the Slack bot')
    parser.add_argument(
        '--mode', '-m',
        choices=['socket', 'poller'],
        default='socket',
        help='Bot mode: socket (Bolt/WebSocket) or poller (simple polling)'
    )

    args = parser.parse_args()

    if args.mode == 'socket':
        start_socket_mode()
    else:
        start_poller_mode()


if __name__ == '__main__':
    main()

