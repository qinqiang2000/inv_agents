# 快速参考指南

## 一行命令速查

```bash
# 全量导出
./export_invoice_data.sh

# 增量导出（所有租户）
EXPORT_MODE=incremental ./export_invoice_data.sh

# 增量导出（单个租户）
EXPORT_MODE=incremental TENANT_ID=123 ./export_invoice_data.sh

# 测试模式
DRY_RUN=true EXPORT_MODE=incremental TENANT_ID=123 ./export_invoice_data.sh

# 组合使用
EXPORT_MODE=incremental TENANT_ID=456 DRY_RUN=false ./export_invoice_data.sh
```

## 环境变量

| 变量 | 值 | 说明 |
|------|-----|------|
| `EXPORT_MODE` | `full` / `incremental` | 导出模式 |
| `TENANT_ID` | 数字 | 租户ID（可选） |
| `DRY_RUN` | `true` / `false` | 测试模式 |

## 输出位置

```
../context/{tenant_id}/{country}/{date}+{invoice_no}.json
```

## 状态文件

```
../context/.export_state/.last_export_time
```

## 故障排除

```bash
# 清除锁文件
rm -rf ../context/.export_state/.export.lock

# 查看状态文件
cat ../context/.export_state/.last_export_time

# 查看备份
ls -la ../context/.export_state/.last_export_time.backup.*
```
