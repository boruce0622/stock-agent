# StockPilot 股票研究 Agent

StockPilot 是一个面向沪、深、北交易所 A 股的本地股票研究应用。系统使用大模型理解问题、规划研究步骤并综合回答，同时通过可追溯工具获取实时行情、K 线和新闻证据。知识库只作为可选补充，不会因为本地知识未命中而阻断行情研究或一般性解释。

技术栈：LangGraph、LangChain、FastAPI、SQLAlchemy、SQLite、Vue 3、Element Plus、Vite。

> 本项目仅用于信息与教育目的，不执行交易，不承诺收益，也不构成投资建议。公开网络数据源可能延迟、变更或不可用，重要信息请通过交易所公告及持牌数据服务再次核验。

详细设计和产品边界见 [DESIGN.md](./DESIGN.md)。

## 功能概览

- AI 主导研究：模型识别意图与标的，从受限工具集合中选择行情、K 线、分时、舆情和知识库，再基于工具证据生成回答。
- 全市场标的解析：支持股票名称、简称和代码；覆盖沪市主板、深市主板、科创板、创业板和北交所，包括北交所现行 `920` 代码。
- 多源行情降级：实时行情、历史 K 线、分时和新闻均设置超时、重试、限速及备用数据源。
- 多轮对话记忆：保存会话消息及当前股票；追问“它怎么样”“风险呢”时可沿用当前标的。
- 可恢复运行：Agent Run、消息和工具调用持久化到 SQLite；服务重启后会重新调度未完成任务，终态 SSE 事件可从数据库恢复。
- 流式交互：通过 SSE 展示规划、取证、综合等安全阶段状态，支持取消和断线重连。
- 本地 RAG：按需检索市场规则、指标与风险知识；无命中时不会冒充知识库内容，也不会阻止其他证据继续分析。
- 管理界面：可在前端配置并测试 OpenAI 兼容模型及公网行情模式，API Key 加密保存。
- 行情看板：查看 K 线、成交量及近期新闻倾向。
- 页面体验：刷新后恢复最近使用的会话并直接定位到最新消息，切换会话时不从顶部滚动。

## 工作方式

一次股票研究按以下顺序运行：

1. 程序先尝试解析用户输入和当前会话标的。
2. LLM 根据问题和候选标的生成受限 JSON 计划，决定 `stock_query`、研究重点和所需工具。
3. 编排层以 LLM 给出的 `stock_query` 重新解析标的；有效结果优先于初步候选。
4. 工具层查询事实证据，并执行格式归一化、超时、重试和降级。
5. LLM 只能使用已提供证据中的实时数字完成综合；引用行情、K 线和舆情时分别标注 `[行情]`、`[K线]`、`[舆情]`。
6. 应用层统一追加风险提示，保存回答、运行状态和工具审计信息。

这套设计的原则是“模型主导研究，工具提供事实”。模型可以识别标的、组织逻辑和提出假设，但不能把自身记忆当成实时行情。

## 数据源与降级策略

| 能力 | 首选来源 | 降级来源 |
|---|---|---|
| 股票名称解析 | 本地确定性规则、腾讯证券搜索 | 临时上市名称匹配、东方财富证券目录 |
| 实时行情 | 腾讯财经 | 新浪财经、AKShare |
| 实时行情校验 | Baostock 最近交易日日线 | 校验不可用时保留实时结果并标记状态 |
| 日 K 线 | 东方财富 `push2his` | Baostock、AKShare 新浪日线 |
| 分时 | 东方财富 `push2his` | AKShare 新浪分钟线 |
| 新闻舆情 | AKShare 个股新闻 | 返回可用证据或明确失败 |
| 知识解释 | `backend/knowledge/*.md` | 模型的一般知识解释，禁止伪造知识库引用 |

舆情标签由透明关键词规则生成，只表示新闻文本倾向，不代表投资评级。AKShare 及网页公开接口可能因上游调整而失效，不提供生产级 SLA；正式部署前应确认数据许可和使用条款。

## 项目结构

