#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Start the Slack poller to receive and process messages.

Usage:
    export SLACK_BOT_TOKEN="xoxb-your-token"
    export SLACK_CHANNEL_ID="D1234567890"  # Your DM channel with the bot
    python start_slack.py
"""

import os
import sys
import signal
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)

def main():
    # Check required env vars
    if not os.environ.get('SLACK_BOT_TOKEN'):
        print("❌ Error: Set SLACK_BOT_TOKEN environment variable")
        print("   Get it from: https://api.slack.com/apps → Your App → OAuth & Permissions")
        sys.exit(1)
    
    if not os.environ.get('SLACK_CHANNEL_ID'):
        print("❌ Error: Set SLACK_CHANNEL_ID environment variable")
        print("   To find it: Open Slack → Right-click the DM → View conversation details → Copy the ID at bottom")
        print("   Or: Open DM in browser, the URL will be like: slack.com/archives/D1234567890")
        sys.exit(1)
    
    from backend.services.slack import SlackPoller
    
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


if __name__ == '__main__':
    main()

