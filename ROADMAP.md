# AI 对话平台 · 项目路线图

> 目标：从 0 到 1 完成一个可用的全栈 AI 对话平台，并在这个过程中真正掌握 FastAPI 全栈开发。
> 你的前置条件：Vue 两年经验（前端是强项）、刚学完 FastAPI 基础。
> 所以本项目的策略是：**前端快速推进、后端深挖细讲**。

---

## 一、技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 前端框架 | Vue 3 + TypeScript + Vite | 你的主场，直接用 `<script setup>` |
| UI 组件 | Element Plus | 表单、弹窗、下拉、消息提示等"重交互"组件 |
| 样式 | TailwindCSS v4 | 布局、间距、颜色等"轻样式"，和 EP 分工明确 |
| 状态管理 | Pinia | 会话列表、消息列表、用户设置 |
| 路由 | Vue Router | 对话页 / 设置页 |
| HTTP | Axios + 原生 fetch | 普通接口用 Axios；**流式接口必须用原生 fetch** |
| 后端框架 | FastAPI | 异步优先，自动生成 `/docs` |
| ORM | SQLAlchemy 2.0（async 模式） | 用 2.0 新语法，别学 1.x 老写法 |
| 数据校验 | Pydantic v2 | 请求/响应模型 |
| 迁移 | Alembic | Phase 2 之后再引入 |
| 数据库 | MySQL 8.0（aiomysql 驱动） | InnoDB + utf8mb4，本机安装服务 |
| LLM 接入 | 硅基流动 SiliconFlow | OpenAI 兼容接口，`openai` SDK + 自定义 base_url |
| 包管理 | 后端 conda 环境 `fastapi_env`；前端 `pnpm` | Python 环境：`D:\anaconda3\envs\fastapi_env` |

**环境现状**：Node 22.19 / pnpm 12.6 / Python 3.11.7 (Anaconda) / git 2.42 ✅

---

## 二、系统架构

```
┌──────────────────────────────────────────────────────────┐
│  浏览器 (Vue 3 + Element Plus + Tailwind)                 │
│                                                          │
│   ┌────────────┐   ┌──────────────┐   ┌───────────────┐  │
│   │ 会话列表    │   │ 消息区        │   │ 输入框         │  │
│   │ (侧边栏)    │   │ Markdown渲染  │   │ 发送/停止      │  │
│   └────────────┘   └──────────────┘   └───────────────┘  │
│         │                  ▲                  │          │
│         │ Axios            │ SSE 流           │ POST     │
└─────────┼──────────────────┼──────────────────┼──────────┘
          │                  │                  │
          ▼                  │                  ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI (uvicorn)                                       │
│                                                          │
│  /api/v1/conversations   ← 会话 CRUD                      │
│  /api/v1/messages        ← 消息查询                       │
│  /api/v1/chat/stream     ← 流式对话 (SSE)  ★核心          │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐   │
│  │ Service 层   │  │ LLM 客户端    │  │ 异常/日志中间件  │   │
│  │ 业务逻辑     │  │ httpx/openai │  │                │   │
│  └─────────────┘  └──────┬───────┘  └────────────────┘   │
│         │                │                               │
│  ┌─────────────┐         │                               │
│  │ Repository  │         │                               │
│  └──────┬──────┘         │                               │
└─────────┼────────────────┼───────────────────────────────┘
          │                │
          ▼                ▼
  ┌──────────────┐   ┌─────────────────────┐
  │ MySQL 8.0    │   │ 硅基流动 API          │
  │ 本地服务      │   │ api.siliconflow.cn   │
  │ InnoDB/utf8mb4│  │                      │
  └──────────────┘   └─────────────────────┘
```

**分层原则**：Router（收参数、返回响应）→ Service（业务逻辑）→ Repository（数据访问）。
不要在 Router 里直接写 SQL，也不要在里面调 LLM API。这是本项目后端最重要的工程习惯。

---

## 三、数据模型（v1）

MySQL 建表比 SQLite 严格得多：**索引列必须指定长度**、**字符集要显式声明**、
**主键设计直接影响写入性能**。下面这些类型不是随手写的，Phase 1 会逐条讲原因。

