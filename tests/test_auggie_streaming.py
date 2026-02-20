"""
Robust tests for Python-Auggie PTY streaming integration.

These tests verify:
1. PTY communication with auggie
2. Streaming response handling
3. Complex queries requiring multiple tool uses
4. Long response handling
5. Timeout and completion detection

Run with: python -m pytest tests/test_auggie_streaming.py -v -s
"""

import os
import sys
import time
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.session import AuggieSession, SessionManager
from backend.models.stream_state import StreamState
from backend.services.stream_processor import StreamProcessor
from backend.utils.text import TextCleaner

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
log = logging.getLogger('test.auggie')


@dataclass
class StreamTestResult:
    """Result of a streaming test."""
    question: str
    success: bool
    total_time: float
    first_chunk_time: Optional[float] = None
    total_chunks: int = 0
    total_bytes: int = 0
    final_content: str = ''
    raw_output: str = ''
    errors: List[str] = field(default_factory=list)
    tool_blocks_detected: List[str] = field(default_factory=list)
    streaming_events: List[dict] = field(default_factory=list)

    def summary(self) -> str:
        """Generate test result summary."""
        status = "✓ PASS" if self.success else "✗ FAIL"
        return f"""
{'='*80}
{status} - {self.question[:60]}...
{'='*80}
Total Time: {self.total_time:.2f}s
First Chunk: {self.first_chunk_time:.2f}s (time to first response)
Total Chunks: {self.total_chunks}
Total Bytes: {self.total_bytes}
Content Length: {len(self.final_content)} chars
Tool Blocks: {len(self.tool_blocks_detected)}
Errors: {len(self.errors)}

Tool Blocks Detected:
{chr(10).join('  - ' + t for t in self.tool_blocks_detected) or '  (none)'}

Errors:
{chr(10).join('  - ' + e for e in self.errors) or '  (none)'}

Final Content (first 500 chars):
{self.final_content[:500]}...
{'='*80}
"""


