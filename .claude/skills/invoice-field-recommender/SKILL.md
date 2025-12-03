---
name: invoice-field-recommender
description: Provides intelligent field value recommendations for UBL invoices by analyzing historical invoice data and master data. Supports tenant isolation and progressive fallback strategy.
---

# Invoice Field Recommender

## Overview

This skill provides intelligent field value recommendations for UBL 2.1 invoice generation by analyzing historical successful invoicing records and master data in the `/context` directory.

## When to Use This Skill

Use this skill when users provide:
- **Tenant ID** (e.g., `1`, `10`, `89`)
- **Target field name** (e.g., `unitCode`, `TaxCategory`, `PaymentMeans`)
- **Invoice file path** - Path to pending invoice file in `./context/pending-invoices/{tenantId}/`

## Input Parameters

### Required Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `tenantId` | String | Tenant identifier (numeric) | `"1"`, `"10"`, `"89"` |
| `targetField` | String | UBL field name to recommend | `"unitCode"`, `"TaxCategory"`, `"PaymentMeans"` |
| `invoiceFilePath` | String | Path to pending invoice file | `"./context/pending-invoices/1/order-2024-001.xml"` |

### Input Validation

Before starting the recommendation workflow, validate all required inputs:
1. **Check tenantId**: Must exist, be non-empty, and be a numeric string
2. **Check targetField**: Must exist, be non-empty, and be a recognized UBL field name
3. **Check invoiceFilePath**: Must exist, start with `./context/pending-invoices/{tenantId}/`, and file must exist

### Error Response Format

```json
{
  "error": "ERROR_CODE",
  "message": "English error message",
  "missing_parameters": ["parameter1", "parameter2"]
}
```

## Security and Tenant Isolation

### Critical Security Rules

1. **Tenant ID is mandatory** - Every request must include a valid tenantId
2. **Pending invoice access restriction** - Only read from `./context/pending-invoices/{tenantId}/`
3. **Historical invoice search restriction** - Only search within `./context/invoices/{tenantId}/{countryCode}/`
4. **Path validation** - Reject any paths containing `..` (path traversal)
5. **Basic data access** - `./context/basic-data/` is shared across all tenants

### Path Validation Example

```python
# Before reading pending invoice file:
expected_pending_prefix = f"./context/pending-invoices/{tenant_id}/"
if not invoice_file_path.startswith(expected_pending_prefix):
    raise SecurityError("ACCESS_DENIED: Cross-tenant pending invoice access blocked")

# Before reading historical invoice file:
expected_history_prefix = f"./context/invoices/{tenant_id}/"
if not file_path.startswith(expected_history_prefix):
    raise SecurityError("ACCESS_DENIED: Cross-tenant access blocked")

if ".." in file_path:
    raise SecurityError("Path traversal detected")
```

## Field Dependencies

Extract relevant dependency data from invoiceData based on target field:

| Target Field | Dependency Paths | Matching Context |
|--------------|------------------|------------------|
| `unitCode` | `InvoiceLine[].Item.Name`, `InvoiceLine[].Item.Description` | Product type determines unit |
| `TaxCategory.ID` | `InvoiceLine[].Item.Name`, `InvoiceLine[].Item.Description` | Tax treatment by product type |
| `PaymentMeansCode` | `AccountingCustomerParty`, `InvoiceTypeCode`, `LegalMonetaryTotal.PayableAmount` | Transaction context |
| `DocumentCurrencyCode` | `AccountingSupplierParty.Party.PostalAddress.Country` | Default currency by country |

## Recommendation Workflow

### Core Principle

All recommendations must be based on **semantic similarity**, not simple string equality matching.

### Progressive Lookup Strategy

Historical Data → Country-Specific → Global → WebSearch

```
┌─────────────────────────────────────────────────────────────┐
│                    Input Validation                         │
│ - Validate tenantId, targetField, invoiceData, country code │
│ - Extract dependency data based on targetField              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Step 1: Historical Invoice Search              │
│ Path: ./context/invoices/{tenantId}/{countryCode}/          │
│ - Security: Only search within tenant directory!            │
│ - Find semantically similar invoices                        │
│ - If 90%+ confidence match found → Return and STOP          │
└─────────────────────────────────────────────────────────────┘
                              │
                  (No high confidence match)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│      Step 2: Country-Specific Basic Data (Terminal Step)    │
│ Path: ./context/basic-data/codes/{codeType}/{country}.json  │
│ - Load all candidate values for this field type             │
│ - Perform semantic matching with dependency data            │
│ - 🚨 If file exists → Select best match → Return and STOP   │
└─────────────────────────────────────────────────────────────┘
                              │
              (Country file exists → Return immediately and STOP)
                              │
              (No country-specific data file)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Step 3: Global Basic Data                      │
│ Path: ./context/basic-data/global/*.json                    │
│       ./context/basic-data/codes/*/global.json              │
│ - Perform semantic matching with dependency data            │
│ - If found → Return and STOP                                │
└─────────────────────────────────────────────────────────────┘
                              │
                  (No match found in basic data)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Step 4: WebSearch Fallback                     │
│ - Build search query based on field type and context        │
│ - Use WebSearch tool to find standard codes/values          │
│ - Return with "source: websearch" indicator                 │
└─────────────────────────────────────────────────────────────┘
```

## Execution Control Flow

### Decision Tree Logic (Correct)