```text
stock-agent/
├── backend/
│   ├── app/
│   │   ├── agent/          LangGraph 状态图与研究工具
│   │   ├── api/v1/         会话、运行、配置、行情和知识库 API
│   │   ├── db/             SQLAlchemy 模型与数据库会话
│   │   ├── llm/            OpenAI 兼容模型网关与供应商目录
│   │   ├── providers/      行情、历史数据、新闻与标的解析适配器
│   │   ├── rag/            本地知识检索
│   │   └── services/       运行调度、恢复及配置服务
│   ├── knowledge/          Markdown 知识文档
│   ├── tests/              后端测试
│   ├── pyproject.toml
│   └── start.ps1
├── frontend/
│   ├── public/             浏览器图标等静态资源
│   ├── src/                Vue 页面、组件、API 与测试
│   ├── package.json
│   └── start.ps1
├── DESIGN.md
└── README.md
```

## 环境要求

- Windows PowerShell 7 或 Windows PowerShell 5.1
- Python 3.11 或更高版本
- Node.js 20.19+ 或 22.12+，附带 npm（与 Vite 7 要求一致）
- 可访问所配置模型服务及公开行情数据源的网络环境

项目启动脚本会自动创建根目录 `.venv`，并在依赖缺失时安装所需包。

## 快速开始

### 1. 配置后端环境

```powershell
Copy-Item .\backend\.env.example .\backend\.env
```

开发环境可直接启动，但建议立即修改 `backend/.env` 中的 `APP_ENCRYPTION_KEY`。这个密钥用于加密数据库里的模型 API Key；密钥丢失后，原有 API Key 将无法解密。

可以用 Python 生成随机密钥：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. 启动后端

```powershell
.\backend\start.ps1
```

- API：`http://127.0.0.1:9010`
- Swagger：`http://127.0.0.1:9010/docs`
- 健康检查：`http://127.0.0.1:9010/api/v1/health/live`
- SQLite：`backend/data/stock_agent.db`

首次运行会安装依赖。需要强制重新安装时：

```powershell
.\backend\start.ps1 -Install
```

其他参数：

```powershell
.\backend\start.ps1 -Port 9011
.\backend\start.ps1 -BindAddress 0.0.0.0 -NoReload
```

开发模式默认启用 Uvicorn reload。修改后端代码后应确认服务已完成重载；若未使用 reload 或运行状态异常，请停止进程后重新执行启动脚本。

### 3. 启动前端

另开一个 PowerShell 窗口：

```powershell
.\frontend\start.ps1
```

浏览器访问 `http://localhost:6173`。Vite 会把 `/api` 代理到 `http://127.0.0.1:9010`。

强制重新安装前端依赖或更换端口：

```powershell
.\frontend\start.ps1 -Install
.\frontend\start.ps1 -Port 6174
```

如果更换前端端口，需要同步修改 `backend/.env` 中的 `CORS_ORIGINS`；如果更换后端端口，还需修改 `frontend/vite.config.js` 的代理目标。

### 4. 启用真实模型和行情

应用首次运行时，未启用模型或公网行情会使用确定性的 Fake 模式，方便本地演示和测试。

在页面右上角完成以下配置：

1. 打开“AI 设置”，选择供应商，填写账号实际可用的模型 ID 与 API Key。
2. 非 OpenAI 官方接口需要填写对应的 OpenAI 兼容 Base URL。
3. 点击“测试连接”，通过后保存并启用。
4. 打开“行情设置”，点击“测试实时行情”，通过后保存并启用多源公网行情。

内置模型供应商预设：

