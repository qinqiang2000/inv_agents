---
name: invoice-field-recommender
description: 通过分析历史发票数据和主数据为 UBL 发票提供智能字段值推荐。支持租户隔离和渐进式回退策略。
---

# 发票字段推荐器

## 概述

该技能通过分析历史成功开票记录和主数据，为 UBL 2.1 发票生成提供智能字段值推荐。

**目录结构说明**：
- 公共数据（basic-data）在当前工作目录 `./basic-data/`
- 租户数据在 `../tenant-data/{tenant_id}/` 目录下

## 何时使用此技能

当用户提供以下信息时使用此技能：
- **租户 ID**（例如 `1`、`10`、`89`）
- **目标字段名称**（例如 `unitCode`、`TaxCategory`、`PaymentMeans`）
- **发票文件路径** - `../tenant-data/{tenantId}/pending-invoices/` 中待处理发票文件的路径

## 输入参数

### 必需参数

| 参数 | 类型 | 描述 | 示例 |
|------|------|------|------|
| `tenantId` | String | 租户标识符（数字） | `"1"`、`"10"`、`"89"` |
| `targetField` | String | 要推荐的 UBL 字段名称 | `"unitCode"`、`"TaxCategory"`、`"PaymentMeans"` |
| `invoiceFilePath` | String | 待处理发票文件的路径 | `"../tenant-data/1/pending-invoices/order-2024-001.xml"` |

### 输入验证

在开始推荐工作流之前，验证所有必需的输入：
1. **检查 tenantId**：必须存在、非空且为数字字符串
2. **检查 targetField**：必须存在、非空且为公认的 UBL 字段名称
3. **检查 invoiceFilePath**：必须存在、以 `../tenant-data/{tenantId}/pending-invoices/` 开头，且文件必须存在

## 安全性和租户隔离

### 关键安全规则

1. **租户 ID 是强制性的** - 每个请求都必须包含有效的 tenantId
2. **待处理发票访问限制** - 仅从 `../tenant-data/{tenantId}/pending-invoices/` 读取
3. **历史发票搜索限制** - 仅在 `../tenant-data/{tenantId}/invoices/{countryCode}/` 内搜索
4. **路径验证** - 拒绝尝试访问其他租户目录的路径
5. **基础数据访问** - `./basic-data/` 在所有租户间共享

### 路径验证示例

```python
# 读取待处理发票文件之前：
expected_pending_prefix = f"../tenant-data/{tenant_id}/pending-invoices/"
if not invoice_file_path.startswith(expected_pending_prefix):
    raise SecurityError("ACCESS_DENIED: 跨租户待处理发票访问被阻止")

# 读取历史发票文件之前：
expected_history_prefix = f"../tenant-data/{tenant_id}/invoices/"
if not file_path.startswith(expected_history_prefix):
    raise SecurityError("ACCESS_DENIED: 跨租户访问被阻止")
```

## 字段依赖关系

根据目标字段从 invoiceData 中提取相关依赖数据：

| 目标字段 | 依赖路径 | 匹配上下文 |
|---------|---------|----------|
| `unitCode` | `InvoiceLine[].Item.Name`、`InvoiceLine[].Item.Description` | 产品类型决定单位 |
| `TaxCategory.ID` | `InvoiceLine[].Item.Name`、`InvoiceLine[].Item.Description` | 按产品类型的税务处理 |
| `PaymentMeansCode` | `AccountingCustomerParty`、`InvoiceTypeCode`、`LegalMonetaryTotal.PayableAmount` | 交易上下文 |
| `DocumentCurrencyCode` | `AccountingSupplierParty.Party.PostalAddress.Country` | 按国家的默认货币 |

---

## 执行状态输出规范

🚨 **每个检查点必须输出以下格式的状态** 🚨

> **📍 检查点 {N}：{检查点名称}**
> - 结果：{成功/无匹配/文件不存在/文件存在}
> - 决策：{🛑 终止 | ➡️ 继续}
> - 原因：{一句话解释}
> - 下一步：{跳转到输出验证 | 进入步骤 N}

---

## 推荐工作流

### 核心原则

1. 所有推荐必须基于**语义相似性**，而不是简单的字符串相等匹配
2. 每个步骤后必须执行**检查点评估**
3. 检查点决策为"终止"时，**立即跳转到输出验证**

