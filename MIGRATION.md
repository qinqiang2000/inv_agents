# 服务器迁移指南

本文档描述如何将其他服务器（同版本）的数据目录从旧结构迁移到新结构。

## 变更概述

| 旧路径 | 新路径 |
|-------|--------|
| `context/basic-data/` | `data/basic-data/` |
| `tenant-data/{tenant_id}/` | `data/tenants/{tenant_id}/` |

## 迁移步骤

### 1. 停止服务

```bash
# 停止 uvicorn 服务
pkill -f "uvicorn app:app" || true
```

### 2. 拉取最新代码

```bash
cd /path/to/invoice_engine_3rd/agents
git pull origin main
```

### 3. 创建新目录结构

```bash
mkdir -p data/basic-data data/tenants
```

### 4. 迁移数据

```bash
# 迁移公共基础数据
mv context/basic-data/* data/basic-data/

# 迁移租户数据（包括隐藏文件）
mv tenant-data/* data/tenants/
mv tenant-data/.export_state data/tenants/ 2>/dev/null || true
```

### 5. 清理旧目录

```bash
rm -rf context/ tenant-data/
```

### 6. 验证目录结构

```bash
tree -L 2 data/
# 应该看到:
# data/
# ├── basic-data
# │   ├── codes
# │   └── global
# └── tenants
#     ├── 1
#     ├── 10
#     └── ...
```

### 7. 重启服务

```bash
./run.sh
```

### 8. 验证服务

```bash
# 测试 API
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

## 一键迁移脚本

将以下脚本保存为 `migrate_to_new_structure.sh` 并执行：

```bash
#!/bin/bash
set -e

echo "=== 开始迁移数据目录结构 ==="

# 检查是否在正确的目录
if [ ! -f "CLAUDE.md" ] || [ ! -d "api" ]; then
    echo "错误: 请在 agents/ 目录下执行此脚本"
    exit 1
fi

# 检查旧目录是否存在
if [ ! -d "context" ] && [ ! -d "tenant-data" ]; then
    echo "旧目录不存在，可能已经迁移过了"
    exit 0
fi

# 创建新目录
echo "创建新目录结构..."
mkdir -p data/basic-data data/tenants

# 迁移数据
if [ -d "context/basic-data" ]; then
    echo "迁移 context/basic-data -> data/basic-data..."
    mv context/basic-data/* data/basic-data/ 2>/dev/null || true
fi

if [ -d "tenant-data" ]; then
    echo "迁移 tenant-data -> data/tenants..."
    # 迁移所有内容（包括隐藏文件）
    shopt -s dotglob
    mv tenant-data/* data/tenants/ 2>/dev/null || true
    shopt -u dotglob
fi

# 清理旧目录
echo "清理旧目录..."
rm -rf context/ tenant-data/

# 验证
echo ""
echo "=== 迁移完成 ==="
echo "新目录结构:"
tree -L 2 data/ 2>/dev/null || ls -la data/

echo ""
echo "请执行 ./run.sh 启动服务并验证"
```

## 回滚步骤（如需）

如果需要回滚到旧结构：

```bash
# 创建旧目录
mkdir -p context/basic-data tenant-data

# 还原数据
mv data/basic-data/* context/basic-data/
mv data/tenants/* tenant-data/

# 清理新目录
rm -rf data/

# 回滚代码
git checkout HEAD~1 -- api/agent_service.py api/endpoints.py CLAUDE.md .claude/skills/
```

## 注意事项

1. **数据量**：租户 1 有约 600MB 数据，迁移可能需要几分钟
2. **磁盘空间**：确保有足够的磁盘空间（至少 1GB 可用）
3. **导出脚本**：迁移后，增量导出脚本会自动使用新路径
4. **服务中断**：迁移期间服务不可用，建议在低峰期执行
