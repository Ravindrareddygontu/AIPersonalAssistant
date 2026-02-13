# Terminal vs Python API Comparison Report

**Date:** February 13, 2026  
**Test Chat ID:** `5d01c3a9`  
**Workspace:** `/home/dell/Projects/POC'S/ai-chat-app`

---

## Executive Summary

This report documents a comprehensive comparison between running `auggie` directly in terminal versus through the Python Flask API. The test revealed a **critical bug** in the API's response extraction logic that causes incorrect answers to be saved for subsequent questions in a session.

---

## Test Configuration

### 5 Distinct Test Questions

| # | Question |
|---|----------|
| 1 | What files are in this folder? Just list the main files briefly. |
| 2 | Is there any app running on port 5000? Just answer yes or no and what it is. |
| 3 | What is the current date and time? Answer briefly. |
| 4 | How many Python files are in this project? Give a number. |
| 5 | What is the name of the main Flask app file in this project? |

### Test Methodology

1. Created unique chat ID (`5d01c3a9`) in MongoDB
2. Sent each question through Python API (saves to DB)
3. Ran same questions through direct terminal auggie
4. Compared outputs and database entries

---

## Results: Terminal Output Analysis

### Output Size Comparison

| Question | Terminal Raw (bytes) | Terminal Clean (bytes) | API Response (bytes) |
|----------|---------------------|------------------------|---------------------|
| Q1 (files) | 381,900 | 212,505 | 645 |
| Q2 (port 5000) | ~140,000 | 139,204 | 217 |
| Q3 (date/time) | ~122,000 | 122,308 | 1,090 |
| Q4 (Python files) | ~240,000 | 132,440 | 1,226 |
| Q5 (Flask app) | ~244,000 | 133,827 | 1,423 |

### Key Observations

**Terminal Output Contains:**
- ANSI escape codes for colors/formatting (accounts for ~40% of raw size)
- TUI (Text User Interface) rendering characters (box drawing, etc.)
- Full screen buffer including prompts, history, decorations
- Previous conversation context in the buffer

**API Output Contains:**
- Cleaned markdown text
- Filtered content (UI elements removed)
- Much smaller payload (200-1500 bytes vs 100K-380K)

---

## Results: Response Accuracy

### Terminal Responses (Direct auggie) ✅

| # | Question | Terminal Answer | Status |
|---|----------|-----------------|--------|
| 1 | Files in folder | Listed main.js, package.json, backend/, etc. | ✅ Correct |
| 2 | Port 5000 | "Yes — a Python application is running on port 5000" | ✅ Correct |
| 3 | Date/time | "Friday, February 13, 2026, 12:35 PM IST" | ✅ Correct |
| 4 | Python files | "2143 Python files" | ✅ Correct |
| 5 | Flask app file | "backend/app.py" | ✅ Correct |

### API Responses (Saved to DB) ⚠️

| # | Question | DB Answer | Status |
|---|----------|-----------|--------|
| 1 | Files in folder | Correct file listing | ✅ Correct |
| 2 | Port 5000 | "Yes — Python process running on port 5000" | ✅ Correct |
| 3 | Date/time | `/Projects/POC'S/ai-chat-app` | ❌ **WRONG** |
| 4 | Python files | `/Projects/POC'S/ai-chat-app` | ❌ **WRONG** |
| 5 | Flask app file | `/Projects/POC'S/ai-chat-app` | ❌ **WRONG** |

---

## Database Schema

Each Q&A pair stored in MongoDB:

```json
{
  "id": "5d01c3a9-0-aec0c121",
  "index": 0,
  "question": "What files are in this folder?...",
  "answer": "cleaned response (sent to frontend)",
  "rawAnswer": "original terminal output",
  "questionTime": "2026-02-13T07:04:31.913234",
  "answerTime": "2026-02-13T07:04:43.978078"
}
```

**Unique ID Format:** `{chatId}-{index}-{contentHash}`
- `chatId`: 8-char UUID prefix
- `index`: Sequential message number
- `contentHash`: MD5 hash of first 100 chars of question

---

## Bug Analysis

### Symptom
Questions 3, 4, and 5 have incorrect answers saved to database. The `answer` field contains just the workspace path, while `rawAnswer` contains **previous conversation responses** instead of the current answer.

### Root Cause (Preliminary)
The response extraction logic in `backend/routes/chat.py` appears to:
1. Not properly isolate NEW responses from accumulated session output
2. Grab stale data from the terminal buffer
3. Fail to detect the correct response boundaries when questions are sent in quick succession

### Affected Code
- `backend/routes/chat.py` - `StreamGenerator._stream_response()` method
- Response boundary detection logic
- Session output buffer management

---

## How Python Processes Terminal Output

### Architecture Flow

```
User Request → Flask API → AuggieSession (PTY) → auggie CLI
                    ↓
              Response Stream
                    ↓
         ANSI Strip + Filter (config.py patterns)
                    ↓
              MongoDB Save (answer + rawAnswer)
                    ↓
              Frontend (SSE stream)
```

### Key Components

1. **Session Management** (`backend/session.py`)
   - Uses PTY (pseudo-terminal) for auggie interaction
   - Maintains persistent session per workspace
   - `AuggieSession.wait_for_prompt()` - detects ready state
   - `AuggieSession.drain_output()` - clears buffer

2. **Response Streaming** (`backend/routes/chat.py`)
   - `StreamGenerator.generate()` - main entry point
   - `StreamGenerator._stream_response()` - reads and processes output
   - Sends SSE events to frontend

3. **Output Filtering** (`backend/config.py`)
   - `SKIP_PATTERNS` - list of strings to filter out
   - `BOX_CHARS_PATTERN` - regex for TUI box characters

---

## Recommendations

1. **Fix Response Extraction Bug** (Critical)
   - Improve response boundary detection
   - Clear session buffer before each new question
   - Track message echo to identify response start

2. **Improve Session Management**
   - Add response markers/delimiters
   - Implement proper output isolation per question

3. **Add Logging**
   - Log raw terminal output for debugging
   - Track response extraction boundaries

---

## Test Files

- `run_comparison_test.py` - Test script used for this comparison
- `test_compare_output.py` - Original comparison test file

---

## Appendix: Sample Database Entries

### Q1 (Correct)
```
Message ID: 5d01c3a9-0-aec0c121
Question: What files are in this folder? Just list the main files briefly.
Answer: The user wants to see what files are in the current workspace folder.
Read Directory - .
↳ Listed 87 entries
Here are the main files and folders:
Root files:
• main.js - Electron main process
• package.json - Node.js dependencies
...
```

### Q3 (Incorrect - Bug)
```
Message ID: 5d01c3a9-2-add35686
Question: What is the current date and time? Answer briefly.
Answer: /Projects/POC'S/ai-chat-app  ← WRONG!
Raw Answer: Contains Q1's response instead of Q3's
```

---

*Report generated by comparison test on 2026-02-13*