| 供应商 | 默认兼容地址 | 示例模型 |
|---|---|---|
| OpenAI | SDK 默认地址 | 以账号实际可用模型为准 |
| DeepSeek | `https://api.deepseek.com` | `deepseek-v4-flash`、`deepseek-v4-pro` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2` |
| Kimi | `https://api.moonshot.cn/v1` | `kimi-k3`、`kimi-k2.6` |
| MiniMax | `https://api.minimaxi.com/v1` | `MiniMax-M2.7`、`MiniMax-M2.7-highspeed` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 豆包 | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-0-lite-260215` |
| 自定义 | 用户填写 | OpenAI Chat Completions 兼容模型 |

供应商、地址和模型 ID 都可能变化，以上示例以代码内预设为准，并不保证账号一定具有访问权限。

## 环境变量

`backend/.env.example` 提供以下配置：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_ENV` | `development` | 环境名称；非开发/测试环境禁止使用默认加密密钥 |
| `APP_HOST` | `127.0.0.1` | 应用配置中的监听地址 |
| `APP_PORT` | `9010` | 应用配置中的端口；启动脚本参数可覆盖实际监听端口 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/stock_agent.db` | SQLAlchemy 数据库地址，相对于后端工作目录 |
| `CORS_ORIGINS` | `http://localhost:6173` | 允许的前端来源；多个值用逗号分隔 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `APP_ENCRYPTION_KEY` | 示例占位值 | 模型 API Key 的 Fernet 派生密钥，生产必须替换 |
| `LLM_TIMEOUT_SECONDS` | `45` | 单次模型请求超时 |
| `LLM_MAX_RETRIES` | `2` | 模型请求重试次数 |
| `LLM_TEMPERATURE` | `0.1` | 模型生成温度 |

模型供应商、模型 ID、Base URL、API Key 及启用状态由设置页写入 SQLite。读取配置的接口只返回掩码后的 Key；修改其他字段时可将 API Key 留空以沿用旧值。

## 多轮对话与持久化

- 每轮运行会加载当前会话最近 20 条已完成消息，最多 12,000 个字符。
- 成功识别的股票保存在会话 `current_symbol` 字段中，后续指代式问题可以复用。
- 会话详情接口返回最新 500 条消息，并按时间正序展示；更早消息仍保存在数据库中。
- 浏览器通过 `localStorage` 记住当前会话，刷新后恢复该会话并立即定位至底部。
- 未完成的 `queued`/`running` 任务会在单进程服务重启时重新调度；已结束任务的 SSE 内容可从数据库重建。
- 进程内 SSE Broker 的终态事件保留 300 秒后清理，数据库记录不受影响。

当前版本没有生成长期会话摘要。超过短期窗口的上下文不会自动压缩进模型提示词，但历史消息仍保留在 SQLite。

## 本地知识库

知识文档位于 `backend/knowledge/*.md`。系统会把 Markdown 按章节切分并建立本地中文检索索引，不需要额外的向量数据库或 Embedding API。

知识库定位是补充市场规则、指标解释和风险边界：

- 有命中时，模型可使用对应 `[知识库N]` 引用。
- 无命中时，模型仍可根据一般知识解释概念，并继续查询行情、K 线和舆情。
- 模型不得把一般知识伪装成知识库内容，也不得伪造引用编号。

独立测试检索：

```text
GET /api/v1/knowledge/search?q=市盈率怎么理解
GET /api/v1/knowledge/search?q=科创板代码规则
```

添加或修改 Markdown 文档后需要重启后端以重建索引。建议为文档标注更新时间，并用二级标题拆分独立主题。

## 常用 API

完整参数和响应结构请查看 Swagger。常用接口如下：

### 会话与运行

```text
POST /api/v1/conversations
GET  /api/v1/conversations
GET  /api/v1/conversations/{conversation_id}/messages
POST /api/v1/conversations/{conversation_id}/runs
GET  /api/v1/runs/{run_id}/events
POST /api/v1/runs/{run_id}/cancel
```

创建一次运行：

```json
{
  "message": "研究一下中科美菱",
  "client_request_id": "由客户端生成的唯一请求 ID"
}
```

`client_request_id` 用于幂等控制。事件流可能包含 `run.status`、`tool.result`、`message.delta`、`message.completed`、`run.cancelled` 和 `run.error`。

### 行情与标的解析

```text
GET /api/v1/market-data/resolve?q=中科美菱
GET /api/v1/market-data/quote/920992
GET /api/v1/market-data/kline/920992?period=daily&adjust=forward&limit=120
GET /api/v1/market-data/intraday/600519?days=1
GET /api/v1/market-data/sentiment/601318?limit=12
```

K 线周期支持 `daily`、`weekly`、`monthly`、`1`、`5`、`15`、`30`、`60`；复权方式支持 `none`、`forward` 和 `backward`。股票代码也可以使用规范格式，例如 `600519.SH`、`300750.SZ`、`920992.BJ`。