class AuggieStreamTester:
    """Test harness for Auggie PTY streaming."""

    WORKSPACE = os.path.expanduser("~/Projects/POC'S/ai-chat-app")

    def __init__(self):
        self.session: Optional[AuggieSession] = None
        self.results: List[StreamTestResult] = []

    def setup(self) -> bool:
        """Initialize auggie session."""
        log.info(f"Setting up AuggieSession for workspace: {self.WORKSPACE}")
        try:
            self.session, is_new = SessionManager.get_or_create(self.WORKSPACE)
            if is_new or not self.session.initialized:
                self.session.start()
                ready, output = self.session.wait_for_prompt(timeout=60)
                if not ready:
                    log.error(f"Failed to initialize session. Output: {output[:500]}")
                    return False
                self.session.initialized = True
            log.info("Session ready!")
            return True
        except Exception as e:
            log.error(f"Setup failed: {e}")
            return False

    def teardown(self):
        """Cleanup session."""
        if self.session:
            log.info("Cleaning up session...")
            self.session.cleanup()
            self.session = None

    def run_streaming_test(self, question: str, timeout: float = 300.0) -> StreamTestResult:
        """Run a single streaming test."""
        result = StreamTestResult(question=question, success=False, total_time=0)
        start_time = time.time()

        log.info(f"\n{'='*60}")
        log.info(f"TEST: {question[:80]}...")
        log.info(f"{'='*60}")

        if not self.session or not self.session.is_alive():
            result.errors.append("Session not alive")
            return result

        try:
            # Drain any pending output
            self.session.drain_output(timeout=0.5)

            # Send the question
            sanitized = question.replace('\n', ' ').strip()
            os.write(self.session.master_fd, sanitized.encode('utf-8'))
            time.sleep(0.1)
            os.write(self.session.master_fd, b'\r')

            log.info(f"Question sent, waiting for response...")

            # Initialize processor and state
            processor = StreamProcessor(sanitized)
            state = StreamState(prev_response=self.session.last_response or "")

            import select
            fd = self.session.master_fd
            last_data_time = time.time()
            first_chunk_received = False
            chunk_count = 0

            # Main streaming loop
            while time.time() - start_time < timeout:
                ready = select.select([fd], [], [], 0.1)[0]

                if ready:
                    try:
                        chunk = os.read(fd, 8192).decode('utf-8', errors='ignore')
                        if chunk:
                            chunk_count += 1
                            result.total_bytes += len(chunk)
                            state.all_output += chunk
                            last_data_time = time.time()

                            if not first_chunk_received:
                                result.first_chunk_time = time.time() - start_time
                                first_chunk_received = True
                                log.info(f"First chunk received at {result.first_chunk_time:.2f}s")

                            # Log streaming event
                            result.streaming_events.append({
                                'time': time.time() - start_time,
                                'chunk_size': len(chunk),
                                'total_output_size': len(state.all_output)
                            })

                            # Process content
                            clean = TextCleaner.strip_ansi(state.all_output)

                            # Check for message echo
                            if not state.saw_message_echo:
                                msg_prefix = sanitized[:30]
                                if msg_prefix in clean:
                                    state.mark_message_echo_found(clean.rfind(msg_prefix))
                                    log.info("Message echo detected")

                            # Extract content
                            if state.saw_message_echo:
                                content = processor.process_chunk(clean, state)
                                if content:
                                    result.final_content = content
                                    result.total_chunks = chunk_count

                                    # Detect tool blocks
                                    for line in content.split('\n'):
                                        if any(tool in line for tool in ['Terminal -', 'Codebase Search', 'Codebase search', 'Read File', 'Web Search']):
                                            if line not in result.tool_blocks_detected:
                                                result.tool_blocks_detected.append(line[:100])
                                                log.info(f"Tool detected: {line[:60]}")

                                # Check for end pattern
                                if processor.check_end_pattern(clean, state):
                                    log.info("End pattern detected!")
                                    break
                    except (BlockingIOError, OSError) as e:
                        result.errors.append(f"Read error: {e}")

                # Check silence timeout - only log once per second
                silence = time.time() - last_data_time
                if silence > 5.0 and state.saw_response_marker:
                    # For simple short responses, we can use shorter silence
                    content_length = len(result.final_content) if result.final_content else 0

                    # Short response heuristic: If we have content, no tool blocks, and silence
                    if content_length > 0 and content_length < 100 and not result.tool_blocks_detected:
                        if silence > 8.0:
                            log.info(f"Short response complete (silence={silence:.1f}s, length={content_length})")
                            break

                    # For longer responses - check if we have substantial content + silence
                    # This is the same approach the production code uses
                    if content_length > 200 and silence > 10.0:
                        # Check actual content ending
                        content = result.final_content.rstrip() if result.final_content else ""
                        last_char = content[-1] if content else ""
                        # Accept proper endings OR if we've waited long enough with stable content
                        if last_char in '.!?)"`\'' or silence > 20.0:
                            log.info(f"Long response complete (silence={silence:.1f}s, len={content_length}, ends='{last_char}')")
                            break

                    # Log warning less frequently
                    if int(silence) != getattr(self, '_last_logged_silence', 0):
                        self._last_logged_silence = int(silence)
                        log.warning(f"Silence timeout ({silence:.1f}s), content_len={content_length}")

                        if state.content_looks_complete():
                            log.info("Content looks complete, ending.")
                            break

                    if silence > 60.0:
                        log.warning("Extended silence, forcing end.")
                        result.errors.append("Extended silence timeout")
                        break

            result.total_time = time.time() - start_time
            result.raw_output = state.all_output
            result.success = len(result.final_content) > 0 and len(result.errors) == 0

            # Store for next test
            self.session.last_response = result.final_content

            log.info(f"Test completed in {result.total_time:.2f}s")
            log.info(f"Content length: {len(result.final_content)} chars")

        except Exception as e:
            result.errors.append(f"Exception: {e}")
            result.total_time = time.time() - start_time
            log.error(f"Test failed with exception: {e}")

        self.results.append(result)
        return result


    def run_all_tests(self) -> dict:
        """Run all test cases and return summary."""
        test_cases = self.get_test_cases()

        log.info(f"\n{'#'*80}")
        log.info(f"# RUNNING {len(test_cases)} STREAMING TESTS")
        log.info(f"{'#'*80}\n")

        for i, (name, question, expected_tools) in enumerate(test_cases, 1):
            log.info(f"\n[{i}/{len(test_cases)}] {name}")
            result = self.run_streaming_test(question)
            print(result.summary())

            # Brief pause between tests
            time.sleep(2)

        return self.generate_report()

    def get_test_cases(self) -> List[tuple]:
        """Define test cases: (name, question, expected_tool_patterns)"""
        return [
            # 1. Simple question - should be fast
            (
                "Simple Arithmetic",
                "What is 2 + 2?",
                []
            ),

            # 2. Codebase search - tests tool execution
            (
                "Codebase Search - Find Function",
                "Find where the function formatMessage is defined in this codebase",
                ["Codebase Search", "Codebase search"]
            ),

            # 3. Complex multi-search question
            (
                "Multi-Search Complex Query",
                "Search the codebase and find: 1) How is the PTY session started with auggie? 2) What timeouts are configured for streaming? 3) How is the response cleaned before sending to frontend?",
                ["Codebase Search", "Codebase search"]
            ),

            # 4. Web search question
            (
                "Web Search Query",
                "What is the current version of Python and when was it released? Search the web for the latest information.",
                ["Web Search"]
            ),

            # 5. File reading test
            (
                "Read File Content",
                "Read the content of backend/session.py and tell me what AuggieSession class does",
                ["Read File", "Codebase"]
            ),

            # 6. Terminal command test
            (
                "Terminal Command Execution",
                "Run 'ls -la backend/' and show me the files",
                ["Terminal"]
            ),

            # 7. Long response generation
            (
                "Long Response - Explain Architecture",
                "Explain in detail the complete architecture of this chat application. Include: 1) Backend structure 2) Frontend structure 3) How PTY works 4) How streaming works 5) Database schema. Be comprehensive.",
                ["Codebase Search", "Codebase search"]
            ),

            # 8. Complex project-specific question (like user's HFCL example)
            (
                "Complex Project Search",
                "Search the codebase for any API endpoints, base URLs, or configuration related to chat or messaging. Find the main routes and their purposes.",
                ["Codebase Search", "Codebase search"]
            ),

            # 9. Multiple tool types in one query
            (
                "Multi-Tool Query",
                "First check what's in the backend/routes directory, then read the chat.py file and explain the main endpoints",
                ["Terminal", "Read File", "Codebase"]
            ),

            # 10. Stress test - very long question
            (
                "Long Question Input",
                "I need you to help me understand the streaming implementation in this codebase. Specifically: " +
                "1) How does the PTY session get created and managed? " +
                "2) What is the StreamState class and how is it used? " +
                "3) How does the StreamProcessor extract content from raw terminal output? " +
                "4) What are all the timeout values and why are they set to those values? " +
                "5) How does the frontend receive and display streamed content? " +
                "6) What patterns indicate that a response is complete? " +
                "7) How are tool blocks (Terminal, Codebase Search, etc.) detected and formatted? " +
                "Search the codebase thoroughly and provide a comprehensive answer.",
                ["Codebase Search", "Codebase search"]
            ),
        ]

    def generate_report(self) -> dict:
        """Generate final test report."""
        passed = sum(1 for r in self.results if r.success)
        failed = len(self.results) - passed

        report = {
            'timestamp': datetime.now().isoformat(),
            'total_tests': len(self.results),
            'passed': passed,
            'failed': failed,
            'pass_rate': f"{(passed/len(self.results)*100):.1f}%" if self.results else "N/A",
            'total_time': sum(r.total_time for r in self.results),
            'avg_first_chunk_time': sum(r.first_chunk_time or 0 for r in self.results) / len(self.results) if self.results else 0,
            'total_bytes_received': sum(r.total_bytes for r in self.results),
            'tests': []
        }

        for r in self.results:
            report['tests'].append({
                'question': r.question[:100],
                'success': r.success,
                'time': r.total_time,
                'first_chunk_time': r.first_chunk_time,
                'content_length': len(r.final_content),
                'tool_blocks': len(r.tool_blocks_detected),
                'errors': r.errors
            })

        return report


