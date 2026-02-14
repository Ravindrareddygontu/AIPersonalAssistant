"""
Test cases for end-of-response detection.

Tests that responses are captured completely without being cut off mid-sentence.
"""

import requests
import json
import time
import re

BASE_URL = "http://localhost:5000"


def test_simple_response():
    """Test a simple one-word answer - should not be cut off."""
    print("\n" + "="*60)
    print("TEST 1: Simple one-word answer")
    print("="*60)
    
    question = "What is 2+2? Answer in one word only."
    response = send_message(question)
    
    if response:
        print(f"Question: {question}")
        print(f"Answer: {response}")
        
        # Check for common cutoff indicators
        is_complete = check_response_complete(response)
        print(f"Response complete: {is_complete}")
        return is_complete
    return False


def test_sentence_response():
    """Test a full sentence response."""
    print("\n" + "="*60)
    print("TEST 2: Full sentence response")
    print("="*60)
    
    question = "What is the capital of France? Answer in one sentence."
    response = send_message(question)
    
    if response:
        print(f"Question: {question}")
        print(f"Answer: {response}")
        
        is_complete = check_response_complete(response)
        print(f"Response complete: {is_complete}")
        return is_complete
    return False


def test_list_response():
    """Test a response with a list - common cutoff scenario."""
    print("\n" + "="*60)
    print("TEST 3: List response (common cutoff scenario)")
    print("="*60)
    
    question = "List 3 primary colors. Be brief."
    response = send_message(question)
    
    if response:
        print(f"Question: {question}")
        print(f"Answer: {response}")
        
        is_complete = check_response_complete(response)
        print(f"Response complete: {is_complete}")
        return is_complete
    return False


def test_question_ending():
    """Test response that might end with a question (previous cutoff issue)."""
    print("\n" + "="*60)
    print("TEST 4: Response ending with question")
    print("="*60)
    
    question = "What is Python? Give a one-line definition and ask if I want more details."
    response = send_message(question)
    
    if response:
        print(f"Question: {question}")
        print(f"Answer: {response}")
        
        is_complete = check_response_complete(response)
        # For this test, response should end with "?" 
        ends_with_question = response.rstrip().endswith('?')
        print(f"Response complete: {is_complete}")
        print(f"Ends with question mark: {ends_with_question}")
        return is_complete
    return False


def test_longer_response():
    """Test a longer response to ensure it's not cut off."""
    print("\n" + "="*60)
    print("TEST 5: Longer response")
    print("="*60)
    
    question = "Explain what a variable is in programming in 2-3 sentences."
    response = send_message(question)
    
    if response:
        print(f"Question: {question}")
        print(f"Answer: {response}")
        print(f"Answer length: {len(response)} chars")
        
        is_complete = check_response_complete(response)
        print(f"Response complete: {is_complete}")
        return is_complete
    return False


def send_message(message: str, timeout: int = 120) -> str | None:
    """Send a message to the chat API and collect the streamed response."""
    try:
        # Create a new chat
        chat_response = requests.post(f"{BASE_URL}/api/chats", json={}, timeout=10)
        chat_id = chat_response.json().get('id', 'test-chat')

        # Send message via SSE stream (POST request)
        response = requests.post(
            f"{BASE_URL}/api/chat/stream",
            json={"message": message, "chat_id": chat_id},
            stream=True,
            timeout=timeout
        )
        
        streaming_content = ""
        final_content = None

        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    event_type = chunk.get("type", "")

                    if event_type == "stream":
                        # Accumulate streaming chunks
                        streaming_content += chunk.get("content", "")
                    elif event_type == "stream_end":
                        # Use final content if provided, otherwise use accumulated
                        final_content = chunk.get("content", "") or streaming_content
                    elif event_type == "response":
                        # Fallback: use response message if no streaming occurred
                        if not final_content and not streaming_content:
                            final_content = chunk.get("message", "")
                    elif event_type == "error":
                        print(f"Error: {chunk.get('message', 'Unknown error')}")
                        return None
                except json.JSONDecodeError:
                    pass

        # Return final content or accumulated streaming content
        result = final_content if final_content else streaming_content
        return result.strip()
        
    except requests.exceptions.Timeout:
        print("Request timed out!")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def check_response_complete(response: str) -> bool:
    """
    Check if response appears complete (not cut off mid-sentence).
    
    Returns True if response looks complete, False if it appears truncated.
    """
    if not response:
        return False
    
    response = response.strip()
    
    # Check for common incomplete word endings (articles, prepositions, etc.)
    incomplete_endings = [
        ' the', ' a', ' an', ' to', ' for', ' with', ' in', ' on', ' at',
        ' of', ' by', ' as', ' is', ' are', ' was', ' were', ' be', ' been',
        ' have', ' has', ' had', ' do', ' does', ' did', ' will', ' would',
        ' could', ' should', ' may', ' might', ' must', ' can', ' this',
        ' that', ' these', ' those', ' my', ' your', ' his', ' her', ' its',
        ' our', ' their', ' and', ' or', ' but', ' if', ' when', ' where',
        ' which', ' who', ' whom', ' whose', ' e.g.', ' i.e.', ' etc',
    ]
    
    response_lower = response.lower()
    for ending in incomplete_endings:
        if response_lower.endswith(ending):
            print(f"  WARNING: Response ends with incomplete word: '{ending.strip()}'")
            return False
    
    # Check for proper sentence ending punctuation
    proper_endings = ['.', '!', '?', ':', ')', ']', '"', "'", '`']
    last_char = response[-1] if response else ''
    
    if last_char not in proper_endings:
        # Could be a code block or list item - check for common patterns
        if not re.search(r'```\s*$', response):  # code block
            print(f"  WARNING: Response doesn't end with punctuation: '{last_char}'")
            # This is a soft warning, not necessarily incomplete
    
    return True


def run_all_tests():
    """Run all test cases."""
    print("\n" + "#"*60)
    print("# END-OF-RESPONSE DETECTION TEST SUITE")
    print("#"*60)
    
    results = []
    
    # Run each test with a small delay between
    tests = [
        ("Simple Response", test_simple_response),
        ("Sentence Response", test_sentence_response),
        ("List Response", test_list_response),
        ("Question Ending", test_question_ending),
        ("Longer Response", test_longer_response),
    ]
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"Test {name} failed with error: {e}")
            results.append((name, False))
        time.sleep(2)  # Small delay between tests
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    failed = 0
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed} passed, {failed} failed out of {len(results)}")
    return failed == 0


if __name__ == "__main__":
    run_all_tests()

