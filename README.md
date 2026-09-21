# 🔍 采访事实核查 Web 工作台

为编辑/事实核查记者设计的轻量工作台：录入**事实断言**、**逐字稿片段**与**来源文档**，
在断言之间标记 **支持 / 反驳 / 派生自** 关系，系统维护一张**有向证据图**，自动检测

- 🔁 **循环引用**（支持、派生边上的有向环）
- ⚔ **同一主题的互斥结论**（净反驳路径，给出逐步可解释的冲突链）
- 📭 **无来源断言**（含沿“派生自”链向上的传递证据追溯）

断言可在 **待核查 → 已确认 / 存疑** 间流转，支持按主题筛选，并导出带完整证据链的
**Markdown 核查稿**。

技术栈：Python · FastAPI · SQLite · 原生 HTML/CSS/JS（无构建步骤）。

---

## 快速开始

### Docker Compose（推荐）

```bash
docker compose up -d --build
# 打开 http://localhost:8000
```

SQLite 数据库保存在命名卷 `fc-data`（容器内 `/data/factcheck.db`）。
首次启动会自动建表并写入一组演示数据（含冲突路径与循环引用示例）。
设置环境变量 `SEED_SAMPLE=0` 可关闭演示数据。

### 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 打开 http://localhost:8000
```

本地运行时数据库默认写入 `./data/factcheck.db`（可用环境变量 `FC_DATABASE` 覆盖）。

---

## 使用指南

| 模块 | 能做什么 |
| --- | --- |
| 📊 核查总览 | 状态统计；互斥结论、循环引用、无来源断言三类问题清单及可解释路径 |
| 📌 断言 | 新建/编辑/删除断言；状态流转；挂载来源/逐字稿证据；建立断言间关系 |
| 📄 来源文档 | 管理政府通报、论文、网页等来源（标题、发布方、日期、URL、摘要） |
| 🎙 逐字稿片段 | 管理采访录音的文字片段（说话人、采访人、日期、原文） |
| 🕸 证据图 | 力导向有向图：绿色=支持，红色=反驳，蓝色=派生自；点击节点查看断言 |
| 📝 导出 | 按主题（或全部）预览并下载 Markdown 核查稿 |

### 核查工作流建议

1. 把采访中出现的每个**事实主张**录成断言，归入同一“主题”；
2. 给断言挂载**逐字稿片段**（原始说法）与**来源文档**（外部佐证），附引文定位；
3. 在断言间标注关系：
   - `A ─支持→ B`：A 为 B 提供依据；
   - `A ─反驳→ B`：A 与 B 结论互斥；
   - `A ─派生自→ B`：A 是从 B 推导而来（证据可向上继承）；
4. 在“核查总览”查看三类问题，沿冲突路径定位矛盾；
5. 核查完成后将状态改为**已确认**或**存疑**，导出 Markdown 稿件交编辑会讨论。

---

## 检测规则说明

### 循环引用

在 `supports` + `derived_from` 两类**依赖边**构成的图上枚举简单有向环
（如 `#1 → #4 → #3 → #1`）。环上的断言互为依据、缺乏独立证据，会在总览与导出稿中逐条列出。
`refutes` 边不参与环检测——互相反驳属于“冲突”而非“循环论证”。

### 互斥结论与冲突路径

仅在**同一主题**内比较断言对。路径上每条边都传递结论极性：

- `supports` / `derived_from` 保持极性（+1）；
- `refutes` 翻转极性（−1）。

若两断言之间存在一条有向路径、其上 `refutes` 边数为**奇数**，说明它们沿证据图**净反驳**，
即构成互斥结论。系统输出最短路径的逐步链条与自然语言解释，并按端点状态定级：

| 级别 | 条件 |
| --- | --- |
| 🔴 高危 | 两端均为“已确认” |
| 🟠 需关注 | 一端“已确认” |
| 🟡 待观察 | 两端均未确认 |

路径搜索上限为 4 跳，避免大图上的组合膨胀。

### 无来源断言与传递证据链

断言没有直接挂载任何来源/逐字稿证据时，系统沿 `derived_from` 边向上 BFS：
- 若上游祖先断言有证据 → 证据可经派生链继承（详情页展示追溯链）；
- 若整条派生链都无证据 → 标记为“无来源断言”。

### 导出的 Markdown 包含

统计概览 → 互斥冲突及路径 → 循环引用 → 无来源清单 → 每条断言的状态、证据（含引文）、
派生证据链与全部关系。

---

## HTTP API 摘要

交互式文档：启动后访问 `http://localhost:8000/docs`（Swagger UI）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/assertions` | 断言列表（`?topic=&status=` 过滤） |
| POST | `/api/assertions` | 新建断言 |
| GET | `/api/assertions/{id}` | 断言详情（证据、关系、派生证据链） |
| PATCH | `/api/assertions/{id}` | 编辑 / 状态流转 |
| DELETE | `/api/assertions/{id}` | 删除（级联移除证据挂载与关系） |
| POST | `/api/assertions/{id}/evidence` | 挂载来源/逐字稿证据 |
| DELETE | `/api/assertions/{id}/evidence/{eid}` | 移除证据挂载 |
| POST | `/api/assertions/relations` | 建立 支持/反驳/派生自 关系 |
| DELETE | `/api/assertions/relations/{rid}` | 删除关系 |
| GET/POST/PATCH/DELETE | `/api/sources[...]` | 来源文档 CRUD |
| GET/POST/PATCH/DELETE | `/api/transcripts[...]` | 逐字稿片段 CRUD |
| GET | `/api/analysis` | 循环 / 冲突 / 无来源分析（`?topic=`） |
| GET | `/api/graph` | 力导向图节点与边（`?topic=`） |
| GET | `/api/export/markdown` | 导出 Markdown（`?topic=`） |
| GET | `/api/health` | 健康检查 |

---

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FC_DATABASE` | `/data/factcheck.db`（容器）/ `./data/factcheck.db`（本地回退） | SQLite 文件路径 |
| `SEED_SAMPLE` | `1` | 数据库为空时是否写入演示数据（`0` 关闭） |

## 项目结构

```
app/
  main.py          FastAPI 入口（lifespan 中初始化数据库 + 种子数据）
  database.py      SQLite 连接与 schema
  models.py        Pydantic 模型
  graph.py         证据图分析：循环 / 冲突路径 / 证据闭包
  report.py        Markdown 核查稿生成
  seed.py          演示数据
  routers/         assertions / sources / transcripts / analysis / export
  seed.py          演示数据
tests/             图算法规格测试 + HTTP 端到端冒烟测试
static/
  index.html       单页前端
  styles.css
  app.js           列表、表单、详情模态框、力导向图、导出预览
Dockerfile
docker-compose.yml
requirements.txt
```

## 重置数据

```bash
docker compose down -v          # 删除数据库卷后重新启动
# 本地：rm data/factcheck.db
```

## 测试

无需额外依赖（纯标准库）：

```bash
# 1) 图算法规格测试（环去重、极性冲突、派生证据闭包、严重度）
python3 tests/test_graph.py

# 2) HTTP 端到端冒烟测试（先启动服务，使用独立主题前缀，结束自动清理）
uvicorn app.main:app --port 8000 &
python3 tests/test_api_e2e.py
```
