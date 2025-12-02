# 发票数据导出脚本使用说明

## 概述

`export_invoice_data.sh` 是一个用于从数据库导出发票数据的脚本，支持全量导出和增量导出两种模式。

## 功能特性

- ✅ 全量导出：导出所有开票成功的发票数据
- ✅ 增量导出：基于时间戳只导出新增/更新的数据
- ✅ 按租户导出：支持指定单个租户ID进行增量导出
- ✅ 并发控制：防止多个导出进程同时运行
- ✅ 状态管理：为每个租户独立维护导出时间戳
- ✅ 测试模式：DRY_RUN模式可以预览导出结果而不实际写入文件

## 使用方法

### 1. 全量导出（默认模式）

导出所有租户的所有发票数据：

```bash
cd script
./export_invoice_data.sh
```

### 2. 增量导出（所有租户）

导出所有租户的增量数据：

```bash
cd script
EXPORT_MODE=incremental ./export_invoice_data.sh
```

### 3. 增量导出（指定租户）

只导出特定租户的增量数据：

```bash
cd script
EXPORT_MODE=incremental TENANT_ID=123 ./export_invoice_data.sh
```

### 4. 测试模式（不写入文件）

预览导出结果，不实际写入文件：

```bash
cd script
DRY_RUN=true EXPORT_MODE=incremental TENANT_ID=123 ./export_invoice_data.sh
```

## 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `EXPORT_MODE` | `full` | 导出模式：`full`（全量）或 `incremental`（增量） |
| `TENANT_ID` | 空 | 指定租户ID，为空则处理所有租户（仅增量模式有效） |
| `DRY_RUN` | `false` | 测试模式：`true`（不写入文件）或 `false`（正常写入） |

## 输出目录结构

```
context/
├── .export_state/              # 状态管理目录
│   ├── .last_export_time       # 租户导出时间戳记录
│   └── .export.lock/           # 并发锁目录
├── {tenant_id}/                # 租户目录
│   └── {country}/              # 国家目录
│       └── {date}+{invoice_no}.json  # 发票文件
```

### 文件命名规则

- 格式：`{fissue_date}+{finvoice_no}.json`
- 示例：`20231215+INV-2023-001.json`
- 特殊字符会被替换为下划线

## 状态文件格式

`.last_export_time` 文件记录每个租户的导出状态：

```
{tenant_id}|{export_time}|{record_count}|{status}
```

示例：
```
123|2024-12-02 10:30:00|150|SUCCESS
456|2024-12-02 10:31:00|0|SUCCESS
789|2024-12-02 10:32:00|0|FAILED
```

## 增量导出机制

1. **时间边界**：导出时间为当前时间减去5分钟（安全边界），避免捕获正在进行的事务
2. **租户隔离**：每个租户独立维护导出时间戳
3. **状态更新**：即使没有新数据，也会更新时间戳到边界时间
4. **并发控制**：使用锁目录防止多个进程同时导出

## 常见使用场景

### 场景1：首次全量导出

```bash
cd script
./export_invoice_data.sh
```

### 场景2：定时增量同步（所有租户）

```bash
# 添加到 crontab，每10分钟执行一次
*/10 * * * * cd /path/to/script && EXPORT_MODE=incremental ./export_invoice_data.sh
```

### 场景3：单租户数据修复

```bash
# 先测试
DRY_RUN=true EXPORT_MODE=incremental TENANT_ID=123 ./export_invoice_data.sh

# 确认无误后执行
EXPORT_MODE=incremental TENANT_ID=123 ./export_invoice_data.sh
```

### 场景4：重置租户导出状态

如果需要重新导出某个租户的数据：

```bash
# 1. 编辑状态文件，删除该租户的记录
vi ../context/.export_state/.last_export_time

# 2. 执行增量导出（会从1970-01-01开始）
EXPORT_MODE=incremental TENANT_ID=123 ./export_invoice_data.sh
```

## 错误处理

### 锁文件冲突

如果遇到锁文件错误：

```bash
rm -rf ../context/.export_state/.export.lock
```

### 状态文件损坏

脚本会自动备份并重建损坏的状态文件：

```bash
# 查看备份文件
ls -la ../context/.export_state/.last_export_time.backup.*
```

### 磁盘空间不足

脚本会在执行前检查磁盘空间（至少需要100MB）

## 注意事项

1. **数据库密码**：脚本中包含明文密码，请确保文件权限设置正确（建议 `chmod 700`）
2. **并发执行**：增量模式下使用锁机制，不要强制删除锁文件
3. **时间边界**：增量导出有5分钟延迟，确保数据一致性
4. **状态备份**：每次增量导出前会自动备份状态文件
5. **租户ID格式**：确保 TENANT_ID 与数据库中的 ftenant_id 格式一致

## Bug修复记录

### 已修复的Bug

1. **临时文件名错误**：修复了 `update_export_time()` 函数中的临时文件名变量（`tmp.$` → `tmp.$$`）
2. **正则表达式截断**：修复了状态文件格式验证的正则表达式
3. **变量作用域问题**：修复了管道子shell导致的计数器不准确问题（使用临时文件替代管道）

## 性能优化建议

1. 对于大量租户，建议分批次执行增量导出
2. 可以并行执行多个租户的导出（需要修改脚本支持）
3. 定期清理旧的备份文件和临时文件