```sql
CREATE DATABASE ai_chat
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

```
conversations
├── id            BIGINT UNSIGNED AUTO_INCREMENT  主键
├── title         VARCHAR(255)   会话标题（默认"新对话"，首轮后自动生成）
├── model         VARCHAR(100)   使用的模型 ID
├── system_prompt TEXT           系统提示词（可空）
├── created_at    DATETIME(6)    UTC 存储
└── updated_at    DATETIME(6)    用于会话列表排序（建索引）

messages
├── id              BIGINT UNSIGNED AUTO_INCREMENT  主键
├── conversation_id BIGINT UNSIGNED  外键 → conversations.id (ON DELETE CASCADE)
├── role            VARCHAR(20)      'user' | 'assistant' | 'system'
├── content         MEDIUMTEXT       消息正文（TEXT 只有 64KB，长回答会溢出）
├── status          VARCHAR(20)      'complete' | 'streaming' | 'error'
├── token_usage     INT UNSIGNED     可空，记录用量
├── created_at      DATETIME(6)
└── (联合索引: conversation_id + created_at)
```

**为什么主键用自增 BIGINT 而不是 UUID？**
InnoDB 用 B+ 树组织数据，**主键就是聚簇索引**，数据行按主键顺序物理存放。
随机 UUID 每次插入落在 B+ 树的不同位置，频繁触发**页分裂**，写入性能显著下降；
自增整数永远追加在末尾，是顺序写入。这也是"SQLite 里能随便用 TEXT 当主键、
MySQL 里不行"的根本原因。这是 MySQL 面试高频题，值得你记住。

**为什么字符集必须是 utf8mb4？**
MySQL 里的 `utf8` 是个历史遗留的坑——它只有 **3 字节**，存不下 emoji 和部分生僻字，
写入时直接报 `Incorrect string value`。`utf8mb4` 才是真正的 4 字节 UTF-8。
中文项目一律 utf8mb4，没有例外。

**为什么 content 用 MEDIUMTEXT？**
MySQL 的 `TEXT` 上限 64KB，AI 的长回答很容易超过。`MEDIUMTEXT` 上限 16MB，够用到项目结束。

**为什么 message 要存 status？** 因为流式生成中途可能出错或被用户中止。
如果不存状态，下次打开会话会看到一条"半截"消息分不清是正常还是失败。

**为什么不是只存 conversation_id 就够？** 会话列表要显示"最后一条消息预览"，
这个在 Phase 4 会用到，先埋好结构。

---

## 四、SSE 事件协议（先设计，后实现）

这是前后端之间唯一的"契约"，**动手写代码前必须先定死**，否则后期改动会两边一起炸。

**请求**：`POST /api/v1/chat/stream`

```json
{
  "conversation_id": "uuid",
  "content": "你好"
}
```

**响应**：`Content-Type: text/event-stream`

```
event: start
data: {"message_id": "uuid", "conversation_id": "uuid"}

event: delta
data: {"content": "你"}

event: delta
data: {"content": "好"}

event: usage
data: {"prompt_tokens": 12, "completion_tokens": 5}

event: done
data: {"message_id": "uuid"}

