#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Start the Telegram bot to receive and process messages.

Usage:
    export TELEGRAM_BOT_TOKEN="your-bot-token"
    python start_telegram.py

To get a bot token:
    1. Open Telegram and search for @BotFather
    2. Send /newbot and follow the instructions
    3. Copy the token provided

Optional environment variables:
    TELEGRAM_WORKSPACE - Path to the workspace (default: DEFAULT_WORKSPACE_PATH from config)
    TELEGRAM_MODEL - AI model to use (default: system default)
"""

import os
import sys
import signal
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


def main():
    if not os.environ.get('TELEGRAM_BOT_TOKEN'):
        print("❌ Error: Set TELEGRAM_BOT_TOKEN environment variable")
        print("   Get it from: @BotFather on Telegram")
        print("   1. Open Telegram and search for @BotFather")
        print("   2. Send /newbot and follow the instructions")
        print("   3. Copy the token provided")
        sys.exit(1)

    from backend.services.bots.telegram import create_telegram_bot

    bot = create_telegram_bot()

    def signal_handler(sig, frame):
        print("\n🛑 Stopping...")
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    print("🚀 Starting Telegram Bot...")
    print(f"   Workspace: {bot.config.workspace}")
    print(f"   Model: {bot.config.model or 'default'}")
    print("\n💬 Send a message to your bot on Telegram to test!")
    print("   Use /help for available commands")
    print("   Press Ctrl+C to stop\n")

    bot.run_polling()


if __name__ == '__main__':
    main()

