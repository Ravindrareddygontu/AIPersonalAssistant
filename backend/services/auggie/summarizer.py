import re
import os
import logging
import httpx
from typing import List, Optional

log = logging.getLogger('auggie.summarizer')


class ResponseSummarizer:

    FILE_CREATED_PATTERNS = [
        r'[Cc]reated?\s+(?:file\s+)?[`\'"]([\w/.\-]+)[`\'"]',
        r'[Ww]rote\s+(?:to\s+)?[`\'"]([\w/.\-]+)[`\'"]',
        r'[Ss]aved?\s+(?:to\s+)?[`\'"]([\w/.\-]+)[`\'"]',
    ]
    
    FILE_MODIFIED_PATTERNS = [
        r'[Mm]odified\s+[`\'"]([\w/.\-]+)[`\'"]',
        r'[Uu]pdated\s+[`\'"]([\w/.\-]+)[`\'"]',
        r'[Ee]dited\s+[`\'"]([\w/.\-]+)[`\'"]',
        r'[Cc]hanged\s+[`\'"]([\w/.\-]+)[`\'"]',
    ]
    
    FILE_DELETED_PATTERNS = [
        r'[Dd]eleted?\s+[`\'"]([\w/.\-]+)[`\'"]',
        r'[Rr]emoved?\s+[`\'"]([\w/.\-]+)[`\'"]',
    ]
    
    COMMAND_PATTERNS = [
        r'[Rr]an\s+[`\'"]([\w\s\-./]+)[`\'"]',
        r'[Ee]xecuted\s+[`\'"]([\w\s\-./]+)[`\'"]',
        r'\$\s*([\w\s\-./|>]+)',
    ]
    
    ERROR_PATTERNS = [
        r'[Ee]rror:?\s*(.+)',
        r'[Ff]ailed:?\s*(.+)',
        r'[Ee]xception:?\s*(.+)',
    ]
    
    SUCCESS_INDICATORS = [
        'successfully', 'complete', 'done', 'finished', 'created', 'updated',
        'fixed', 'resolved', 'implemented', 'added', 'installed'
    ]
    
    FAILURE_INDICATORS = [
        'error', 'failed', 'exception', 'could not', 'unable to', 'not found',
        'permission denied', 'timeout'
    ]
    
    @classmethod
    def summarize(cls, content: str, max_length: int = 500) -> str:
        if not content:
            return "❓ No response received"
        
        # Detect overall status
        status = cls._detect_status(content)
        
        # Extract key actions
        files_created = cls._extract_matches(content, cls.FILE_CREATED_PATTERNS)
        files_modified = cls._extract_matches(content, cls.FILE_MODIFIED_PATTERNS)
        files_deleted = cls._extract_matches(content, cls.FILE_DELETED_PATTERNS)
        commands_run = cls._extract_matches(content, cls.COMMAND_PATTERNS)
        errors = cls._extract_matches(content, cls.ERROR_PATTERNS)
        
        # Build summary
        parts = []
        
        # No emoji prefix - keep it clean for Slack formatting
        
        # Action summary
        actions = []
        if files_created:
            actions.append(f"Created {len(files_created)} file(s)")
        if files_modified:
            actions.append(f"Modified {len(files_modified)} file(s)")
        if files_deleted:
            actions.append(f"Deleted {len(files_deleted)} file(s)")
        if commands_run:
            actions.append(f"Ran {len(commands_run)} command(s)")
        
        if actions:
            parts.append(" | ".join(actions))
        
        # Add file details (without emojis)
        if files_created and len(files_created) <= 3:
            parts.append(f"({', '.join(files_created[:3])})")
        elif files_modified and len(files_modified) <= 3:
            parts.append(f"({', '.join(files_modified[:3])})")

        # If no specific actions detected, use first meaningful line
        if not actions:
            first_line = cls._get_first_meaningful_line(content)
            if first_line:
                parts.append(first_line[:150])

        summary = " ".join(parts) if parts else "Task completed"
        
        # Truncate if needed
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."
        
        return summary
    
    @classmethod
    def _detect_status(cls, content: str) -> str:
        content_lower = content.lower()
        
        success_count = sum(1 for ind in cls.SUCCESS_INDICATORS if ind in content_lower)
        failure_count = sum(1 for ind in cls.FAILURE_INDICATORS if ind in content_lower)
        
        if failure_count > success_count:
            return 'failure'
        elif success_count > 0:
            return 'success'
        return 'neutral'
    
    @classmethod
    def _extract_matches(cls, content: str, patterns: List[str]) -> List[str]:
        matches = []
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                if match.groups():
                    matches.append(match.group(1).strip())
        return list(set(matches))  # Dedupe
    
    @classmethod
    def _get_first_meaningful_line(cls, content: str) -> str:
        skip_start = [
            '↳', '│', '─', '╭', '╰', '●', '⎿', '┌', '└', '├',
            '>', '$', '#', '```', '~~~', 'Terminal', 'Command'
        ]

        # Patterns that indicate a command/code line
        command_indicators = [
            '2>/dev/null', '/dev/null', '||', '&&', ' | ',
            'grep ', 'awk ', 'sed ', 'cat ', 'ls ', 'cd ',
            'pip ', 'npm ', 'git ', 'docker ', 'kubectl ',
            '$(', '${', './', '../', '/usr/', '/bin/', '/home/'
        ]

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Skip UI/command lines by prefix
            if any(line.startswith(s) for s in skip_start):
                continue
            # Skip very short lines
            if len(line) < 10:
                continue
            # Skip lines that look like code
            if line.startswith(('import ', 'from ', 'def ', 'class ', 'const ', 'let ', 'var ')):
                continue
            # Skip lines with command indicators
            if any(cmd in line for cmd in command_indicators):
                continue
            # Skip lines with too many special chars (likely code/commands)
            special_count = sum(1 for c in line if c in '|<>{}[]()$`\\;:')
            if special_count > 3:
                continue
            # Accept lines with actual words
            if any(c.isalpha() for c in line):
                # Clean up and return
                return line[:200]
        return "Task completed"