```

**出错时**：
```
event: error
data: {"code": "UPSTREAM_ERROR", "message": "上游服务超时"}
```

**约定**：
- 每条事件以 `\n\n` 结尾（SSE 规范）
- `delta` 是**增量**文本，不是全量，前端负责追加
- 前端收到 `done` 或 `error` 后必须主动关闭连接
- 任何单一事件内的 JSON 解析失败，前端应忽略该事件而不是崩溃

**⚠️ 关键坑**：浏览器原生 `EventSource` **只支持 GET 请求**，
而我们的对话接口必须用 POST（要传消息体）。所以前端**必须手写 fetch + ReadableStream 解析器**。
这个我们在 Phase 2 会从头写一遍，理解了就不难。

---

## 五、分阶段路线图

每个阶段都有明确的**交付物**和**验收标准**。验收不过不进入下一阶段。

---

### Phase 0 · 地基与环境（预计 0.5 天）

**做什么**
1. `git init`，建 `.gitignore`（Python + Node 双份）
2. 后端骨架：`backend/` + 激活 conda 环境 `fastapi_env` + 依赖 + FastAPI 应用 + `GET /api/health`
3. 前端骨架：`frontend/` + Vite + Vue3 + TS + Element Plus + TailwindCSS
4. **解决 Tailwind 与 Element Plus 的样式冲突**（见下方踩坑预警 #1）
5. Vite `proxy` 把 `/api` 转发到 FastAPI，前端页面调通 `/api/health` 并显示后端版本

**验收**：浏览器打开页面，看到"后端版本: 0.1.0"——说明前后端联调通了。

**你会学到**：Vite 代理原理、FastAPI 应用生命周期、CORS 什么时候才需要、Tailwind 的 `@layer` 机制。

---

### Phase 1 · 数据层与会话 CRUD（预计 2 天）

**做什么**
0. **安装并启动 MySQL 8.0**，创建 `ai_chat` 库（utf8mb4）、建一个专用账号（不要用 root 连应用）
1. SQLAlchemy 2.0 async engine（`mysql+aiomysql`）+ session 依赖注入（`Depends`）
2. 定义 `Conversation` / `Message` 模型（含 InnoDB、级联外键、联合索引）
3. Pydantic v2 的 Create / Update / Read 三套 Schema，以及 `from_attributes`
4. Repository 层封装数据访问
5. 会话接口：列表 / 创建 / 详情 / 重命名 / 删除
6. 消息接口：按会话查列表
7. 引入 Alembic，生成第一版迁移脚本

**验收**：在 `/docs` 里能完整走一遍"建会话 → 加消息 → 改标题 → 查列表 → 删会话（消息级联删除）"。
再用 DBeaver / Navicat 打开表，亲眼确认 `utf8mb4` 生效、级联删除真的删掉了子表数据。

**你会学到**：异步 ORM 的正确姿势、`Depends` 依赖注入、分层的意义、Pydantic v2 与 ORM 的配合、
MySQL 字符集与索引原理、Alembic 迁移工作流。
**⚠️ 这里会重点讲**：async session 的生命周期陷阱（为什么不能把 session 存成全局）。

---

### Phase 2 · 流式对话打通 ★项目最关键阶段（预计 2 天）

**做什么**
1. `.env` + `pydantic-settings` 管理 API Key（**绝不硬编码、绝不提交到 git**）
2. LLM 客户端封装：`openai` SDK + `base_url="https://api.siliconflow.cn/v1"`
3. 组装上下文：从 DB 取历史消息 → 转成 OpenAI messages 格式 → 加上 system prompt
4. 实现 SSE 响应：`StreamingResponse` + 异步生成器
5. 不管生成成功还是失败，都要把 assistant 消息落库
6. 前端：手写 `fetch` + `ReadableStream` 的 SSE 解析器
7. 前端：流式追加渲染 + 打字机效果
8. **中止功能**：`AbortController`，用户点"停止"能真正掐断上游请求

**验收**：输入问题，文字能一个字一个字流出来；点停止能立即停住且不报错；刷新页面后消息仍在。

**你会学到**：异步生成器、SSE 协议细节、为什么流式接口不能用普通 `return`、
上游连接的生命周期管理、`AbortController` 与后端取消的联动。
**这是整个项目技术含量最高的一段，也是面试最能聊的一段。**

---

### Phase 3 · 对话界面打磨（预计 2 天）

**做什么**
1. 三栏布局：侧边栏（会话列表）+ 主区（消息）+ 底部（输入框）
2. 消息气泡：用户右侧、AI 左侧，头像/配色区分
3. **Markdown 渲染**：`markdown-it` + `highlight.js`，代码块带语言标签和一键复制
4. 自动滚到底部（但用户手动上滑时不强制拉回——这个细节体验差别很大）
5. 输入框：多行自适应高度、`Enter` 发送、`Shift+Enter` 换行
6. 重新生成 / 删除单条消息
7. 亮暗主题切换

**验收**：自己用起来"像个产品"，而不是"像个 demo"。让朋友用一次，记录他们卡住的地方。

**你会学到**：Tailwind + Element Plus 混合使用的取舍、Markdown XSS 风险、
滚动位置控制、Vue 的响应式性能（长列表渲染）。

---

### Phase 4 · 工程化与体验完善（预计 1.5 天）

**做什么**
1. 后端：全局异常处理器（统一错误响应格式）、结构化日志、请求耗时记录
2. 前端：统一请求封装、错误处理、loading 态、ElMessage 提示
3. **标题自动生成**：首轮对话后，用一个小模型总结出会话标题
4. 会话搜索、按更新时间排序、消息数量统计
5. 长对话的上下文裁剪（超过 N 条时只带最近的，避免超 token）

**验收**：故意断网、故意填错 API Key、故意发超长消息，界面都有清晰友好提示，不白屏、不静默失败。

**你会学到**：全局异常处理的意义、日志该记什么、token 预算的概念、容错设计。

---

### Phase 5 · 部署上线（预计 1.5 天）—— 在这里学 Docker

**做什么**
1. 前端 `pnpm build` 产出静态文件
2. 后端用 `uvicorn` 多 worker 启动，配置生产环境变量
3. **学 Docker**：写 `Dockerfile`（前端、后端）+ `docker-compose.yml`，把 MySQL 也容器化
4. 买一台云服务器（阿里云/腾讯云轻量，学生机很便宜），Nginx 反代 + HTTPS
5. 把项目地址写进简历

**验收**：给朋友一个网址，他能在自己手机上跟你做的 AI 聊天。

**你会学到**：Docker 镜像/容器/卷/网络、Nginx 反向代理、
**⚠️ 特别坑**：Nginx 默认会缓冲响应，会让 SSE 变成"等 30 秒然后一次性蹦出来"，
必须加 `proxy_buffering off`——这个坑 90% 的人第一次部署都会踩。

---

### Phase 6 · 可选进阶（选一个做深，别全做）

- **用户体系**：注册/登录/JWT/多用户数据隔离/管理员后台
- **知识库 RAG**：文档上传 → 切分 → 向量化（embedding）→ 检索 → 注入上下文
- **多模型切换**：抽象 Provider 层，支持硅基流动/OpenAI/Ollama 任意切换
- **附件与多模态**：图片上传与视觉模型
- **Agent 工具调用**：Function Calling + 联网搜索

建议顺序：多模型切换 → 用户体系 → RAG。**RAG 最难，放最后。**

---

## 六、踩坑预警（提前知道能省你很多时间）

### 1. TailwindCSS 与 Element Plus 的 reset 冲突 ⚠️
Tailwind 自带 `preflight`（全局样式重置），它会重置 `button`、`input`、标题、
列表的默认样式，而 Element Plus 也依赖一套自己的 reset。两者叠加会出现：
按钮背景消失、边框错乱、输入框高度不对劲。

**解决方案**：Tailwind v4 用分层导入，**只引 theme 和 utilities，跳过 preflight**：
```css
/* src/style.css */
@layer theme, base, components, utilities;
@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/utilities.css" layer(utilities);
/* 全局 reset 交给 Element Plus */
@import "element-plus/dist/index.css";
```
Phase 0 我会带你**先故意开着 preflight 看一眼坏的对比**，再关掉——这样你以后遇到类似冲突能自己判断。

### 2. SSE 不能用 `EventSource`
原生 `EventSource` 只支持 GET 且不能自定义 header。我们的对话接口是 POST。
必须用 `fetch` + `response.body.getReader()` 手写解析。Phase 2 会讲透。

### 3. Nginx 缓冲会让 SSE 失效
部署时必须 `proxy_buffering off;` 和 `X-Accel-Buffering: no`。

### 4. async session 不能全局复用
FastAPI 的异步 DB session 必须每请求一个，用 `Depends` 注入。存成模块级全局变量
会在并发下出各种诡异错误。

### 5. 别在 async 函数里写同步阻塞代码
`requests`、`time.sleep`、同步文件 IO 都会阻塞整个事件循环。
统一用 `httpx.AsyncClient`。这是新手写 FastAPI 最常见的性能事故。

### 6. `.env` 必须进 `.gitignore`
API Key 泄露到 GitHub 会被爬虫扫到并盗刷。**第一件事就配好 `.gitignore`。**

### 7. MySQL 服务没启动（最常见的"灵异报错"）
MySQL 是**独立的后台服务**，不是文件。重启电脑后服务没自启、或你手动停了它，
后端会报 `Can't connect to MySQL server on 'localhost'`。
遇到这个报错先查服务状态（Windows 上 `services.msc` 里找 `MySQL80`），
再怀疑代码。这个坑会浪费你半小时，如果不知道的话。

