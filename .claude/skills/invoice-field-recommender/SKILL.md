---
name: invoice-field-recommender
description: Recommend UBL invoice field values based on historical invoice data and basic master data. Use this skill when the user requests field value recommendations for invoice generation, providing tenant ID, country code, product information (name/description/code), and the target field name. The skill searches similar invoices first, then falls back to basic master data if needed.
---

# Invoice Field Recommender

## Overview

Provide intelligent field value recommendations for UBL 2.1 invoice generation by analyzing historical successfully-issued invoices and basic master data in the `/context` directory.

## When to Use This Skill

Use this skill when the user provides:
- Tenant ID (e.g., `1`, `10`, `89`)
- Country code (e.g., `DE`, `FR`, `MY`)
- Product information (name, description, or code)
- Target field name to recommend (e.g., `TaxCategory`, `UnitCode`, `ItemClassificationCode`)

## Recommendation Workflow

**核心原则**: 所有推荐必须基于**语义相似性**（比较查询上下文与数据源的相关性），而非简单的租户/国家匹配

**渐进式查找**: 历史数据 → Country-specific → Global，任一步骤找到高置信度（90%+）推荐值即停止

- **Step1**: 从历史发票中查找语义相似的上下文（如相似商品、相似交易场景）
- **Step2**: 若Step1未找到合适值，则从基础主数据的country-specific候选值中语义匹配
- **Step3**: 若country-specific无合适值，最后从global候选值中语义匹配

### Step 1: Search Historical Invoices (Primary Source)

1. **Locate invoice directory**: `/context/invoices/{tenant_id}/{country_code}/`
   - Files are named: `{InvoiceDate}+{InvoiceNumber}.json`
   - Format: UBL 2.1 compliant JSON (single-line, no formatting)

2. **Search for similar invoices** using semantic understanding:
   - **关键**: 必须评估**上下文相似性**（依字段类型而定）：
     - 商品级字段（unitCode、税率等）：比较商品名称/描述的语义相似度
     - 发票级字段（PaymentMeans等）：比较交易场景、业务类型的相似度
   - **不要**仅因租户/国家匹配就使用历史数据
   - **如果**历史发票中没有语义相似的上下文，则**跳过Step1，直接进入Step2**

3. **Extract field values** from semantically similar invoices:
   - Navigate the nested JSON structure to find the target field
   - Common field paths:
     - `Invoice.InvoiceLine[].Item.ClassifiedTaxCategory.ID` → Tax category code
     - `Invoice.InvoiceLine[].InvoicedQuantity.unitCode` → Unit of measure
     - `Invoice.InvoiceLine[].Item.ClassifiedTaxCategory.Percent` → Tax rate
     - `Invoice.TaxTotal.TaxSubtotal[].TaxCategory.ID` → Tax category at invoice level

4. **Return recommendations** if found:
   - **仅当**找到语义相似且置信度90%+的值时，返回Step1推荐并结束查找
   - **否则**进入Step2

### Step 2: Fallback to Basic Master Data (Secondary Source)

**优先级**: Country-specific语义匹配 > Global语义匹配

#### Step 2a - Country-specific语义匹配 (优先)

1. **读取所有候选值**:
   - `/context/basic-data/codes/uom-codes/{country_code}.json` - Unit of measure codes
   - `/context/basic-data/codes/tax-category-codes/{country_code}.json` - Tax categories
   - `/context/basic-data/codes/payment-means/{country_code}.json` - Payment methods
   - `/context/basic-data/codes/duty-tax-fee-category-codes/{country_code}.json`
   - `/context/basic-data/codes/allowance-reason-codes/{country_code}.json`
   - `/context/basic-data/codes/charge-codes/{country_code}.json`
   - `/context/basic-data/codes/tax-exemption-reason-codes/{country_code}.json`