```
Step 1: Historical Search (Immediate Termination)
├── Found 90%+ match → Immediately return and STOP
└── No high confidence match → Continue to Step 2

Step 2: Country-Specific Data (Forced Terminal)
├── Country file exists → Select best match → Immediately return and STOP
└── Country file missing → Continue to Step 3

Step 3: Global Data (Only if Step 2 failed)
├── Found global match → Return result and STOP
└── No global match → Continue to Step 4

Step 4: WebSearch (Final fallback)
└── Always return result and STOP
```

### Prohibited Execution Patterns

❌ **Wrong**: Try Step 1 → Try Step 2 → Try Step 3 → Try Step 4
❌ **Wrong**: Continue execution after finding successful match
❌ **Wrong**: Mix results from multiple steps
❌ **Wrong**: "Just to confirm, let me check other sources"

### Key Principles

1. **Stop when answer found** - Don't continue to "confirm"
2. **Single best answer** - Don't mix results from multiple steps
3. **Decision tree logic** - Each step is conditional branch, not sequential execution
4. **Immediate return** - Don't delay after finding valid answer

## Step-by-Step Implementation

### Step 1: Search Historical Invoices (Immediate Termination)

🚨 **Step 1 Absolute Termination Rule** 🚨
- If 90%+ confidence match found → Immediately return and STOP
- Never continue to Step 2 under any circumstances
- Historical match success = Execution complete = Return result to user

1. **Locate invoice directory**: `./context/invoices/{tenant_id}/{country_code}/`
2. **Search for semantically similar invoices** using context similarity
3. **🚨 Immediately return and STOP** if found:
   - **Only when** semantically similar with 90%+ confidence:
     - Immediately return Step 1 recommendation to user
     - **STOP all subsequent step execution**
     - **Forbidden to continue to Step 2, Step 3, or Step 4**

### Step 2: Country-Specific Basic Data (Forced Terminal Step)

🚨 **Critical Termination Rule** 🚨
- Step 2 is a terminal step - execution MUST stop here
- If country-specific file exists → Select best match → Immediately return and STOP
- Never continue to Step 3 after successful Step 2 completion

**【Forced Termination】If country-specific basic data file exists:**
1. Must select a recommendation value from it
2. Must immediately return result to user
3. Must stop all subsequent processing steps
4. Forbidden to continue to Step 3 or any other steps

| Target Field | Data File Path |
|--------------|----------------|
| `unitCode` | `./context/basic-data/codes/uom-codes/{country}.json` |
| `TaxCategory` | `./context/basic-data/codes/tax-category-codes/{country}.json` |
| `PaymentMeans` | `./context/basic-data/codes/payment-means/{country}.json` |
| `AllowanceChargeReason` | `./context/basic-data/codes/allowance-reason-codes/{country}.json` |
| `ChargeCode` | `./context/basic-data/codes/charge-codes/{country}.json` |
| `TaxExemptionReason` | `./context/basic-data/codes/tax-exemption-reason-codes/{country}.json` |

### Step 3: Global Basic Data

**Execute only when country-specific data file does not exist**

1. **Read global candidate values**
2. **Use same semantic matching strategy**
3. **Return best match result**

### Step 4: WebSearch Fallback

**Execute only when Steps 2 and 3 cannot provide recommendations**

Build search queries based on field type and use WebSearch tool.

## Output Format

### Success Response Format

```json
{
  "recommended": "H87",
  "reason": "Found in historical invoices for similar product 'DJI Mavic 3 drone' in tenant 1/MY. Unit code H87 (pieces) commonly used for personal electronic devices.",
  "source": "historical",
  "confidence": "high"
}
```

### Response Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `recommended` | String | Yes | Recommended field value |
| `reason` | String | Yes | Explanation for the recommendation |
| `source` | Enum | Yes | `historical`, `country_basic_data`, `global_basic_data`, `websearch` |
| `confidence` | Enum | No | `high` (90%+), `medium` (70-89%), `low` (<70%) |

## Data Directory Structure

```
./context/
├── pending-invoices/            # Pending invoices (tenant isolated!)
│   └── {tenant_id}/
│       └── {invoice_filename}.xml|.json
│
├── invoices/                    # Historical invoices (tenant isolated!)
│   └── {tenant_id}/
│       └── {country_code}/
│           └── {date}+{invoice_number}.json
│
└── basic-data/                  # Shared basic data (no tenant isolation)
    ├── global/
    │   ├── currencies.json
    │   └── invoice-types.json
    └── codes/
        ├── uom-codes/{country}.json
        ├── tax-category-codes/{country}.json
        ├── payment-means/{country}.json
        └── ...
```

## Common Pitfalls to Avoid

1. **❌ Searching for preset specific values instead of semantic matching**
2. **❌ Ignoring context similarity and directly using historical data**
3. **❌ Cross-tenant data access**
4. **❌ Continuing execution after finding successful match**
5. **❌ Mixing results from multiple steps**

## Non-Negotiable Execution Rules

### Rule #1: Step 1 termination is absolute
- Step 1 is not "exploration phase" - it's "match and return phase"
- Found 90%+ confidence match = Step 1 success = Execution end

### Rule #2: Step 2 termination is absolute
- Step 2 is not "validation phase" - it's "select and return phase"
- Found country-specific data = Step 2 success = Execution end

### Rule #3: Decision tree logic, not sequential search
- Each step is conditional branch, not sequential execution
- Success in any step means immediate termination

### Rule #4: Immediate return, no delay
- Return valid answer the moment it's found
- No "additional checks", "completeness validation", or "alternatives"

### Rule #5: Single answer principle
- Return one best answer, not multiple options
- Don't mix results from different steps
- Trust first high-confidence answer found