# ============================================================================
# PYTEST TEST FUNCTIONS
# ============================================================================

try:
    import pytest
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False

# Global tester instance for pytest
_tester: Optional[AuggieStreamTester] = None


def _get_tester():
    """Get or create tester instance."""
    global _tester
    if _tester is None:
        _tester = AuggieStreamTester()
        if not _tester.setup():
            return None
    return _tester


if PYTEST_AVAILABLE:
    @pytest.fixture(scope="module")
    def tester():
        """Pytest fixture for AuggieStreamTester."""
        t = _get_tester()
        if t is None:
            pytest.skip("Failed to initialize Auggie session")
        yield t
        # Don't teardown between tests - reuse session


@pytest.mark.slow
@pytest.mark.integration
def test_simple_question(tester=None):
    """Test simple arithmetic question - fast response expected."""
    if tester is None:
        tester = _get_tester()
    result = tester.run_streaming_test("What is 2 + 2?")
    print(result.summary())
    assert result.success, f"Test failed: {result.errors}"
    assert "4" in result.final_content, "Expected '4' in response"
    assert result.total_time < 30, "Simple question should complete in under 30s"


@pytest.mark.slow
@pytest.mark.integration
def test_codebase_search(tester=None):
    """Test codebase search functionality."""
    if tester is None:
        tester = _get_tester()
    result = tester.run_streaming_test(
        "Find where the function formatMessage is defined in this codebase"
    )
    print(result.summary())
    assert result.success, f"Test failed: {result.errors}"
    assert len(result.tool_blocks_detected) > 0, "Expected tool blocks for search"


