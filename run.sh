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

python app.py

