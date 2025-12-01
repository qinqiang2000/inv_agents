# 基础数据导出脚本使用说明

## 概述

本脚本使用 **Python + MySQL JSON_ARRAYAGG** 技术，从数据库导出基础数据到 JSON 文件。

相比旧的 Bash 脚本（800+ 行），新脚本仅 ~300 行，更简洁、稳定、易维护。

## 特性

✅ **数据正确性**：使用 MySQL JSON_ARRAYAGG，自动处理特殊字符转义，无字段错位
✅ **按国家分组**：代码数据按国家分开导出，便于查找
✅ **性能优化**：数据库端生成 JSON，一次查询完成
✅ **易于维护**：Python 代码简洁，类型提示完善

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 执行导出

```bash
./export_basic_data.sh
```

### 3. 查看输出

导出的文件位于 `../context/basic-data/` 目录：

```
context/basic-data/
├── global/                      # 全局数据
│   ├── currencies.json         # 货币数据（42条）
│   └── invoice-types.json      # 发票类型数据（41条）
└── codes/                       # 代码数据（按国家分组）
    ├── uom-codes/              # UOM代码
    │   ├── global.json         # 全局UOM代码（2162条）
    │   ├── CN.json             # 中国特定UOM代码
    │   └── DE.json             # 德国特定UOM代码
    ├── payment-means/          # 支付方式
    │   └── global.json         # 84条
    ├── charge-codes/           # 费用代码
    │   ├── global.json         # 251条
    │   ├── CN.json             # 1条
    │   └── DE.json             # 1条
    ├── duty-tax-fee-category-codes/  # 税费类别
    │   └── global.json         # 19条
    └── tax-category-codes/     # 税种类别
        └── global.json         # 178条
```

## JSON 文件结构

### 全局数据示例（货币）

```json
{
  "meta": {
    "exportTime": "2025-11-30T00:56:38Z",
    "recordCount": 42,
    "scope": "global"
  },
  "currencies": [
    {
      "code": "AED",
      "name": "阿联酋迪拉姆",
      "englishName": "UAE Dirham",
      "symbol": "د.إ",
      "unitPrecision": 2,
      "amountPrecision": 2
    },
    ...
  ]
}
```

### 代码数据示例（UOM代码）

```json
{
  "meta": {
    "exportTime": "2025-11-30T00:56:39Z",
    "recordCount": 2162,
    "scope": "country",
    "country": "global",
    "codeType": "0001"
  },
  "uomCodes": [
    {
      "id": 393,
      "country": "",
      "codeType": "0001",
      "code": "10",
      "name": "group",
      "description": "A unit of count defining the number of groups...",
      "isSystem": 1,
      "active": 1
    },
    ...
  ]
}
```

## 技术细节

### 数据库要求

- MySQL 5.7.22+ 或 8.0+（支持 JSON_ARRAYAGG 函数）

### Python 依赖

- Python 3.6+
- pymysql >= 1.0.0

### 环境变量配置（可选）

```bash
export DB_HOST="jump-test.piaozone.com"
export DB_PORT="3306"
export DB_USER="rnd"
export DB_PASSWORD="your_password"
export DB_NAME="test_jin"
export OUTPUT_DIR="../context/basic-data"
```

## 代码类型说明

| 代码类型 | 名称 | 目录 |
|---------|------|------|
| 0001 | UOM代码 | `codes/uom-codes/` |
| 0003 | 行业代码 | `codes/industry-codes/` |
| 0004 | 支付方式 | `codes/payment-means/` |
| 0005 | 折扣/费用原因代码 | `codes/allowance-reason-codes/` |
| 0006 | 费用代码 | `codes/charge-codes/` |
| 0007 | 税费类别代码 | `codes/duty-tax-fee-category-codes/` |
| 0008 | 税种类别代码 | `codes/tax-category-codes/` |
| 0009 | 免税原因代码 | `codes/tax-exemption-reason-codes/` |

## 故障排查

### 错误：MySQL 版本不支持 JSON_ARRAYAGG

```
ERROR - MySQL 版本 5.6.x 不支持 JSON_ARRAYAGG，需要 5.7.22+ 或 8.0+
```

**解决方案**：升级 MySQL 版本到 5.7.22+ 或 8.0+

### 错误：数据库连接失败

```
ERROR - 数据库错误: (2003, "Can't connect to MySQL server...")
```

**解决方案**：
1. 检查数据库配置（host、port、user、password）
2. 确认网络连接正常
3. 检查数据库是否运行

### 错误：Python 环境缺失

```
错误: 需要 Python 3.6+
```

**解决方案**：安装 Python 3.6 或更高版本

## 对比旧脚本

| 特性 | 旧脚本（Bash） | 新脚本（Python） |
|------|---------------|----------------|
| 代码行数 | 800+ 行 | ~300 行 |
| 数据解析 | AWK tab分隔，易出错 | MySQL JSON_ARRAYAGG，自动处理 |
| 特殊字符 | 手动转义，容易遗漏 | 数据库自动转义 |
| 字段错位问题 | 存在（换行符破坏解析） | 不存在 |
| 按国家分组 | 不支持 | 支持 |
| 维护性 | 困难（复杂的 AWK 逻辑） | 简单（清晰的 Python 代码） |
| 性能 | 中等（应用层解析） | 优秀（数据库端生成） |

## 更新日志

### v2.0.0 (2025-11-30)

- ✨ 完全重构，使用 Python + MySQL JSON_ARRAYAGG
- ✨ 支持按国家分组导出代码数据
- ✨ 修复字段错位问题
- ✨ 代码量减少 75%
- ✨ 性能提升，数据库端生成 JSON
- 🗑️ 删除旧的 Bash 脚本（800+ 行）

### v1.0.0 (2025-11-27)

- 初始版本（Bash + AWK）

## 支持

如有问题或建议，请联系开发团队。