### 渐进式查询策略概览

```
输入验证 → 步骤1 → 检查点1 → [终止?] → 步骤2 → 检查点2 → [终止?] → 步骤3 → 检查点3 → [终止?] → 步骤4 → 输出验证
                      ↓                      ↓                      ↓
                 输出验证 ←──────────────────┴──────────────────────┘
```

---

## 分步实现

### 步骤 1：搜索历史发票

1. **定位发票目录**：`../tenant-data/{tenant_id}/invoices/{country_code}/`
2. **安全性检查**：确保仅在租户目录内搜索
3. **使用上下文相似性搜索语义相似的发票**
4. **记录匹配结果和置信度**

---

### 检查点 1：历史匹配评估

**必须回答以下问题并输出状态：**

| 条件 | 决策 | 下一步 |
|------|------|--------|
| 找到 90%+ 置信度匹配 | 🛑 终止 | 跳转到输出验证 |
| 无高置信度匹配 | ➡️ 继续 | 进入步骤 2 |

**状态输出示例（终止）：**

> **📍 检查点 1：历史匹配评估**
> - 结果：成功（置信度 95%，匹配发票：2024-01-15+INV-001.json）
> - 决策：🛑 终止
> - 原因：找到高置信度历史匹配，无需继续查询
> - 下一步：跳转到输出验证

**状态输出示例（继续）：**

> **📍 检查点 1：历史匹配评估**
> - 结果：无匹配（最高置信度 65%，未达到 90% 阈值）
> - 决策：➡️ 继续
> - 原因：历史数据中无高置信度匹配
> - 下一步：进入步骤 2

---

### 步骤 2：国家特定基础数据

**仅当检查点 1 决策为"继续"时执行**

1. **确定数据文件路径**（根据目标字段）：

| 目标字段 | 数据文件路径 |
|---------|------------|
| `unitCode` | `./basic-data/codes/uom-codes/{country}.json` |
| `TaxCategory` | `./basic-data/codes/tax-category-codes/{country}.json` |
| `PaymentMeans` | `./basic-data/codes/payment-means/{country}.json` |
| `AllowanceChargeReason` | `./basic-data/codes/allowance-reason-codes/{country}.json` |
| `ChargeCode` | `./basic-data/codes/charge-codes/{country}.json` |
| `TaxExemptionReason` | `./basic-data/codes/tax-exemption-reason-codes/{country}.json` |

2. **检查文件是否存在**
3. **如果存在**：加载候选值，执行语义匹配，选择最佳匹配
4. **记录文件存在状态和匹配结果**

---

### 检查点 2：国家数据评估

**必须回答以下问题并输出状态：**

| 条件 | 决策 | 下一步 |
|------|------|--------|
| 国家文件存在 | 🛑 终止 | 跳转到输出验证（使用最佳匹配） |
| 国家文件不存在 | ➡️ 继续 | 进入步骤 3 |

🚨 **关键规则**：国家文件存在时，必须从中选择推荐值并终止，即使匹配置信度不高

**状态输出示例（终止）：**

> **📍 检查点 2：国家数据评估**
> - 结果：文件存在（./basic-data/codes/uom-codes/DE.json）
> - 决策：🛑 终止
> - 原因：国家特定数据文件存在，已选择最佳匹配值 "EA"
> - 下一步：跳转到输出验证

**状态输出示例（继续）：**

> **📍 检查点 2：国家数据评估**
> - 结果：文件不存在（./basic-data/codes/uom-codes/XX.json）
> - 决策：➡️ 继续
> - 原因：无国家特定数据文件
> - 下一步：进入步骤 3

---

### 步骤 3：全局基础数据

**仅当检查点 2 决策为"继续"时执行**

1. **读取全局数据文件**：
   - `./basic-data/global/*.json`
   - `./basic-data/codes/*/global.json`
2. **使用相同的语义匹配策略**
3. **记录匹配结果**

---

### 检查点 3：全局数据评估

**必须回答以下问题并输出状态：**

| 条件 | 决策 | 下一步 |
|------|------|--------|
| 找到匹配 | 🛑 终止 | 跳转到输出验证 |
| 无匹配 | ➡️ 继续 | 进入步骤 4 |

**状态输出示例（终止）：**

