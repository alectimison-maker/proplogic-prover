# 命题逻辑自然推理系统

一个基于自然演绎（Natural Deduction）的命题逻辑学习与验证平台。

## 项目介绍

本项目提供了一套完整的命题逻辑自然推理工具，涵盖自动证明、AI 辅助解释和系统化学习资料。系统支持 Fitch 风格的自然演绎证明，包含合取（∧）、析取（∨）、蕴含（→）、否定（¬）等命题逻辑的核心推理规则。

**目标用户**：学习形式逻辑的本科生、对自然演绎感兴趣的自学者。

---

## 功能模块

### 1. 证明助手（Proof Assistant）
输入前提公式和目标公式，系统自动搜索并生成严格的自然演绎证明步骤。

- 支持三种证明方法：自然演绎、真值表、语义树
- 每个证明步骤可点击"解释"按钮，由 AI 提供详细解释
- 使用 Fitch 风格可视化展示，嵌套子证明以多层竖线区分深度

### 2. 学习资料（Learning Materials）
系统化的命题逻辑学习文档，按规则模块组织：

- 命题逻辑基础（符号与语义）
- ∧ 合取规则（引入与消除）
- ¬¬ 双重否定规则
- → 蕴含消除（→-elim、MT、HS、DS）
- → 蕴含引入（条件证明、子证明结构）
- ∨ 析取规则（引入与消除）
- ¬ 否定规则（¬-elim、¬-intro、RAA）

每个章节包含形式定义、完整例题（含逐步解析）和解题策略。

---

## 技术栈

### 前端

| 技术 | 说明 |
|------|------|
| HTML / CSS / JavaScript | 纯原生实现，无框架依赖 |
| [KaTeX](https://katex.org/) | 数学公式渲染 |
| Fitch 风格证明表格 | 自定义 CSS + JavaScript 双遍扫描渲染 |

主要文件：
- `frontend/index.html` — 首页
- `frontend/prover.html` — 证明助手
- `frontend/learn.html` — 学习资料（含内嵌 Markdown 解析器）
- `frontend/css/` — 样式表
- `frontend/js/` — 分析埋点脚本

### 后端

| 技术 | 说明 |
|------|------|
| Python 3.10+ | 主要语言 |
| [FastAPI](https://fastapi.tiangolo.com/) | ASGI Web 框架 |
| [Uvicorn](https://www.uvicorn.org/) | ASGI 服务器（配置 2 workers） |
| SQLite | 轻量级数据存储（知识库 + 分析数据） |

主要文件：
- `backend/main.py` — API 路由（`/prove`、`/explain`、`/knowledge/{key}.md`）
- `backend/data/knowledge/` — Markdown 格式的学习内容文件
- `backend/prover/` — 自然演绎证明搜索逻辑

### AI 解释功能

每个证明步骤的"解释"功能通过 [Anthropic Claude API](https://www.anthropic.com/) 实现：

- 后端接收步骤信息，调用 Claude API 生成中文解释
- 使用 `claude-sonnet` 系列模型
- 需要在环境变量中配置 `ANTHROPIC_API_KEY`

---

## 本地运行

### 前提条件

- Python 3.10+
- pip

### 步骤

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 配置 API Key（可选，仅 AI 解释功能需要）
export ANTHROPIC_API_KEY=your_api_key_here

# 3. 启动后端
uvicorn main:app --host 0.0.0.0 --port 8081

# 4. 打开前端
# 用浏览器直接打开 frontend/index.html
# 或使用静态文件服务器（如 nginx、python -m http.server）
```

### API 接口说明

| 端点 | 方法 | 说明 |
|------|------|------|
| `/prove` | POST | 自然演绎证明 |
| `/truth-table` | POST | 真值表验证 |
| `/explain` | POST | AI 解释单个证明步骤 |
| `/knowledge/{key}.md` | GET | 获取学习资料内容 |

---

## 系统局限性

### 并发能力

- 当前配置支持约 **20–30 人同时在线**使用
- `/prove` 为 CPU 密集型同步端点，同时只能处理 2 个证明请求（2 个 Uvicorn worker）
- SQLite 单文件数据库，写操作存在锁竞争

### 证明逻辑

- 当前证明搜索深度有限，部分复杂证明（深度超过 6 层嵌套）可能超时
- ↔ 双条件规则（`↔-intro`、`↔-elim`）支持有限，某些双条件命题无法自动证明
- RAA（归谬法）在复杂嵌套场景下的搜索效率有待优化
- 目前不支持一阶逻辑（量词 ∀、∃）

---

## 未来发展方向

### 学习资料

- [ ] 持续补充各规则章节的例题和解题技巧
- [ ] 增加"错误示范"章节，分析常见证明错误
- [ ] 添加排中律、双重否定律等经典重言式专题

### 证明体验

- [ ] 优化证明搜索算法，提升大型证明的速度
- [ ] 支持用户手动输入证明步骤并逐步验证（交互式证明模式）
- [ ] 增加证明步骤的可视化动画，帮助理解子证明的开闭过程

### 系统架构

- [ ] `/prove` 端点改为异步处理，提升并发能力
- [ ] 迁移至更具扩展性的数据库（PostgreSQL）
- [ ] 增加 API 限流保护

---

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
