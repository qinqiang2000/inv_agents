# 发票数据导出脚本使用说明

## 概述

`export_invoice_data.py` 是高性能的Python发票数据导出脚本，已完全替代原有的bash脚本。该脚本支持全量导出和增量导出两种模式，具备多线程处理、实时进度显示、压缩输出等高级功能。

**性能提升**: 相比bash脚本提升10-20倍，52,523条记录从数小时缩短至16.5分钟，成功率100%。

## 功能特性

- ✅ **全量导出**: 导出所有开票成功的发票数据
- ✅ **增量导出**: 基于时间戳只导出新增/更新的数据
- ✅ **多线程处理**: 并行处理多个租户-国家分组，大幅提升性能
- ✅ **实时进度**: 使用tqdm显示详细进度条和处理统计
- ✅ **压缩输出**: 支持gzip压缩，节省磁盘空间
- ✅ **状态管理**: 为每个租户独立维护导出时间戳
- ✅ **并发控制**: 防止多个导出进程同时运行
- ✅ **错误处理**: 完善的异常处理和数据验证机制
- ✅ **试运行模式**: 预览导出结果而不实际写入文件

## 环境要求

- Python 3.7+
- MySQL数据库访问权限
- 必要的Python包（见requirements.txt）

## 安装依赖

```bash
pip install -r requirements.txt
```

**requirements.txt内容**:
```
pymysql>=1.0.0
tqdm>=4.0.0
```

## 使用方法

### 1. 查看帮助信息

```bash
python3 export_invoice_data.py --help
```

### 2. 全量导出（默认模式）

导出所有租户的所有发票数据：

```bash
python3 export_invoice_data.py
```

### 3. 增量导出

导出所有租户的增量数据：

```bash
python3 export_invoice_data.py --incremental
```

### 4. 高级选项

```bash
# 多线程处理 + 压缩输出
python3 export_invoice_data.py --threads 8 --compress

# 试运行模式（预览不写入）
python3 export_invoice_data.py --incremental --dry-run

# 限制处理数量（测试用）
python3 export_invoice_data.py --limit 10

# 详细日志模式
python3 export_invoice_data.py --verbose
```

### 5. 组合使用示例

```bash
# 高性能增量导出
python3 export_invoice_data.py --incremental --threads 4 --compress --verbose

# 测试模式验证
python3 export_invoice_data.py --incremental --dry-run --limit 5
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--output-dir`, `-o` | `../context/invoices` | 指定输出目录 |
| `--threads`, `-t` | `4` | 线程数量 |
| `--compress`, `-c` | `False` | 启用gzip压缩 |
| `--incremental`, `-i` | `False` | 增量导出模式 |
| `--dry-run`, `-d` | `False` | 试运行模式 |
| `--limit`, `-l` | `None` | 限制处理分组数量（测试用） |
| `--verbose`, `-v` | `False` | 详细日志模式 |
| `--help`, `-h` | - | 显示帮助信息 |

## 输出目录结构

```
context/
├── invoices/
│   ├── .export_state/              # 状态管理目录
│   │   ├── .last_export_time       # 租户导出时间戳记录
│   │   └── .export.lock           # 并发锁文件
│   └── {tenant_id}/                # 租户目录
│       └── {country_code}/         # 国家目录
│           ├── {date}+{invoice_no}.json     # 发票文件
│           └── {date}+{invoice_no}.json.gz # 压缩发票文件（可选）
└── basic-data/                     # 基础数据目录
    ├── global/                     # 全局数据
    │   ├── currencies.json         # 货币数据
    │   └── invoice-types.json      # 发票类型数据
    └── codes/                      # 代码数据
        ├── uom-codes/              # 单位代码
        ├── tax-category-codes/     # 税种类别代码
        └── payment-means/          # 支付方式
```

### 文件命名规则

- 格式：`{fissue_date}+{finvoice_no}.json`
- 示例：`20250819+CN-FP-0005.json`
- 特殊字符会被替换为下划线

## 状态文件格式

增量导出会为每个租户维护独立的导出时间戳：

```
{tenant_id}|{export_time}|{record_count}|{status}
```

示例：
```
1|2025-12-03 17:04:06|59|SUCCESS
123|2025-12-03 17:05:00|0|SUCCESS
456|2025-12-03 17:06:00|150|SUCCESS
```

## 增量导出机制

1. **时间边界**: 导出时间为当前时间减去5分钟（安全边界），避免捕获正在进行的事务
2. **租户隔离**: 每个租户独立维护导出时间戳
3. **状态更新**: 即使没有新数据，也会更新时间戳到边界时间
4. **并发控制**: 使用文件锁防止多个进程同时导出
5. **自动备份**: 每次增量导出前自动备份状态文件

## 性能对比

### 测试数据: 52,523条发票记录

| 指标 | Bash脚本 | Python脚本 | 提升倍数 |
|------|----------|------------|----------|
| **总耗时** | 数小时（经常卡住） | **16.5分钟** | **10-20x** |
| **成功率** | 不稳定（经常中断） | **100%** | - |
| **内存使用** | 高（管道处理） | **优化的批量处理** | **5-10x** |
| **并发处理** | 不支持 | **多线程支持** | - |
| **进度显示** | 基础文本输出 | **实时进度条** | - |
| **错误处理** | 基础 | **完善异常处理** | - |

### 实际运行结果

```bash
# 全量导出结果示例
==========================================
导出完成!
==========================================
总分组数: 15
成功分组: 15
失败分组: 0
无数据分组: 0
总发票数: 52,523
成功文件: 52,523
失败文件: 0
总耗时: 990.50 秒
平均每张发票处理时间: 0.019 秒
==========================================
```