2. **基于查询上下文进行语义匹配** (适用所有字段类型):
   - **核心原则**: 从**所有可用的候选值**中评估哪个最适合查询上下文
   - **严格禁止**: 搜索预设的特定值 - 这违背了语义匹配的本质！
   - **正确做法**: 分析上下文特征 → 遍历候选值 → 评估匹配度 → 返回最佳匹配

   **示例1 - unitCode字段**:
   - 查询: "租户1, MY, 咖啡机, unitCode"
   - 上下文特征: 咖啡机=单个可数的电器设备
   - ✅ 正确流程:
     1. 读取MY所有unitCode候选值(1163个)
     2. 遍历评估: "piece"✓、"each"✓、"set"△、"thousand piece"✗、"kg"✗
     3. 找到最佳: XPP(Piece) - 置信度95%
   - ❌ 错误做法: 直接搜索"EA是否在MY中" (预设了答案是EA)

   **示例2 - TaxCategory字段**:
   - 查询: "租户1, MY, 食品(面包), TaxCategory"
   - 上下文特征: 食品=基本生活必需品，通常享受税收优惠
   - ✅ 正确流程:
     1. 读取MY所有tax-category-codes候选值
     2. 遍历评估: "E"(Exempt)✓、"Z"(Zero rated)✓、"S"(Standard)✗
     3. 根据MY税制判断最佳匹配
   - ❌ 错误做法: 因为历史发票都用"S"就推荐"S" (忽略了食品特征)

   **示例3 - PaymentMeans字段**:
   - 查询: "租户10, SG, B2B批发, PaymentMeans"
   - 上下文特征: B2B批发=企业间大额交易，通常赊账或转账
   - ✅ 正确流程:
     1. 读取SG所有payment-means候选值
     2. 遍历评估: "30"(Credit transfer)✓、"42"(Payment to bank account)✓、"10"(Cash)✗
     3. 匹配B2B场景特征
   - ❌ 错误做法: 只看历史数据频率，忽略B2B vs B2C差异

3. **返回推荐**:
   - **如果**找到置信度90%+的匹配 → 返回推荐并**终止查找**
   - **否则** → 进入Step 2b

#### Step 2b - Global语义匹配 (仅当country-specific无合适值)

1. **读取所有global候选值**:
   - `/context/basic-data/global/currencies.json` - Currency codes
   - `/context/basic-data/global/invoice-types.json` - Invoice type codes
   - `/context/basic-data/codes/*/global.json` - Various code enums

2. **使用相同的语义匹配策略**:
   - 从global的所有候选值中找最佳匹配
   - 返回最佳匹配结果

## Common Mistakes to Avoid (适用所有字段类型)

**❌ 错误1: 搜索预设的特定值，而非语义匹配**

这是最常见且最严重的错误！

```python
# ❌ 错误示例 (unitCode)
if 'EA' in my_uom_codes:  # 预设答案是EA
    return 'EA'

# ❌ 错误示例 (TaxCategory)
if 'S' in my_tax_codes:  # 预设答案是S
    return 'S'

# ✅ 正确做法 (通用)
candidates = []
for code in country_specific_codes:
    confidence = evaluate_semantic_match(code, query_context)
    if confidence >= 90:
        candidates.append((code, confidence))
return best_match(candidates)
```

**为什么错误？**
- 你在假设答案，而非分析上下文
- 可能错过更合适的 country-specific 值（如 MY 有 XPP，但你去找 EA）
- 违背了语义匹配的核心原则

**❌ 错误2: 忽略上下文相似性，直接使用历史数据**

```python
# ❌ 错误 (unitCode)
# 历史发票都用EA → 推荐EA
# 但没检查: 历史商品是否与"咖啡机"相似？

# ❌ 错误 (TaxCategory)
# 历史发票都用"S" → 推荐"S"
# 但没检查: 历史商品是否与"食品"相似？

# ✅ 正确做法
if has_semantically_similar_items_in_history(query_product):
    return extract_field_from_similar_items()
else:
    skip_step1_go_to_step2()  # 进入基础数据查找
```

**❌ 错误3: 跳过 country-specific，直接用 global**

```python
# ❌ 错误流程
if field_value not in country_data:  # 简单的存在性检查
    return get_from_global(field_value)

# ✅ 正确流程
best_country_match = semantic_match_in_country_data(query_context)
if best_country_match.confidence >= 90:
    return best_country_match
else:
    return semantic_match_in_global_data(query_context)
```

**为什么重要？**
- 各国税制、商业习惯、监管要求不同
- Country-specific 数据更符合当地实践
- 例如: MY 的 XPP(Piece) 可能比 global 的 EA(Each) 更符合当地发票规范

**✅ 正确的思维方式**

对于任何字段推荐：
1. **理解上下文**: 这是什么商品/交易/场景？
2. **遍历候选值**: 不预设答案，看所有可能性
3. **评估匹配度**: 哪个最符合上下文特征？
4. **渐进式查找**: 历史相似 → country-specific → global

## Output Format

Return recommendations as a JSON array (formatted for readability):

```json
[
  {
    "recommended": "推荐值",
    "reason": "理由: 优先是上面step1或step2得出的理由；如果没有，才用common sense，且说明因为step1和step2都找不到合适的值"
  },
  ...
]
```

## Resources

This skill does not include bundled scripts, references, or assets. All data is located in the user's `/context` directory.