### 8. 字符集不是 utf8mb4，中文/emoji 直接报错
建库时没指定字符集，默认可能是 `latin1` 或 3 字节的 `utf8`，
插入中文报 `Incorrect string value`。**三个地方都要对**：库、表、连接串
（连接串带 `?charset=utf8mb4`）。只改一处不生效是新手最容易犯的错。

### 9. VARCHAR 不带长度是语法错误
`title VARCHAR` 在 MySQL 里直接报错，必须 `VARCHAR(255)`。
而且**参与索引的列必须有长度上限**——这是 MySQL 和 SQLite 最大的建表差异，
也是为什么第三节里每个字符串字段都写了具体数字。

### 10. 主键别用随机 UUID
见第三节。InnoDB 主键是聚簇索引，随机主键导致页分裂、写入变慢。
本项目统一 `BIGINT UNSIGNED AUTO_INCREMENT`。

---

## 七、目标目录结构

```
ai-chat/
├── ROADMAP.md
├── .gitignore
├── README.md
├── backend/
│   ├── .env                    # 不进 git
│   ├── .env.example            # 进 git
│   ├── pyproject.toml
│   ├── alembic/                # Phase 2 后引入
│   └── app/
│       ├── main.py             # 应用入口
│       ├── core/               # config, logging, exceptions
│       ├── db/                 # session, base
│       ├── models/             # SQLAlchemy 模型
│       ├── schemas/            # Pydantic 模型
│       ├── repositories/       # 数据访问
│       ├── services/           # 业务逻辑
│       │   └── llm_client.py   # 硅基流动客户端
│       └── api/
│           └── v1/
│               ├── conversations.py
│               ├── messages.py
│               └── chat.py     # SSE 流式接口
└── frontend/
    ├── src/
    │   ├── api/                # Axios 封装 + 流式请求
    │   ├── stores/             # Pinia
    │   ├── components/
    │   │   ├── ConversationList.vue
    │   │   ├── MessageBubble.vue
    │   │   ├── MessageInput.vue
    │   │   └── MarkdownRenderer.vue
    │   ├── views/
    │   │   └── ChatView.vue
    │   ├── router/
    │   ├── types/              # TS 类型定义
    │   └── utils/
    │       └── sse.ts          # SSE 解析器
    └── vite.config.ts
```

