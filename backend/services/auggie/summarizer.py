"""
ResponseSummarizer - Summarizes Auggie responses for concise reporting.

Used by integrations like Slack where full responses are too verbose.
"""

import re
import logging
from typing import List, Tuple

log = logging.getLogger('auggie.summarizer')


class ResponseSummarizer:
    """
    Summarizes Auggie responses into concise status updates.
    
    Extracts key actions like:
    - Files created/modified/deleted
    - Commands executed
    - Errors encountered
    - Key findings
    """
    
    # Patterns to detect actions
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
        """
        Generate a concise summary of the response.
        
        Args:
            content: Full response content
            max_length: Maximum summary length
            
        Returns:
            Concise summary string
        """
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
        
        # Status emoji
        if errors:
            parts.append("❌")
        elif status == 'success':
            parts.append("✅")
        elif status == 'failure':
            parts.append("⚠️")
        else:
            parts.append("📝")
        
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
        
        # Add specific details (truncated)
        details = []
        if files_created:
            details.append(f"📄 Created: {', '.join(files_created[:3])}")
        if files_modified:
            details.append(f"✏️ Modified: {', '.join(files_modified[:3])}")
        if errors:
            details.append(f"❗ Error: {errors[0][:100]}")
        
        if details:
            parts.append("\n" + "\n".join(details))
        
        # If no specific actions detected, use first meaningful line
        if not actions and not details:
            first_line = cls._get_first_meaningful_line(content)
            if first_line:
                parts.append(first_line[:200])
        
        summary = " ".join(parts) if len(parts) > 1 else parts[0] if parts else "Task processed"
        
        # Truncate if needed
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."
        
        return summary
    
    @classmethod
    def _detect_status(cls, content: str) -> str:
        """Detect overall success/failure status."""
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
        """Extract all matches from patterns."""
        matches = []
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                if match.groups():
                    matches.append(match.group(1).strip())
        return list(set(matches))  # Dedupe
    
    @classmethod
    def _get_first_meaningful_line(cls, content: str) -> str:
        """Get first non-empty, meaningful line."""
        for line in content.split('\n'):
            line = line.strip()
            # Accept any non-empty line that's not just a comment
            if line and not line.startswith('#'):
                return line
        return ""