### 配置与健康检查

```text
GET  /api/v1/health/live
GET  /api/v1/health/ready
GET  /api/v1/ai-config/providers
GET  /api/v1/ai-config
PUT  /api/v1/ai-config
POST /api/v1/ai-config/test
GET  /api/v1/market-config
PUT  /api/v1/market-config
POST /api/v1/market-config/test
```

## 使用示例

- `中科美菱今天表现怎么样？`
- `分析贵州茅台近期走势和新闻驱动`
- `宁德时代近 20 日趋势如何？`
- `什么是市盈率？它有哪些局限？`
- 第一轮：`看看中国平安`；第二轮：`它近期有什么风险？`
- `告诉我哪只股票可以全仓稳赚`（系统会拒绝收益承诺和代客决策）

## 开发与验证

安装后端开发依赖：

```powershell
.\backend\start.ps1 -Install
```

运行后端静态检查和测试：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m pytest -q
Set-Location ..
```

运行前端测试和生产构建：

```powershell
Set-Location .\frontend
npm test
npm run build
Set-Location ..
```

测试默认使用 Fake 行情和测试数据库，不应依赖公网行情的即时可用性。

## 常见问题

### 页面提示 Fake 模式

模型或公网行情尚未启用。分别打开右上角“AI 设置”和“行情设置”，完成连接测试后保存。行情设置关闭时，聊天中的实时工具使用内置 Fake 数据，但独立行情 API 仍会访问公网适配器。

### 股票名称无法识别

优先尝试完整证券名称或六位代码。系统会依次使用本地规则、腾讯搜索、临时上市名称匹配和东方财富证券目录；如果返回多个候选，需要补充代码确认。

### 行情或 K 线暂时失败

公开网页接口可能限流或调整。先重试并查看响应中的 `source`、`fallback_reason` 和错误详情。北交所数据不受 Baostock 完整支持，系统会继续尝试腾讯、东方财富或 AKShare 等可用来源。

### 刷新后仍显示旧配置

确认前后端连接的是同一个数据库和端口。修改 `backend/.env` 或知识文档后需重启后端；修改后端 Python 代码后也应重启或确认 Uvicorn reload 已成功完成。

### API Key 是否安全

Key 使用由 `APP_ENCRYPTION_KEY` 派生的 Fernet 密钥加密后存入 SQLite，读取接口不返回明文。但当前项目没有用户或管理员鉴权，只适合受信任的本地环境。共享部署前必须保护配置 API、数据库文件和加密密钥。

## 当前限制与生产建议

- 当前没有用户体系、权限隔离、管理员鉴权和审计后台。
- SQLite 适合本地单实例；生产环境应使用正式数据库迁移和支持并发的数据库。
- 任务调度与实时 SSE Broker 仍位于单个应用进程。虽然运行状态可恢复，但多 Worker 之间不共享事件；生产环境建议使用 Redis、任务队列和分布式锁。
- 开发启动使用 `create_all` 自动建表，尚未集成 Alembic 迁移。
- 尚未实现长期对话摘要、公司基本面专用工具、组合分析、量化回测或自动交易。
- 公网行情源没有生产 SLA，也不应被视为持牌行情服务。
- 部署到共享或公网环境前，应增加 HTTPS、认证授权、速率限制、密钥管理、监控告警、备份恢复及目标地区合规审核。

## 扩展数据源或模型

1. 在 `backend/app/providers/` 新增适配器，实现 `MarketDataProvider` 协议或相应研究工具接口。
2. 在服务装配层注册新 Provider，并保持统一 `ToolEnvelope`、规范 symbol 和来源字段。
3. 若模型服务兼容 OpenAI Chat Completions，可在设置页使用“自定义兼容接口”。
4. 非兼容协议应在 `backend/app/llm/` 新增网关，不要把供应商细节耦合进 Agent 图。
5. 为解析、降级、错误路径和证据引用补充测试。

## License

仓库当前未包含开源许可证文件。若计划发布或分发，请先选择许可证并添加 `LICENSE`。