class AISummarizer:

    DEFAULT_MODEL = "gpt-5.2"
    OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

    @classmethod
    def summarize(
        cls,
        question: str,
        answer: str,
        model: Optional[str] = None,
        max_points: int = 3
    ) -> Optional[str]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            log.warning("[AI_SUMMARIZER] OPENAI_API_KEY not set, skipping AI summary")
            return None

        model = model or os.environ.get("SLACK_SUMMARY_MODEL", cls.DEFAULT_MODEL)

        prompt = f"""You're a friendly assistant. Give a quick, human summary of what happened.

User asked: {question}

Bot responded: {answer[:4000]}

Rules:
- Be casual and conversational, like talking to a coworker
- For simple actions (commits, file changes, commands), just say what was done in 1-2 sentences
- Only use bullet points (max {max_points}) if there are multiple distinct things to mention
- Skip unnecessary details, focus on what matters
- No formal language, no "The assistant..." - just be direct

Example good responses:
- "Done! Committed your changes with message 'Fix login bug'"
- "Created the new component and added it to the main page"
- "Found 3 issues: auth token expired, missing env var, and a typo in the config"
"""

        try:
            summary = cls._call_openai(api_key, model, prompt)
            return summary
        except Exception as e:
            log.error(f"[AI_SUMMARIZER] Failed to generate summary: {e}")
            return None

    @classmethod
    def _call_openai(cls, api_key: str, model: str, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You're a friendly, casual assistant. Keep responses short and human. No formal language."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_completion_tokens": 150
        }

        log.info(f"[AI_SUMMARIZER] Requesting summary from {model}")

        with httpx.Client(timeout=30.0) as client:
            response = client.post(cls.OPENAI_API_URL, headers=headers, json=payload)
            if response.status_code != 200:
                log.error(f"[AI_SUMMARIZER] API error {response.status_code}: {response.text}")
            response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()

        log.info(f"[AI_SUMMARIZER] Generated summary: {len(content)} chars")
        return content

