#!/usr/bin/env python3
"""Test script for Invoice Field Recommender API."""

import requests
import json
import sys

def test_query():
    """Test the /api/query endpoint."""
    url = "http://localhost:8000/api/query"

    payload = {
        "tenant_id": "1",
        "prompt": "推荐unitCode for 飞天茅台",
        "skill": "invoice-field-recommender",
        "language": "zh-CN",
        "session_id": None,
        "country_code": "MY"
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }

    print(f"Testing POST {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}\n")

    try:
        # Use stream=True for SSE
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)

        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}\n")

        print("Response Stream:")
        print("-" * 80)

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                print(decoded_line)

        print("-" * 80)

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")


def test_continuation_call():
    """Test continuation call without country_code and language."""
    url = "http://localhost:8000/api/query"

    payload = {
        "tenant_id": "1",
        "prompt": "继续前面的对话",
        "session_id": "test-session-123"
        # No country_code, no language - should succeed for continuation
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }

    print(f"\nTesting Continuation Call: POST {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}\n")

    try:
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            print("✓ Continuation call validation PASSED (accepts request without country_code/language)")
        else:
            print(f"✗ Continuation call validation FAILED")
            print(f"Response: {response.text}")

        return response.status_code == 200

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return False


def test_new_session_missing_country_code():
    """Test new session without country_code should fail validation."""
    url = "http://localhost:8000/api/query"

    payload = {
        "tenant_id": "1",
        "prompt": "推荐unitCode",
        "language": "zh-CN"
        # Missing country_code and session_id=None (implicitly new session)
    }

    headers = {
        "Content-Type": "application/json"
    }

    print(f"\nTesting New Session Missing country_code: POST {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}\n")

    try:
        response = requests.post(url, json=payload, headers=headers)

        print(f"Status Code: {response.status_code}")

        if response.status_code == 422:
            print("✓ Validation correctly REJECTED new session without country_code")
            error_data = response.json()
            print(f"Error details: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
        else:
            print(f"✗ Validation should have rejected this request (expected 422, got {response.status_code})")

        return response.status_code == 422

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return False


def test_new_session_missing_language():
    """Test new session without language should fail validation."""
    url = "http://localhost:8000/api/query"

    payload = {
        "tenant_id": "1",
        "prompt": "推荐unitCode",
        "country_code": "MY"
        # Missing language and session_id=None (implicitly new session)
    }

    headers = {
        "Content-Type": "application/json"
    }

    print(f"\nTesting New Session Missing language: POST {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}\n")

    try:
        response = requests.post(url, json=payload, headers=headers)

        print(f"Status Code: {response.status_code}")

        if response.status_code == 422:
            print("✓ Validation correctly REJECTED new session without language")
            error_data = response.json()
            print(f"Error details: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
        else:
            print(f"✗ Validation should have rejected this request (expected 422, got {response.status_code})")

        return response.status_code == 422

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return False


def run_all_tests():
    """Run all validation tests."""
    print("=" * 80)
    print("Running Validation Tests")
    print("=" * 80)

    results = {
        "New session missing country_code": test_new_session_missing_country_code(),
        "New session missing language": test_new_session_missing_language(),
        "Continuation call without country_code/language": test_continuation_call()
    }

    print("\n" + "=" * 80)
    print("Test Results Summary")
    print("=" * 80)

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + ("All tests PASSED!" if all_passed else "Some tests FAILED!"))

    return all_passed


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--validate":
        # Run validation tests only
        success = run_all_tests()
        sys.exit(0 if success else 1)
    else:
        # Run original query test
        test_query()
