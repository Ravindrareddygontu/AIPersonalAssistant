"""
ContentCleaner - Cleans terminal artifacts from assistant responses.

Follows Single Responsibility Principle: Only handles content cleaning.
"""

import re


class ContentCleaner:
    """Cleans terminal artifacts and formatting from AI responses."""

    # Patterns that indicate end of AI response (start of prompt)
    PROMPT_INDICATORS = ('›', '│ ›')
    
    # Box drawing characters (no content)
    BOX_CHARS = '─│╭╮╰╯┌┐└┘├┤┬┴┼'

    @classmethod
    def clean_assistant_content(cls, content: str) -> str:
        """
        Remove terminal artifacts from assistant response before saving.
        
        Args:
            content: Raw content from terminal
            
        Returns:
            Cleaned content suitable for display/storage
        """
        if not content:
            return content

        lines = content.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            # Stop at prompt artifacts (marks end of AI response)
            if cls._is_prompt_line(stripped):
                break

            # Stop at path-like lines (terminal prompt showing directory)
            if cls._is_path_line(stripped):
                break

            # Skip empty box lines
            if cls._is_empty_box_line(line):
                continue

            # Skip lines that are ONLY box drawing characters
            if cls._is_box_only_line(stripped):
                continue

            # Skip garbage escape code remnants
            if cls._is_garbage_line(stripped):
                continue

            # Clean trailing garbage characters
            line = cls._clean_trailing_garbage(line, stripped)
            cleaned_lines.append(line)

        result = '\n'.join(cleaned_lines).rstrip()
        # Final cleanup: remove trailing semicolons and numbers
        result = result.rstrip(';0123456789')
        return result

    @classmethod
    def _is_prompt_line(cls, stripped: str) -> bool:
        """Check if line indicates start of prompt (end of response)."""
        if stripped.startswith('›'):
            return True
        if stripped == '│' or stripped.startswith('│ ›'):
            return True
        return False

    @classmethod
    def _is_path_line(cls, stripped: str) -> bool:
        """Check if line looks like a path prompt."""
        return (
            stripped.startswith('/') and 
            '/' in stripped[1:] and 
            len(stripped) < 100
        )

    @classmethod
    def _is_empty_box_line(cls, line: str) -> bool:
        """Check if line is an empty box formatting line."""
        return '│                                                                          │' in line

    @classmethod
    def _is_box_only_line(cls, stripped: str) -> bool:
        """Check if line contains only box drawing characters."""
        return stripped and all(c in cls.BOX_CHARS for c in stripped)

    @classmethod
    def _is_garbage_line(cls, stripped: str) -> bool:
        """Check if line is garbage from escape codes."""
        if not stripped:
            return False
        if len(stripped) <= 5 and stripped.lstrip(';').isdigit():
            return True
        return False

    @classmethod
    def _clean_trailing_garbage(cls, line: str, stripped: str) -> str:
        """Remove trailing escape code remnants."""
        if stripped.endswith(';'):
            return line.rstrip(';0123456789')
        if (len(stripped) > 2 and 
            stripped[-1].isdigit() and 
            stripped[-2].isdigit() and 
            stripped[-3] in ';│'):
            return line.rstrip(';0123456789')
        return line

    @classmethod
    def strip_previous_response(cls, content: str, previous_response: str) -> str:
        """
        Remove previous response from start of content to avoid stale replay.
        
        Args:
            content: Current content
            previous_response: Previous response to strip
            
        Returns:
            Content with previous response removed if it was at the start
        """
        if previous_response and content and content.startswith(previous_response):
            return content[len(previous_response):].lstrip('\n')
        return content