> **📍 检查点 3：全局数据评估**
> - 结果：成功（在 global.json 中找到匹配）
> - 决策：🛑 终止
> - 原因：全局数据中找到语义匹配值 "KGM"
> - 下一步：跳转到输出验证

**状态输出示例（继续）：**

> **📍 检查点 3：全局数据评估**
> - 结果：无匹配（全局数据中无相关候选值）
> - 决策：➡️ 继续
> - 原因：基础数据中无法找到合适推荐
> - 下一步：进入步骤 4

---

### 步骤 4：网络搜索回退

**仅当检查点 3 决策为"继续"时执行**

1. **根据字段类型和上下文构建搜索查询**
2. **使用网络搜索工具查找标准代码/值**
3. **记录搜索结果**

步骤 4 完成后，直接进入输出验证（无需检查点，因为这是最终回退）

---

## 数据目录结构

**公共数据（当前工作目录 cwd）**：
```
./                              # 工作目录 = agents/context/
└── basic-data/                 # 共享基础数据（无租户隔离）
    ├── global/
    │   ├── currencies.json
    │   └── invoice-types.json
    └── codes/
        ├── uom-codes/{country}.json
        ├── tax-category-codes/{country}.json
        ├── payment-means/{country}.json
        └── ...
```

**租户数据（通过 add_dirs 授权访问）**：
```
../tenant-data/{tenant_id}/     # 租户隔离目录
├── invoices/                   # 历史发票
│   └── {country_code}/
│       └── {date}+{invoice_number}.json
└── pending-invoices/           # 待处理发票
    └── {invoice_filename}.xml|.json
```

---

## 输出验证（最终步骤）

🚨 **任何检查点决策为"终止"后，必须执行此步骤** 🚨

### 结构化输出模板

```json
{
  "recommended": "任何有效的 UBL 字段值 | 目标字段的推荐值。必须是单个特定值。",
  "reason": "推荐此值的原因。",
  "source": "<historical|country_basic_data|global_basic_data|websearch>",
  "confidence": "<high|medium|low>"
}
```

### 验证检查清单

在输出 JSON 之前，验证：

- [ ] 输出是有效的 JSON 格式
- [ ] 包含所有必需字段：`recommended`、`reason`、`source`
- [ ] 当 `source` 为 `"historical"` 时，包含 `confidence` 字段
- [ ] `recommended` 是非空字符串，单个具体值
- [ ] `source` 是四个允许值之一
- [ ] JSON 使用双引号

### 验证失败处理

如果验证失败：
1. 识别具体错误
2. 修正输出格式
3. 重新验证直到通过

---

### 最终输出规则

🚨 **JSON 代码块是最终输出，之后不允许任何内容** 🚨

**输出要求：**
- ✅ 仅输出一个 JSON 代码块
- ✅ JSON 代码块后立即停止响应
- ❌ 禁止在 JSON 后添加"最终建议"
- ❌ 禁止在 JSON 后添加"总结"
- ❌ 禁止在 JSON 后添加任何解释文字
- ❌ 禁止在 JSON 后添加检查点状态框

**完整输出示例：**

```json
{
  "recommended": "XPP",
  "reason": "基于马来西亚 UOM 数据文件中的语义匹配，XPP 适用于电子设备类产品",
  "source": "country_basic_data"
}
```

**（响应在 JSON 代码块结束后立即停止，无任何后续内容）**

---

## 常见陷阱

1. **❌ 跳过检查点状态输出**
2. **❌ 检查点决策为"终止"后继续执行后续步骤**
3. **❌ 搜索预设特定值而不是语义匹配**
4. **❌ 跨租户数据访问**
5. **❌ 混合来自多个步骤的结果**
6. **❌ 输出验证前返回结果**
7. **❌ 最终检查点后添加额外内容（如"最终建议"、"总结"等）**

---

## 执行规则总结

| 规则 | 描述 |
|------|------|
| 检查点必须输出 | 每个检查点必须输出标准格式的状态 |
| 终止即跳转 | 检查点决策为"终止"时，立即跳转到输出验证 |
| 单一答案 | 返回一个最佳答案，不混合多个步骤的结果 |
| 决策树逻辑 | 每个检查点是条件分支，不是顺序执行 |
| 验证必须通过 | 输出验证通过后：有json格式后才能返回结果 |
