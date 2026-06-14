"""
test_backend.py - GIS-RAG Chatbot Backend Test Suite
=========================================================
Tests all 6 scenarios against the running FastAPI backend.
Run with:
    python test_backend.py

Backend must be running at http://127.0.0.1:8000
"""

import sys
import time
import requests

# ==============================================================================
# CONFIG
# ==============================================================================
BASE_URL = "http://127.0.0.1:8000"
TIMEOUT  = 60   # seconds — LLM calls can be slow; don't time out prematurely

import io
import os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Colours (disabled automatically on Windows if not supported)
try:
    if os.name == "nt":
        os.system("")          # enable ANSI escape codes on Windows terminal
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"
except Exception:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""

# ==============================================================================
# HELPERS
# ==============================================================================
results: list[dict] = []

def header(test_num: int, title: str) -> None:
    print(f"\n{CYAN}{BOLD}{'-'*60}{RESET}")
    print(f"{CYAN}{BOLD}  TEST {test_num}: {title}{RESET}")
    print(f"{CYAN}{'-'*60}{RESET}")

def record(test_num: int, title: str, passed: bool,
           detail: str = "", elapsed: float = 0.0) -> None:
    tag    = f"{GREEN}PASS [OK]{RESET}" if passed else f"{RED}FAIL [!!]{RESET}"
    timing = f"  ({elapsed:.2f}s)"
    print(f"  Result : {tag}{timing}")
    if detail:
        print(f"  Detail : {detail}")
    results.append({"num": test_num, "title": title, "passed": passed})

# ==============================================================================
# SHARED STATE (answers reused across tests)
# ==============================================================================
q2_question = "What does this company do?"
q2_answer   = ""

# ==============================================================================
# TEST 1 — Health check
# ==============================================================================
def test_1():
    title = "Health check (GET /health → 200 + status:ok)"
    header(1, title)
    t0 = time.time()
    try:
        res = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        elapsed = time.time() - t0

        print(f"  Status : {res.status_code}")
        print(f"  Body   : {res.text[:200]}")

        ok = res.status_code == 200 and res.json().get("status") == "ok"
        detail = "" if ok else f"Got status={res.status_code}, body={res.text[:200]}"
        record(1, title, ok, detail, elapsed)
    except Exception as exc:
        record(1, title, False, f"Exception: {exc}", time.time() - t0)

# ==============================================================================
# TEST 2 — On-topic question gets a real answer
# ==============================================================================
def test_2():
    global q2_answer
    title = "On-topic question → real answer + sources (POST /chat)"
    header(2, title)
    t0 = time.time()
    try:
        payload = {"question": q2_question, "chat_history": []}
        res     = requests.post(f"{BASE_URL}/chat", json=payload, timeout=TIMEOUT)
        elapsed = time.time() - t0

        print(f"  Status : {res.status_code}")
        if res.status_code == 200:
            data        = res.json()
            q2_answer   = data.get("answer", "")
            sources     = data.get("sources", [])
            print(f"  Answer : {q2_answer[:150]}{'...' if len(q2_answer)>150 else ''}")
            print(f"  Sources: {sources}")

            ok     = len(q2_answer) > 20 and len(sources) > 0
            detail = (
                ""
                if ok
                else f"answer_len={len(q2_answer)} (need >20), sources={sources} (need ≥1)"
            )
            record(2, title, ok, detail, elapsed)
        else:
            record(2, title, False, f"HTTP {res.status_code}: {res.text[:200]}", elapsed)
    except Exception as exc:
        record(2, title, False, f"Exception: {exc}", time.time() - t0)

# ==============================================================================
# TEST 3 — Off-topic question gets blocked by Layer 1 intent classifier
# ==============================================================================
def test_3():
    title = "Off-topic question → blocked by intent classifier (POST /chat)"
    header(3, title)
    t0 = time.time()
    try:
        question = "Who won the FIFA World Cup in 2022?"
        payload  = {"question": question, "chat_history": []}
        res      = requests.post(f"{BASE_URL}/chat", json=payload, timeout=TIMEOUT)
        elapsed  = time.time() - t0

        print(f"  Status : {res.status_code}")
        if res.status_code == 200:
            answer = res.json().get("answer", "")
            print(f"  Answer : {answer}")

            # Layer 1 should have blocked this with the canned response
            BLOCK_PHRASES = [
                "can only answer",
                "can only provide",
                "cannot answer",
                "only answer questions about",
                "unable to answer",
                "not able to answer",
                "outside the scope",
                "website and services",
            ]
            blocked = any(p in answer.lower() for p in BLOCK_PHRASES)
            detail  = "" if blocked else f"Expected blocking phrase in answer. Got: {answer[:200]}"
            record(3, title, blocked, detail, elapsed)
        else:
            record(3, title, False, f"HTTP {res.status_code}: {res.text[:200]}", elapsed)
    except Exception as exc:
        record(3, title, False, f"Exception: {exc}", time.time() - t0)

