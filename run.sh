#!/bin/bash

echo "🚀 Starting AI Chat Application..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt

echo ""
echo "✅ Starting server..."
echo "🌐 Open http://localhost:5000 in your browser"
echo ""

# Start Slack bot in background if tokens are configured
if [ -n "$SLACK_BOT_TOKEN" ] && [ -n "$SLACK_APP_TOKEN" ]; then
    echo "🤖 Starting Slack bot in background..."
    python start_slack.py --mode=socket &
    SLACK_PID=$!
    echo "   Slack bot PID: $SLACK_PID"
    echo ""
fi

python app.py

# Cleanup: kill Slack bot when main app exits
if [ -n "$SLACK_PID" ]; then
    kill $SLACK_PID 2>/dev/null
fi

