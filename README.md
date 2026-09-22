# 采访事实核查工作台

面向编辑的事实核查 Web 工作台：录入**事实断言**、**逐字稿片段**与**来源文档**，在断言之间标注
**支持 / 反驳 / 派生**关系，系统自动维护有向证据图，检测**循环引用**、**无来源断言**与
**同一主题下的互斥结论**，并给出可解释的冲突路径。断言可在 **待核查 → 已确认 / 存疑** 间流转，
支持按主题筛选，并可一键导出带完整证据链的 Markdown 核查稿。

技术栈：Python · FastAPI · SQLite · 原生 HTML/JS 单页前端（无外部 CDN 依赖）。

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
docker compose up --build
```

访问 <http://localhost:8000>。SQLite 数据库文件持久化在 `./data/factcheck.db`。

### 方式二：Docker

```bash
docker build -t factcheck-workbench .
docker run -p 8000:8000 -v $(pwd)/data:/app/data factcheck-workbench
```

### 方式三：本地运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**启动时自动初始化数据库**：建表；若库为空，写入一组演示数据（含一处冲突、一处循环引用、
两条无来源断言），便于直接体验分析功能。删除 `data/factcheck.db` 即可重置。

## 功能说明

### 数据模型

| 实体 | 说明 |
| --- | --- |
| 主题 Topic | 核查选题，断言按主题归组、筛选 |
| 来源 Source | 类型为「文档」或「逐字稿」，含标题、发布方、URL、摘录片段 |
| 断言 Claim | 事实断言，关联主题与来源（均可空），状态：待核查 / 已确认 / 存疑 |
| 关系 Relation | 断言间有向边：`supports` 支持、`refutes` 反驳、`derives` 派生自 |

### 证据图语义

- **支持（A 支持 B）**：A 是 B 的佐证，「已确认」状态沿 A → B 正向传播；
- **派生自（A 派生自 B）**：B 是 A 的上游依据，「已确认」状态沿 B → A 传播，溯源沿 A → B 向上；
- **反驳（A 反驳 B）**：A 与 B 互斥。

### 自动分析（冲突分析页 / `GET /api/analysis`）

1. **循环引用**：在全部关系边构成的有向图上检测基本回路（如 A 派生自 B、B 又派生自 A 的循环论证）；
2. **无来源断言**：既未直接关联来源，沿「派生自」链向上也无法抵达任何有来源断言的断言
   （派生环内且无来源同样判定为无法溯源）；
3. **互斥结论冲突**：反驳边两端均被证实（自身已确认，或经支持/派生链由已确认断言传播证实）时，
   输出可解释冲突路径，例如：`#3(已确认) 经「#3 支持 #4」得到证实，#1 本身已确认，但 #4 反驳 #1`；
4. **潜在冲突**：存在反驳边但双方尚未均被证实，提示编辑关注。

### 导出核查稿

导出页选择主题（或全部），预览 / 下载 Markdown 核查稿：按主题分组，每条断言附状态、来源、
摘录与递归展开的证据链（支持 / 派生上游逐级缩进，反驳单独列出），并附该主题的分析摘要。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/topics` · DELETE `/api/topics/{id}` | 主题管理 |
| GET/POST | `/api/sources` · PUT/DELETE `/api/sources/{id}` | 来源管理 |
| GET/POST | `/api/claims?topic_id=&status=` · GET/PUT/DELETE `/api/claims/{id}` | 断言管理（按主题/状态筛选） |
| PATCH | `/api/claims/{id}/status` | 状态流转（pending / confirmed / doubtful） |
| GET/POST | `/api/relations` · DELETE `/api/relations/{id}` | 证据关系管理 |
| GET | `/api/analysis?topic_id=` | 循环引用 / 无来源 / 冲突路径分析 |
| GET | `/api/export/markdown?topic_id=` | 导出 Markdown 核查稿 |
| GET | `/api/health` | 健康检查 |

交互式 API 文档：`http://localhost:8000/docs`。

## 项目结构

```
app/
├── main.py        # FastAPI 入口与 REST 路由
├── database.py    # SQLite 连接、建表、演示数据
├── models.py      # Pydantic 模型与枚举
├── analysis.py    # 证据图分析：循环 / 无来源 / 冲突路径
├── report.py      # Markdown 核查稿生成
└── static/
    └── index.html # 单页前端（断言/来源/主题/证据图/分析/导出）
Dockerfile
docker-compose.yml
requirements.txt
```

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FACTCHECK_DB` | `./data/factcheck.db`（镜像内 `/app/data/factcheck.db`） | SQLite 数据库文件路径 |
