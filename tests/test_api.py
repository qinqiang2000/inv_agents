#!/usr/bin/env python3
"""Test script for Invoice Field Recommender API."""

import requests
import json

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

if __name__ == "__main__":
    test_query()
