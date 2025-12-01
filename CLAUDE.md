## Project Overview

This is a AI agent for **UBL2.1-based invoice management system** 

## Repository Structure

### `context/` - Context Data for AI Agents

**Purpose**: Historical invoice data and basic master data optimized for AI agent search and retrieval

**Structure**:

#### `context/invoices/` - Historical Invoice Data
- **Level 1**: Tenant ID (e.g., `1/`, `10/`, `89/`)
- **Level 2**: Country code (e.g., `DE/`, `FR/`, `MY/`)
- **Files**: `{InvoiceDate}+{InvoiceNumber}.json`
- **Format**: UBL 2.1 compliant JSON

#### `context/basic-data/` - Basic Master Data Export
- **Global Data** (`global/`): Currencies, invoice types, code enums (shared across tenants)
- **Tenant Data** (`{tenant_id}/`): Parties, products, tax categories, code mappings (tenant-specific)
- **Format**: JSON with metadata (export time, record count)

