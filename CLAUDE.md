# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Claude Agent SDK-powered REST API** service for providing intelligent UBL invoice field recommendations. The service exposes Claude's reasoning capabilities via HTTP endpoints and supports multi-turn conversational interactions.

**Technology Stack**: Python 3.x + FastAPI + Claude Agent SDK + SSE (Server-Sent Events)

## Architecture

### Three-Layer Architecture

1. **API Layer** (`api/`)
   - `endpoints.py`: FastAPI route handlers, request validation, SSE streaming
   - `models.py`: Pydantic models for request/response validation
   - `agent_service.py`: Claude SDK integration, prompt building, message streaming

2. **Agent Layer** (`.claude/skills/`)
   - Skills define specialized workflows for invoice field recommendations
   - Skills loaded via Claude SDK's Skill tool

3. **Context Data Layer** (unified data directory)
   - `data/basic-data/`: Master data (currencies, tax codes, payment means, etc.) - shared across tenants
   - `data/tenants/{tenant_id}/invoices/{country_code}/`: Historical successful invoices (UBL 2.1 JSON)
   - `data/tenants/{tenant_id}/pending-invoices/`: Draft invoices awaiting field recommendations

### Request Flow

```
Frontend → POST /api/query → endpoints.py → agent_service.py → Claude SDK
                                                                      ↓
                                                              Loads skills
                                                                      ↓
                                               Executes Tools (Read, Grep, Glob, WebSearch)
                                                                      ↓
                                                     Returns recommendations
                                                                      ↓
                           SSE Stream ← format_sse_message() ← AssistantMessage
```

## Development Commands

### Environment Setup

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Service

```bash
# Start server (recommended - auto-checks dependencies)
./run.sh

# Or manually start with uvicorn
cd /Users/qinqiang02/colab/codespace/ai/invoice_engine_3rd/agents
source .venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

**Critical**: Service MUST run in `/Users/qinqiang02/colab/codespace/ai/invoice_engine_3rd/agents` directory because:
- Claude SDK loads `CLAUDE.md` from current working directory
- Skills are resolved relative to `.claude/skills/`
- Claude SDK `cwd` is set to `agents/` root for skill loading and data access
- All data is under `./data/` directory (basic-data and tenants)

### Testing

```bash
# Web UI test
open http://localhost:8000

# Python test script
python tests/test_api.py

# Shell script test
./tests/test_query.sh

# Direct curl test
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "1",
    "prompt": "推荐unitCode for 咖啡机",
    "skill": "invoice-field-recommender",
    "language": "中文",
    "country_code": "MY"
  }'
```

### Data Export Scripts

```bash
cd script

# Export basic master data (currencies, tax codes, payment means, etc.)
./export_basic_data.py

# Export historical invoices - full export
./export_invoice_data.sh

# Export historical invoices - incremental export
EXPORT_MODE=incremental ./export_invoice_data.sh

# Export for specific tenant
EXPORT_MODE=incremental TENANT_ID=1 ./export_invoice_data.sh

# Dry run (preview without writing)
DRY_RUN=true EXPORT_MODE=incremental ./export_invoice_data.sh
```

See `script/USAGE.md` for detailed export script documentation.

## Key Implementation Details

### Session Management

- **Stateless backend**: Backend does not store session state
- **Frontend-managed sessionId**: Frontend receives `session_id` from `session_created` event and maintains it
- **New session**: `session_id: null` → Backend builds full context prompt
- **Resume session**: `session_id: "abc-123"` → Claude SDK restores conversation history

### SSE Event Types

| Event | Description | Data Format |
|-------|-------------|-------------|
| `session_created` | New session initialized | `{"session_id": "abc-123"}` |
| `assistant_message` | Claude's response text | `{"content": "..."}` |
| `todos_update` | TodoWrite tool updates | `{"todos": [...]}` |
| `result` | Session completion | `{"session_id": "...", "duration_ms": 1234, "num_turns": 2, "is_error": false}` |
| `error` | Error occurred | `{"message": "...", "type": "..."}` |


## Environment Variables

Configure via `.env.prod` (loaded by `python-dotenv`):

```bash
# Anthropic API (or compatible API)
ANTHROPIC_AUTH_TOKEN=your_api_key
ANTHROPIC_API_KEY=your_api_key
ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic
API_TIMEOUT_MS=3000000
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```
## Data Directory Structure

**Unified Data Architecture**:
- `data/` - Single data directory containing all data (relative to cwd = agents/)
- `data/basic-data/` - Shared master data (accessible by all tenants)
- `data/tenants/` - Tenant-specific data (isolated via prompt constraints)

```
agents/                            # cwd (Claude SDK working directory)
├── CLAUDE.md
├── .claude/
│   └── skills/                    # Skills auto-loaded from cwd/.claude/skills/
│       └── invoice-field-recommender/
│           └── SKILL.md
│
└── data/                          # Unified data directory
    ├── basic-data/                # Shared master data
    │   ├── global/
    │   │   ├── currencies.json
    │   │   └── invoice-types.json
    │   └── codes/
    │       ├── uom-codes/{country}.json
    │       ├── tax-category-codes/{country}.json
    │       └── payment-means/{country}.json
    │
    └── tenants/                   # Tenant data (isolated via prompt constraints)
        ├── {tenant_id}/           # Tenant-specific directory
        │   ├── invoices/          # Historical invoices
        │   │   └── {country_code}/
        │   │       └── {date}+{invoice_number}.json
        │   └── pending-invoices/  # Draft invoices
        │       └── draft_{country}_{timestamp}.xml
        └── .export_state/         # Export state management
            └── .last_export_time
```

## Production Deployment Considerations

1. **CORS**: Restrict `allow_origins` to specific domains in `app.py`
2. **Authentication**: Add API key authentication middleware
3. **Rate Limiting**: Implement request throttling
4. **Monitoring**: Add APM (e.g., Prometheus, Datadog)
5. **HTTPS**: Use reverse proxy (Nginx) for SSL termination
6. **Environment**: Use `.env.prod` for production config
7. **Database Credentials**: Ensure `script/export_*.py` use environment variables for DB passwords