## 常见使用场景

### 场景1：首次全量导出

```bash
cd script
python3 export_invoice_data.py
```

### 场景2：定时增量同步（所有租户）

```bash
# 添加到 crontab，每10分钟执行一次
*/10 * * * * cd /path/to/script && python3 export_invoice_data.py --incremental
```

### 场景3：高性能导出

```bash
# 使用更多线程和压缩
python3 export_invoice_data.py --threads 8 --compress
```

### 场景4：测试验证

```bash
# 试运行模式验证
python3 export_invoice_data.py --incremental --dry-run --limit 5

# 详细日志调试
python3 export_invoice_data.py --incremental --verbose --limit 3
```

### 场景5：重置租户导出状态

如果需要重新导出某个租户的数据：

```bash
# 1. 编辑状态文件，删除该租户的记录
vi ../context/invoices/.export_state/.last_export_time

# 2. 执行增量导出（会从1970-01-01开始）
python3 export_invoice_data.py --incremental
```

## 迁移指南（从Bash到Python）

### 命令对照表

| Bash脚本命令 | Python脚本等效命令 | 说明 |
|--------------|-------------------|------|
| `./export_invoice_data.sh` | `python3 export_invoice_data.py` | 全量导出 |
| `EXPORT_MODE=incremental ./export_invoice_data.sh` | `python3 export_invoice_data.py --incremental` | 增量导出 |
| `DRY_RUN=true ./export_invoice_data.sh` | `python3 export_invoice_data.py --dry-run` | 试运行模式 |
| `TENANT_ID=123 ./export_invoice_data.sh` | `python3 export_invoice_data.py --incremental`（暂不支持单租户） | 指定租户 |

### 新增功能

Python脚本提供了bash脚本没有的功能：

- **多线程处理**: `--threads 8`
- **压缩输出**: `--compress`
- **详细日志**: `--verbose`
- **限制测试**: `--limit 10`
- **更好的进度显示**: 实时进度条和统计信息

### 环境变量迁移

Bash脚本使用的环境变量在Python脚本中已改为命令行参数：

| Bash环境变量 | Python命令行参数 |
|-------------|------------------|
| `EXPORT_MODE=incremental` | `--incremental` |
| `DRY_RUN=true` | `--dry-run` |
| `PROGRESS_INTERVAL=10` | 内置实时进度条 |

## 错误处理

### 并发冲突

如果遇到文件锁错误：

```bash
# 检查是否有其他导出进程在运行
ps aux | grep export_invoice_data.py

# 如果确认没有其他进程，手动删除锁文件
rm -f ../context/invoices/.export_state/.export.lock
```

### 状态文件问题

脚本会自动处理状态文件问题：

```bash
# 查看备份文件
ls -la ../context/invoices/.export_state/.last_export_time.backup.*

# 手动恢复（如果需要）
cp ../context/invoices/.export_state/.last_export_time.backup.* ../context/invoices/.export_state/.last_export_time
```

### 数据库连接问题

```bash
# 检查数据库连接配置
python3 -c "
import pymysql
from export_invoice_data import DB_CONFIG
try:
    conn = pymysql.connect(**DB_CONFIG)
    print('数据库连接正常')
    conn.close()
except Exception as e:
    print(f'数据库连接失败: {e}')
"
```

### 权限问题

确保脚本有写入输出目录的权限：

```bash
chmod 755 export_invoice_data.py
chmod -R 755 ../context/
```

## 最佳实践

### 1. 性能优化

- **线程数设置**: 根据CPU核心数设置，推荐4-8个线程
- **压缩输出**: 对于大量数据建议启用压缩
- **增量导出**: 生产环境建议使用增量导出模式

### 2. 监控和维护

- **定期检查状态文件**: 确保增量导出正常工作
- **监控日志**: 使用`--verbose`模式查看详细执行情况
- **备份数据**: 定期备份导出的发票数据

### 3. 故障恢复

- **状态文件备份**: 脚本会自动备份状态文件
- **断点续传**: 增量导出支持从上次中断处继续
- **数据验证**: 脚本包含JSON格式验证和字段检查

## 技术架构

- **数据库连接**: 使用PyMySQL连接池
- **批量查询**: 使用MySQL的JSON_ARRAYAGG进行聚合查询
- **多线程处理**: ThreadPoolExecutor实现并发处理
- **进度显示**: tqdm库实现实时进度条
- **状态管理**: 基于文件的锁机制和时间戳管理
- **错误处理**: 完善的异常捕获和恢复机制

## 基础数据导出脚本

除了发票数据导出，还提供基础数据导出功能：

### export_basic_data.py

用于导出基础数据（货币、发票类型、代码表等）到JSON文件：

```bash
python3 export_basic_data.py
```

**功能特性**:
- ✅ 导出全局数据：货币、发票类型
- ✅ 导出代码表：UOM代码、税种类别代码、支付方式等，按国家分组
- ✅ 使用MySQL JSON_ARRAYAGG聚合查询
- ✅ 自动创建输出目录结构

**输出目录**:
```
context/
└── basic-data/
    ├── global/
    │   ├── currencies.json         # 货币数据
    │   └── invoice-types.json      # 发票类型数据
    └── codes/
        ├── uom-codes/              # 单位代码（按国家）
        ├── tax-category-codes/     # 税种类别代码（按国家）
        └── payment-means/          # 支付方式（按国家）
```

**环境变量**:
- `OUTPUT_DIR`: 指定输出目录（默认：../context/basic-data）
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: 数据库连接配置

## 版本历史

- **v2.0** - Python版本，完全重写，性能提升10-20倍
- **v1.x** - Bash版本，已弃用