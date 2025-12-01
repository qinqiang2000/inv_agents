# Invoice Field Recommender Agent

基于Claude Agent SDK的UBL发票字段智能推荐系统 - 生产就绪版本

## 功能特性

- **REST API**: 提供标准的HTTP API接口，支持前端调用
- **SSE流式传输**: 实时流式返回Claude的响应
- **会话管理**: 支持多轮对话，前端维护sessionId
- **Skill集成**: 内置invoice-field-recommender skill
- **测试UI**: 提供完整的Web聊天界面用于测试

## 快速开始

### 1. 安装依赖

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 启动服务

```bash
# 使用启动脚本 (推荐)
./run.sh

# 或手动启动
cd /Users/qinqiang02/colab/codespace/ai/invoice_engine_3rd/agents
source .venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 访问服务

- **Chat UI**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/health

## API使用说明

### POST /api/query

发送查询请求给Claude Agent

**请求示例**:

```json
{
  "tenant_id": "1",
  "prompt": "推荐unitCode for 咖啡机",
  "skill": "invoice-field-recommender",
  "language": "中文",
  "session_id": null,
  "country_code": "MY"
}
```

**参数说明**:

- `tenant_id` (必填): 租户ID，字符串类型，如 "1", "10", "89"
- `prompt` (必填): 用户的查询内容
- `skill` (可选): 要使用的skill名称，默认为 "invoice-field-recommender"
- `language` (可选): 响应语言，默认 "中文"
- `session_id` (可选): 会话ID，用于继续之前的对话，新对话时传null
- `country_code` (可选): 国家代码，如 "MY", "DE", "SG"

**响应格式** (Server-Sent Events):

```
event: session_created
data: {"session_id": "abc-123-xyz"}

event: assistant_message
data: {"content": "正在查找相关数据..."}

event: tool_use
data: {"tool": "Grep", "input": "..."}

event: assistant_message
data: {"content": "推荐值：XPP (Piece)"}

event: result
data: {"session_id": "abc-123-xyz", "duration_ms": 5234, "is_error": false, "num_turns": 2}
```

## 会话管理

### 新对话

```json
{
  "tenant_id": "1",
  "prompt": "推荐unitCode for 咖啡机",
  "session_id": null
}
```

后端会返回 `session_created` 事件，包含新的 `session_id`

### 继续对话

```json
{
  "tenant_id": "1",
  "prompt": "那税率是多少？",
  "session_id": "abc-123-xyz"
}
```

使用之前获得的 `session_id`，Claude会记住之前的上下文

## 前端集成示例

```javascript
async function queryAgent(tenantId, prompt, sessionId = null) {
    const response = await fetch('/api/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            tenant_id: tenantId,
            prompt: prompt,
            skill: 'invoice-field-recommender',
            language: '中文',
            session_id: sessionId
        })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const {done, value} = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        // 解析SSE格式
        const lines = chunk.split('\n');
        for (const line of lines) {
            if (line.startsWith('data:')) {
                const data = JSON.parse(line.substring(5));

                if (data.session_id && !sessionId) {
                    // 保存新会话ID
                    sessionId = data.session_id;
                }

                if (data.content) {
                    // 显示消息
                    console.log('Claude:', data.content);
                }
            }
        }
    }

    return sessionId;
}
```

## 项目结构

```
agents/
├── app.py                 # FastAPI主应用
├── api/                   # API实现
│   ├── __init__.py
│   ├── models.py          # Pydantic数据模型
│   ├── endpoints.py       # API路由处理
│   └── agent_service.py   # Claude SDK集成
├── tests/                 # 测试文件
│   ├── __init__.py
│   ├── test_api.py        # API测试脚本
│   └── test_query.sh      # Shell测试脚本
├── script/                # 数据导出工具
│   ├── export_basic_data.py
│   ├── export_invoice_data.sh
│   └── ...
├── static/                # Web UI资源
│   └── chat.html
├── context/               # 上下文数据 (历史发票 + 基础数据)
├── .claude/               # Skill配置
├── requirements.txt       # Python依赖
├── quick_start.py         # SDK示例脚本
└── run.sh                 # 启动脚本
```

## 关键特性说明

### 1. 无状态后端

- 后端不存储会话数据
- sessionId由前端维护
- Claude SDK内部处理会话持久化

### 2. SSE流式传输

- 实时返回Claude的思考过程
- 显示工具调用（Grep、Read等）
- 更好的用户体验

### 3. 工作目录

服务器**必须**在 `/Users/qinqiang02/colab/codespace/ai/invoice_engine_3rd/agents` 目录运行，因为：
- Claude SDK需要加载 `CLAUDE.md`
- Skill路径相对于当前目录
- 上下文数据在 `./context/`

### 4. Prompt组装

新会话时，后端自动组装prompt：

```
# 上下文
租户：1
要使用的skill：invoice-field-recommender

# 任务
{用户的prompt}

# 约束
所有的输出使用语言：中文
```

继续对话时，直接传递用户prompt，Claude会记住上下文

## 测试

### 使用Web UI测试

1. 访问 http://localhost:8000
2. 配置租户ID、国家代码等参数
3. 输入问题，如："推荐unitCode for 咖啡机"
4. 查看实时响应
5. 继续对话测试会话管理

### 使用Python脚本测试

```bash
python tests/test_api.py
```

### 使用curl测试

```bash
./tests/test_query.sh

# 或直接使用curl
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

## 生产部署注意事项

1. **CORS配置**: 修改 `app.py` 中的 `allow_origins` 为具体域名
2. **日志**: 配置生产级日志系统
3. **监控**: 添加性能监控和告警
4. **认证**: 添加API密钥认证
5. **限流**: 实施请求速率限制
6. **HTTPS**: 使用反向代理（Nginx）配置HTTPS

## 故障排查

### 端口被占用

```bash
# 查找占用8000端口的进程
lsof -i :8000

# 杀死进程
kill -9 <PID>
```

### 依赖安装失败

```bash
# 清理并重新安装
pip uninstall -r requirements.txt -y
pip install -r requirements.txt
```

### 上下文数据访问失败

确保工作目录正确：
```bash
cd /Users/qinqiang02/colab/codespace/ai/invoice_engine_3rd/agents
./run.sh
```

## 开发参考

- [FastAPI文档](https://fastapi.tiangolo.com/)
- [Claude Agent SDK文档](https://platform.claude.com/docs/en/agent-sdk)
- [SSE规范](https://html.spec.whatwg.org/multipage/server-sent-events.html)
