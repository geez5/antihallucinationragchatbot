import requests

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    passed = 0
    total = 6

    print("Starting backend tests...\n")

    # TEST 1 — Health check
    print("TEST 1: Health check")
    try:
        res = requests.get(f"{BASE_URL}/health")
        if res.status_code == 200 and res.json().get("status") == "ok":
            print("PASS")
            passed += 1
        else:
            print(f"FAIL: Expected 200 and {{'status': 'ok'}}, got {res.status_code} and {res.text}")
    except Exception as e:
        print(f"FAIL: Exception occurred: {e}")
    print()

    # TEST 2 — On-topic question gets a real answer
    print("TEST 2: On-topic question gets a real answer")
    chat_history = []
    q2 = "What does your company do?"
    ans2 = ""
    try:
        res = requests.post(f"{BASE_URL}/chat", json={"question": q2, "chat_history": chat_history})
        if res.status_code == 200:
            data = res.json()
            ans2 = data.get("answer", "")
            sources = data.get("sources", [])
            if len(ans2) > 20 and len(sources) > 0:
                print("PASS")
                passed += 1
            else:
                print(f"FAIL: Answer length ({len(ans2)}) or sources length ({len(sources)}) didn't meet criteria.")
                print(f"Response: {data}")
        else:
            print(f"FAIL: Status code {res.status_code}")
    except Exception as e:
        print(f"FAIL: Exception occurred: {e}")
    print()

    # TEST 3 — Off-topic question gets blocked
    print("TEST 3: Off-topic question gets blocked")
    q3 = "Who won the FIFA World Cup in 2022?"
    try:
        res = requests.post(f"{BASE_URL}/chat", json={"question": q3, "chat_history": []})
        if res.status_code == 200:
            ans3 = res.json().get("answer", "").lower()
            blocking_phrases = ["can only answer", "can only provide", "cannot answer", "only answer", "unable to answer", "i am an ai"]
            if any(phrase in ans3 for phrase in blocking_phrases) or len(ans3) > 0:
                if any(phrase in ans3 for phrase in blocking_phrases):
                    print("PASS")
                    passed += 1
                else:
                    print(f"POSSIBLE FAIL (Check manually): Answer might not be a blocking message. Got: {ans3}")
            else:
                print(f"FAIL: Answer did not contain blocking message. Got: {ans3}")
        else:
            print(f"FAIL: Status code {res.status_code}")
    except Exception as e:
        print(f"FAIL: Exception occurred: {e}")
    print()

    # TEST 4 — Question not on site returns fallback
    print("TEST 4: Question not on site returns fallback")
    # Using a business-related question so it passes Intent check, but info won't be in the DB
    q4 = "What is your refund policy for enterprise customers?"
    try:
        res = requests.post(f"{BASE_URL}/chat", json={"question": q4, "chat_history": []})
        if res.status_code == 200:
            ans4 = res.json().get("answer", "").lower()
            fallback_phrases = ["couldn't find", "contact us", "could not find", "don't have", "not mentioned", "not specify", "unable to find", "don't know", "cannot provide"]
            if any(phrase in ans4 for phrase in fallback_phrases):
                print("PASS")
                passed += 1
            else:
                print(f"POSSIBLE FAIL (Check manually): Answer did not contain expected fallback message. Got: {ans4}")
        else:
            print(f"FAIL: Status code {res.status_code}")
    except Exception as e:
        print(f"FAIL: Exception occurred: {e}")
    print()

    # TEST 5 — Feedback endpoint works
    print("TEST 5: Feedback endpoint works")
    try:
        feedback_data = {
            "session_id": "test",
            "rating": 1,  # rating must be an integer per the backend validation
            "question": "test q",
            "answer": "test a"
        }
        res = requests.post(f"{BASE_URL}/feedback", json=feedback_data)
        if res.status_code == 200 and res.json().get("status") == "received":
            print("PASS")
            passed += 1
        else:
            print(f"FAIL: Expected 200 and {{'status': 'received'}}, got {res.status_code} and {res.text}")
    except Exception as e:
        print(f"FAIL: Exception occurred: {e}")
    print()

    # TEST 6 — Follow-up question with chat history
    print("TEST 6: Follow-up question with chat history")
    try:
        # Using the question and answer from Test 2 to form history
        history = [
            {"role": "user", "content": q2},
            {"role": "assistant", "content": ans2}
        ]
        q6 = "Can you elaborate on that?"
        res = requests.post(f"{BASE_URL}/chat", json={"question": q6, "chat_history": history})
        if res.status_code == 200:
            ans6 = res.json().get("answer", "")
            # Basic sanity check: ensure it's not just repeating the user or previous answer
            if len(ans6) > 10 and q6 not in ans6 and ans6 != ans2:
                print("PASS")
                passed += 1
            else:
                print(f"FAIL: Answer seems incorrect or repeating. Got: {ans6}")
        else:
            print(f"FAIL: Status code {res.status_code}")
    except Exception as e:
        print(f"FAIL: Exception occurred: {e}")
    print()

    print(f"=============================")
    print(f"SUMMARY: {passed}/{total} tests passed.")
    print(f"=============================")

if __name__ == "__main__":
    run_tests()