---

## 八、我们的协作方式（重要）

**分工：所有项目代码由你自己写。我负责讲原理、给最小示例、做 code review。**
目的是让这个项目真正变成"你的项目"，而不是"看我敲完"。

1. **每阶段开工前**：我讲清楚这一步要做什么、为什么这么做、涉及哪些新概念，
   并给出**最小可运行的代码示例**——片段级别，展示"形状"和关键 API，
   不是能直接照抄的完整文件。
2. **我不代写项目代码**：`backend/` 和 `frontend/` 里的文件一律由你创建和修改。
   本路线图文档由我维护。
3. **每完成一步**：把关键代码贴给我，我做 review——指出问题、解释原因，
   但答案要你自己改出来。
4. **每个 Phase 结束**：我会问你 3-5 个问题验证你真懂了（不是考试，是查漏），
   然后做一次小回顾。
5. **遇到卡点**：把**报错信息 + 相关代码 + 你已经试过什么**一起贴给我。
   我们定位根因，不只是修好——**自己 debug 的过程才是真正学到东西的地方**。
6. **进度记录**：每完成一个 Phase，在 `README.md` 打勾，并把踩到的坑记下来
   —— 这些是你面试时最好的素材。
7. **节奏随时可调**：某个概念我讲太快/太慢，直接说。

---

## 九、进度追踪

- [ ] Phase 0 · 地基与环境
- [ ] Phase 1 · 数据层与会话 CRUD
- [ ] Phase 2 · 流式对话打通 ★
- [ ] Phase 3 · 对话界面打磨
- [ ] Phase 4 · 工程化与体验完善
- [ ] Phase 5 · 部署上线
- [ ] Phase 6 · 进阶（选做）

**总计预计 11-12 天**（按每天 4-5 小时有效投入估算）。
