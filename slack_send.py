#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Send a command to Auggie and post the result to Slack.

Usage:
    python3 slack_send.py "your command here"
    
Example:
    python3 slack_send.py "list all python files in this project"
"""

import sys
import json
import urllib.request

# Your Slack webhook
WEBHOOK_URL = ""
WORKSPACE = "~/Projects/POC'S/ai-chat-app"


def send_to_slack(text: str):
    """Send a message to Slack via webhook."""
    data = json.dumps({"text": text}).encode('utf-8')
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"Error sending to Slack: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 slack_send.py \"your command here\"")
        print("Example: python3 slack_send.py \"what is 2+2\"")
        sys.exit(1)
    
    message = " ".join(sys.argv[1:])
    print(f"📤 Sending to Auggie: {message}")
    
    # Send acknowledgment to Slack
    send_to_slack(f"⏳ *Received command:* {message}")
    
    # Execute via Auggie
    from backend.services.auggie import AuggieExecutor, ResponseSummarizer
    
    executor = AuggieExecutor()
    response = executor.execute(message=message, workspace=WORKSPACE)
    
    if response.success:
        summary = ResponseSummarizer.summarize(response.content)
        slack_message = f"✅ *Command:* {message}\n\n{summary}\n\n⏱️ _Completed in {response.execution_time:.1f}s_"
        
        # If response is short, include full content
        if len(response.content) < 500:
            slack_message += f"\n\n```{response.content}```"
    else:
        slack_message = f"❌ *Command:* {message}\n\nError: {response.error}"
    
    # Send to Slack
    print(f"📤 Sending result to Slack...")
    send_to_slack(slack_message)
    print("✅ Done!")
    
    # Also print locally
    print(f"\n📋 Response:\n{response.content}")


if __name__ == "__main__":
    main()

