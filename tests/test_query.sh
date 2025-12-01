#!/bin/bash

curl -N -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "1",
    "prompt": "推荐unitCode for 飞天茅台",
    "skill": "invoice-field-recommender",
    "language": "zh-CN",
    "session_id": null,
    "country_code": "MY"
  }'