@pytest.mark.slow
@pytest.mark.integration
def test_terminal_command(tester=None):
    """Test terminal command execution."""
    if tester is None:
        tester = _get_tester()
    result = tester.run_streaming_test("Run 'ls backend/' and list the files")
    print(result.summary())
    assert result.success, f"Test failed: {result.errors}"
    # Should mention some backend files
    assert any(f in result.final_content.lower() for f in ['session.py', 'app.py', 'routes']), \
        "Expected backend files in response"


@pytest.mark.slow
@pytest.mark.integration
def test_long_response(tester=None):
    """Test that long responses stream completely without cutoff."""
    if tester is None:
        tester = _get_tester()
    result = tester.run_streaming_test(
        "Explain the complete architecture of this chat application. "
        "Include backend structure, frontend, PTY handling, and database. Be thorough."
    )
    print(result.summary())
    assert result.success, f"Test failed: {result.errors}"
    assert len(result.final_content) > 500, "Expected substantial response"
    # Check it doesn't end mid-sentence
    last_char = result.final_content.rstrip()[-1] if result.final_content.strip() else ''
    assert last_char in '.!?)`"\'', f"Response may be cut off, ends with: {repr(last_char)}"


@pytest.mark.slow
@pytest.mark.integration
def test_complex_multi_tool(tester=None):
    """Test complex query requiring multiple tool uses."""
    if tester is None:
        tester = _get_tester()
    result = tester.run_streaming_test(
        "Search the codebase and explain: 1) How PTY sessions work 2) What timeouts exist 3) How streaming works"
    )
    print(result.summary())
    assert result.success, f"Test failed: {result.errors}"
    assert len(result.tool_blocks_detected) >= 1, "Expected at least one tool block"


@pytest.mark.slow
@pytest.mark.integration
def test_streaming_timing(tester=None):
    """Test that streaming starts promptly."""
    if tester is None:
        tester = _get_tester()
    result = tester.run_streaming_test("Say hello and introduce yourself briefly")
    print(result.summary())
    assert result.success, f"Test failed: {result.errors}"
    assert result.first_chunk_time is not None, "Should have first chunk time"
    assert result.first_chunk_time < 10, f"First chunk took too long: {result.first_chunk_time}s"


# ============================================================================
# STANDALONE EXECUTION
# ============================================================================

def run_single_test(question: str):
    """Run a single test interactively."""
    tester = AuggieStreamTester()
    try:
        if tester.setup():
            result = tester.run_streaming_test(question)
            print(result.summary())
            return result
    finally:
        tester.teardown()


def run_full_suite():
    """Run the full test suite."""
    tester = AuggieStreamTester()
    try:
        if tester.setup():
            report = tester.run_all_tests()

            # Print final report
            print("\n" + "="*80)
            print("FINAL TEST REPORT")
            print("="*80)
            print(json.dumps(report, indent=2))

            # Save report to file
            report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to: {report_file}")

            return report
    finally:
        tester.teardown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Auggie PTY Streaming")
    parser.add_argument('--single', '-s', type=str, help="Run single test with given question")
    parser.add_argument('--full', '-f', action='store_true', help="Run full test suite")
    parser.add_argument('--quick', '-q', action='store_true', help="Run quick sanity check")

    args = parser.parse_args()

    if args.single:
        run_single_test(args.single)
    elif args.quick:
        # Quick sanity check
        run_single_test("What is 2 + 2?")
    elif args.full:
        run_full_suite()
    else:
        print("Usage:")
        print("  python test_auggie_streaming.py --quick          # Quick sanity check")
        print("  python test_auggie_streaming.py --single 'question'  # Single test")
        print("  python test_auggie_streaming.py --full           # Full test suite")
        print("\nOr use pytest:")
        print("  pytest tests/test_auggie_streaming.py -v -s")