# ==============================================================================
# TEST 4 — Question not in knowledge base → fallback message
# ==============================================================================
def test_4():
    title = "Unknown question → fallback (POST /chat)"
    header(4, title)
    t0 = time.time()
    try:
        # Business-flavoured so it clears Layer 1, but the info won't exist in the DB
        question = "What is the price of your diamond-encrusted platinum package for moon travel?"
        payload  = {"question": question, "chat_history": []}
        res      = requests.post(f"{BASE_URL}/chat", json=payload, timeout=TIMEOUT)
        elapsed  = time.time() - t0

        print(f"  Status : {res.status_code}")
        if res.status_code == 200:
            answer = res.json().get("answer", "")
            print(f"  Answer : {answer}")

            FALLBACK_PHRASES = [
                "couldn't find",
                "could not find",
                "contact us",
                "contact us directly",
                "not found",
                "don't have",
                "do not have",
                "not available",
                "not in",
                "no information",
                "cannot find",
                "can't find",
            ]
            is_fallback = any(p in answer.lower() for p in FALLBACK_PHRASES)
            detail = "" if is_fallback else f"Expected fallback phrase. Got: {answer[:200]}"
            record(4, title, is_fallback, detail, elapsed)
        else:
            record(4, title, False, f"HTTP {res.status_code}: {res.text[:200]}", elapsed)
    except Exception as exc:
        record(4, title, False, f"Exception: {exc}", time.time() - t0)

# ==============================================================================
# TEST 5 — Feedback endpoint
# ==============================================================================
def test_5():
    title = "Feedback endpoint (POST /feedback → 200 + status:received)"
    header(5, title)
    t0 = time.time()
    try:
        # rating must be an integer (per backend Pydantic model — FeedbackRequest.rating: int)
        payload = {
            "session_id": "test-session-001",
            "rating"    : -1,          # -1 = thumbs down  |  1 = thumbs up
            "question"  : "test q",
            "answer"    : "test a",
        }
        res     = requests.post(f"{BASE_URL}/feedback", json=payload, timeout=TIMEOUT)
        elapsed = time.time() - t0

        print(f"  Status : {res.status_code}")
        print(f"  Body   : {res.text[:200]}")

        ok     = res.status_code == 200 and res.json().get("status") == "received"
        detail = "" if ok else f"Got status={res.status_code}, body={res.text[:200]}"
        record(5, title, ok, detail, elapsed)
    except Exception as exc:
        record(5, title, False, f"Exception: {exc}", time.time() - t0)

# ==============================================================================
# TEST 6 — Follow-up question with chat history
# ==============================================================================
def test_6():
    title = "Follow-up with chat_history → coherent continuation (POST /chat)"
    header(6, title)

    if not q2_answer:
        record(6, title, False,
               "Skipped — Test 2 did not produce an answer to build history from.")
        return

    t0 = time.time()
    try:
        history = [
            {"role": "user",      "content": q2_question},
            {"role": "assistant", "content": q2_answer},
        ]
        follow_up = "Can you tell me more about that?"
        payload   = {"question": follow_up, "chat_history": history}
        res       = requests.post(f"{BASE_URL}/chat", json=payload, timeout=TIMEOUT)
        elapsed   = time.time() - t0

        print(f"  Status    : {res.status_code}")
        if res.status_code == 200:
            ans6 = res.json().get("answer", "")
            print(f"  Answer    : {ans6[:200]}{'...' if len(ans6)>200 else ''}")
            print(f"  (History  : sent {len(history)} prior turns)")

            # Checks:
            # 1. Response is non-trivial (>10 chars)
            # 2. Doesn't just echo the follow-up question back
            # 3. Is different from the first answer (not a verbatim repeat)
            is_coherent = (
                len(ans6) > 10
                and follow_up.lower() not in ans6.lower()
                and ans6.strip() != q2_answer.strip()
            )
            detail = (
                ""
                if is_coherent
                else (
                    f"len={len(ans6)}, "
                    f"echoes_question={follow_up.lower() in ans6.lower()}, "
                    f"same_as_prev={ans6.strip()==q2_answer.strip()}"
                )
            )
            record(6, title, is_coherent, detail, elapsed)
        else:
            record(6, title, False, f"HTTP {res.status_code}: {res.text[:200]}", elapsed)
    except Exception as exc:
        record(6, title, False, f"Exception: {exc}", time.time() - t0)

# ==============================================================================
# RUNNER
# ==============================================================================
def main():
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  GIS-RAG Backend - Test Suite{RESET}")
    print(f"{BOLD}  Target: {BASE_URL}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    suite_start = time.time()

    test_1()
    test_2()
    test_3()
    test_4()
    test_5()
    test_6()

    total_elapsed = time.time() - suite_start

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r["passed"])
    total  = len(results)

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    for r in results:
        icon  = f"{GREEN}PASS{RESET}" if r["passed"] else f"{RED}FAIL{RESET}"
        print(f"  Test {r['num']}: {icon}  - {r['title']}")

    print(f"{BOLD}{'-'*60}{RESET}")
    score_colour = GREEN if passed == total else (YELLOW if passed >= total // 2 else RED)
    print(f"  {BOLD}{score_colour}{passed}/{total} tests passed{RESET}  "
          f"(total time: {total_elapsed:.1f}s)")
    print(f"{BOLD}{'='*60}{RESET}\n")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
