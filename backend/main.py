"""
命题逻辑自然推理系统 - FastAPI 后端
端口: 8081
"""
import asyncio
import os
import sqlite3
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from prover.natural_deduction import NaturalDeductionProver
from prover.truth_table import generate_truth_table
from prover.semantic_tree import semantic_tableau
from prover.parser import ParseError
from ai.explainer import explain_step, explain_exercise_error
from analytics import init_analytics_db, record_event, get_prometheus_metrics

# ── 数据库路径 ────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent / "data" / "exercises.db"
KNOWLEDGE_DIR = Path(__file__).parent / "data" / "knowledge"


def init_db():
    """初始化 SQLite 题库"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
            category TEXT NOT NULL,
            premises TEXT NOT NULL,  -- JSON array
            goal TEXT NOT NULL,
            hint TEXT,
            explanation TEXT
        )
    """)
    if c.execute("SELECT COUNT(*) FROM exercises").fetchone()[0] == 0:
        _seed_exercises(c)
    conn.commit()
    conn.close()


def _seed_exercises(c):
    """插入题库 — 基于课程讲义(1-prop-logic-handout.pdf)结构化分类"""
    exercises = [
        # ═══ 模块1: ∧ 合取规则 (P45-47) ═══
        ("合取引入", "easy", "∧规则",
         '["P", "Q"]', "P & Q",
         "两个命题同时成立，可以合取",
         "∧-intro：P, Q ⊢ P∧Q"),
        ("合取消除（左）", "easy", "∧规则",
         '["P & Q"]', "P",
         "合取命题成立，其任一支也成立",
         "∧-elim_l：P∧Q ⊢ P"),
        ("合取消除（右）", "easy", "∧规则",
         '["P & Q"]', "Q",
         "合取命题成立，其任一支也成立",
         "∧-elim_r：P∧Q ⊢ Q"),
        ("∧规则综合 (P46)", "easy", "∧规则",
         '["(P & Q) & R", "S & T"]', "Q & S",
         "分别从两个合取式提取所需分量，再合并",
         "先用∧-elim提取Q和S，再用∧-intro合并"),
        ("∧规则练习 (P47)", "easy", "∧规则",
         '["P & Q", "R"]', "Q & R",
         "从合取式提取Q，与R合取",
         "∧-elim_r提取Q，再∧-intro得Q∧R"),

        # ═══ 模块2: ¬¬ 双重否定规则 (P48-49) ═══
        ("双重否定消除", "easy", "¬¬规则",
         '["~~P"]', "P",
         "双重否定等于肯定",
         "¬¬-elim：¬¬P ⊢ P"),
        ("双重否定引入", "easy", "¬¬规则",
         '["P"]', "~~P",
         "肯定命题可以加双重否定",
         "¬¬-intro：P ⊢ ¬¬P"),
        ("¬¬规则综合 (P49)", "medium", "¬¬规则",
         '["P", "~~(Q & R)"]', "~~P & R",
         "P用¬¬-intro得¬¬P，Q∧R先¬¬-elim再∧-elim取R",
         "组合使用¬¬-intro、¬¬-elim和∧规则"),

        # ═══ 模块3: →-elim / MT 蕴含消除 (P50-54) ═══
        ("假言推理 (MP)", "easy", "→-elim",
         '["P -> Q", "P"]', "Q",
         "已知蕴含和前件成立，直接得后件",
         "→-elim (Modus Ponens)：P→Q, P ⊢ Q"),
        ("拒取式 (MT)", "easy", "→-elim",
         '["P -> Q", "~Q"]', "~P",
         "已知蕴含和后件否定，得前件否定",
         "MT (Modus Tollens)：P→Q, ¬Q ⊢ ¬P"),
        ("假言三段论 (HS)", "easy", "→-elim",
         '["P -> Q", "Q -> R"]', "P -> R",
         "两个蕴含链接，得首尾蕴含",
         "HS：P→Q, Q→R ⊢ P→R"),
        ("→-elim 综合 (P51)", "medium", "→-elim",
         '["P", "P -> Q", "P -> (Q -> R)"]', "R",
         "先MP得Q，再MP得Q→R，最后MP得R",
         "两次→-elim连续应用"),
        ("→-elim+MT (P52)", "medium", "→-elim",
         '["P -> (Q -> R)", "P", "~R"]', "~Q",
         "先MP得Q→R，再用MT由¬R得¬Q",
         "组合→-elim和MT"),
        ("MT 练习1 (P53)", "medium", "→-elim",
         '["~P -> Q", "~Q"]', "P",
         "用MT得¬¬P，再¬¬-elim得P",
         "MT + ¬¬-elim组合"),
        ("MT 练习2 (P54)", "medium", "→-elim",
         '["P -> ~Q", "Q"]', "~P",
         "Q用¬¬-intro得¬¬Q，再MT得¬P",
         "¬¬-intro + MT组合"),

        # ═══ 模块4: →-intro 条件证明 (P55-61) ═══
        ("恒等蕴含 (P61)", "easy", "→-intro",
         '[]', "P -> P",
         "假设P，直接得P，关闭子证明",
         "最简单的→-intro：假设P即得P"),
        ("条件证明基础 (P56)", "medium", "→-intro",
         '["~Q -> ~P"]', "P -> ~~Q",
         "假设P，由逆否得¬¬Q",
         "假设P，MT得¬¬Q，→-intro关闭"),
        ("柯里化 (P58)", "medium", "→-intro",
         '["(P & Q) -> R"]', "P -> (Q -> R)",
         "先假设P，再假设Q，构造P∧Q后MP得R",
         "双层→-intro：外层假设P，内层假设Q"),
        ("反柯里化 (P59)", "medium", "→-intro",
         '["P -> (Q -> R)"]', "(P & Q) -> R",
         "假设P∧Q，分别提取P和Q后两次MP得R",
         "假设P∧Q，∧-elim后连续→-elim"),
        ("蕴含保持合取 (P60)", "medium", "→-intro",
         '["P -> Q"]', "(P & R) -> (Q & R)",
         "假设P∧R，提取P后MP得Q，再与R合取",
         "→-intro + ∧-elim + →-elim + ∧-intro"),
        ("三层嵌套→-intro (P57)", "hard", "→-intro",
         '[]', "(Q -> R) -> ((~Q -> ~P) -> (P -> R))",
         "三层假设：Q→R, ¬Q→¬P, P，用MT+¬¬-elim推R",
         "需要3层嵌套子证明，最深层使用MT推导"),

        # ═══ 模块5: ∨ 析取规则 (P62-67) ═══
        ("析取引入", "easy", "∨规则",
         '["P"]', "P | Q",
         "已知P成立，P∨Q自然成立",
         "∨-intro：P ⊢ P∨Q"),
        ("析取三段论 (DS)", "easy", "∨规则",
         '["P | Q", "~P"]', "Q",
         "析取成立且一支不成立，另一支必成立",
         "DS：P∨Q, ¬P ⊢ Q"),
        ("构造式两难 (∨-elim)", "medium", "∨规则",
         '["P | Q", "P -> R", "Q -> R"]', "R",
         "对P∨Q分情况讨论，两种情况都推出R",
         "∨-elim：分别假设P和Q，各推出R"),
        ("析取交换 (P63)", "medium", "∨规则",
         '["P | Q"]', "Q | P",
         "P∨Q中分别对P和Q用∨-intro得Q∨P",
         "∨-elim子证明：假设P→Q∨P，假设Q→Q∨P"),
        ("析取保持蕴含 (P64)", "hard", "∨规则",
         '["Q -> R"]', "(P | Q) -> (P | R)",
         "假设P∨Q，分情况：P→P∨R直接，Q→用MP得R→P∨R",
         "→-intro + ∨-elim子证明"),
        ("析取结合律 (P65)", "hard", "∨规则",
         '["(P | Q) | R"]', "P | (Q | R)",
         "外层析取分情况，对P∨Q再分情况讨论",
         "需要嵌套∨-elim子证明"),
        ("分配律→ (P66)", "hard", "∨规则",
         '["P & (Q | R)"]', "(P & Q) | (P & R)",
         "提取P，对Q∨R分情况，各与P合取后∨-intro",
         "∧-elim + ∨-elim + ∧-intro + ∨-intro"),
        ("分配律← (P67)", "hard", "∨规则",
         '["(P & Q) | (P & R)"]', "P & (Q | R)",
         "分情况提取P和Q/R，Q/R用∨-intro后与P合取",
         "∨-elim + ∧-elim + ∨-intro + ∧-intro"),

        # ═══ 模块6: ¬-elim / ¬-intro 否定规则 (P68-74) ═══
        ("否定消除 (¬-elim)", "easy", "¬规则",
         '["P", "~P"]', "~Q",
         "P和¬P同时成立则矛盾，可推出任意结论",
         "¬-elim得⊥，由⊥可得任何命题（爆炸原理）"),
        ("材料蕴含 (P69)", "medium", "¬规则",
         '["~P | Q"]', "P -> Q",
         "假设P，对¬P∨Q分情况讨论",
         "→-intro + ∨-elim：假设P的P+¬P矛盾，或直接得Q"),
        ("反证法 (P71)", "medium", "¬规则",
         '["P -> Q", "P -> ~Q"]', "~P",
         "假设P，得Q和¬Q矛盾，故¬P",
         "¬-intro：假设P导出矛盾⊥"),
        ("¬-intro+¬¬-elim (P72)", "hard", "¬规则",
         '["(P & ~Q) -> R", "~R", "P"]', "Q",
         "假设¬Q，与P合取后MP得R，与¬R矛盾",
         "RAA/¬¬-elim：假设¬Q导出矛盾，得¬¬Q即Q"),
        ("自否定 (P73)", "medium", "¬规则",
         '["P -> ~P"]', "~P",
         "假设P，由MP得¬P，与P矛盾",
         "¬-intro：假设P，由P→¬P得¬P，P和¬P矛盾得⊥"),

        # ═══ 模块7: 重言式 (P40) ═══
        ("MP重言式 (P40a)", "hard", "重言式",
         '[]', "((P -> Q) & P) -> Q",
         "假设(P→Q)∧P，分别提取后MP得Q",
         "→-intro + ∧-elim + →-elim"),
        ("MT重言式 (P40b)", "hard", "重言式",
         '[]', "((P -> Q) & ~Q) -> ~P",
         "假设(P→Q)∧¬Q，分别提取后MT得¬P",
         "→-intro + ∧-elim + MT"),
        ("DS重言式 (P40c)", "hard", "重言式",
         '[]', "((P | Q) & ~P) -> Q",
         "假设(P∨Q)∧¬P，分别提取后DS得Q",
         "→-intro + ∧-elim + DS"),

        # ═══ 补充题: 综合应用 ═══
        ("两步假言推理", "medium", "综合",
         '["P -> Q", "Q -> R", "P"]', "R",
         "先HS得P→R，再MP得R", "组合HS和→-elim"),
        ("前件合取构造", "medium", "综合",
         '["(P & Q) -> R", "P", "Q"]', "R",
         "先∧-intro构造P∧Q，再MP得R",
         "∧-intro + →-elim"),
        ("混合合取推理", "medium", "综合",
         '["P -> Q", "P & R"]', "Q & R",
         "提取P后MP得Q，提取R后∧-intro得Q∧R",
         "∧-elim + →-elim + ∧-intro"),
        ("双条件应用", "medium", "综合",
         '["P <-> Q", "P"]', "Q",
         "从P↔Q提取P→Q，再MP得Q",
         "↔-elim + →-elim"),
        ("嵌套蕴含消除", "medium", "综合",
         '["P -> (Q -> R)", "P", "Q"]', "R",
         "先MP得Q→R，再MP得R",
         "两次→-elim"),
        ("链式推理四步", "hard", "综合",
         '["A -> B", "B -> C", "C -> D", "A"]', "D",
         "多次HS或多次MP",
         "三次HS + 一次→-elim，或直接三次→-elim"),
        ("双条件传递", "hard", "综合",
         '["P <-> Q", "Q <-> R", "P"]', "R",
         "P↔Q提取P→Q得Q，Q↔R提取Q→R得R",
         "两次↔-elim + 两次→-elim"),
        ("∨-intro+MP", "medium", "综合",
         '["(A | B) -> C", "A"]', "C",
         "先由A用∨-intro得A∨B，再MP得C",
         "∨-intro + →-elim"),
        ("德摩根推理", "hard", "综合",
         '["~(P & Q)", "P"]', "~Q",
         "假设Q，与P合取得P∧Q，与¬(P∧Q)矛盾",
         "¬-intro：假设Q导出矛盾"),
        ("材料蕴含(反向)", "hard", "综合",
         '["P -> Q"]', "~P | Q",
         "用∨-elim和RAA等技巧证明",
         "需要反证法和析取引入组合使用"),
    ]
    c.executemany(
        "INSERT INTO exercises (title,difficulty,category,premises,goal,hint,explanation) VALUES (?,?,?,?,?,?,?)",
        exercises
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_analytics_db()
    yield


# ── FastAPI 应用 ─────────────────────────────────────────────────
app = FastAPI(
    title="命题逻辑自然推理系统 API",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 请求/响应模型 ────────────────────────────────────────────────
class ProveRequest(BaseModel):
    premises: list[str]
    goal: str
    style: str = "natural_deduction"


class ExplainRequest(BaseModel):
    step: dict
    all_steps: list[dict]
    premises: list[str]
    goal: str


class CheckAnswerRequest(BaseModel):
    user_answer: str


class TrackRequest(BaseModel):
    event_type: str
    page: str = ""
    detail: str = ""


# ── 路由 ─────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"name": "命题逻辑自然推理系统", "version": "1.1.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/prove")
def prove(req: ProveRequest, request: Request):
    if not req.goal:
        raise HTTPException(400, "目标不能为空")

    try:
        if req.style == "truth_table":
            result = generate_truth_table(req.premises, req.goal)
            record_event("proof_submit", detail=req.style, ip=request.client.host if request.client else "")
            return {"style": "truth_table", "result": result}

        elif req.style == "semantic_tree":
            result = semantic_tableau(req.premises, req.goal)
            record_event("proof_submit", detail=req.style, ip=request.client.host if request.client else "")
            return {"style": "semantic_tree", "result": result}

        else:  # natural_deduction (default)
            prover = NaturalDeductionProver()
            result = prover.prove(req.premises, req.goal)
            record_event("proof_submit", detail=req.style, ip=request.client.host if request.client else "")
            return {"style": "natural_deduction", "result": result.to_dict()}

    except ParseError as e:
        raise HTTPException(400, f"公式解析错误: {e}")
    except Exception as e:
        raise HTTPException(500, f"证明引擎错误: {e}")


@app.post("/explain")
async def explain(req: ExplainRequest, request: Request):
    record_event("ai_explain", ip=request.client.host if request.client else "")
    context = {
        "all_steps": req.all_steps,
        "premises": req.premises,
        "goal": req.goal,
    }
    explanation = await explain_step(req.step, context)
    return {"explanation": explanation}


@app.post("/track")
async def track(req: TrackRequest, request: Request):
    """接收前端埋点（非阻塞写入）"""
    ip = request.client.host if request.client else ""
    # 异步非阻塞写入
    asyncio.get_event_loop().run_in_executor(
        None, record_event, req.event_type, req.page, req.detail, ip
    )
    return {"ok": True}


@app.get("/metrics")
def metrics():
    """Prometheus 格式指标（不加 /api 前缀，由 nginx 直接代理到 8081）"""
    return Response(
        content=get_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@app.get("/exercises")
def list_exercises(
    difficulty: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = "SELECT id, title, difficulty, category, premises, goal, hint FROM exercises WHERE 1=1"
    params = []
    if difficulty:
        query += " AND difficulty = ?"
        params.append(difficulty)
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY CASE difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"
    query += f" LIMIT {limit} OFFSET {offset}"

    rows = c.execute(query, params).fetchall()
    total = c.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
    conn.close()

    exercises = []
    for row in rows:
        e = dict(row)
        e["premises"] = json.loads(e["premises"])
        exercises.append(e)

    return {"total": total, "exercises": exercises}


@app.get("/exercises/{exercise_id}")
def get_exercise(exercise_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "题目不存在")

    e = dict(row)
    e["premises"] = json.loads(e["premises"])
    return e


@app.post("/exercises/{exercise_id}/check")
async def check_answer(exercise_id: int, req: CheckAnswerRequest, request: Request):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "题目不存在")

    exercise = dict(row)
    exercise["premises"] = json.loads(exercise["premises"])

    correct = req.user_answer.strip() == exercise["goal"].strip()

    record_event(
        "exercise_check",
        detail=exercise.get("difficulty", ""),
        ip=request.client.host if request.client else ""
    )

    ai_explanation = ""
    if not correct:
        ai_explanation = await explain_exercise_error(exercise, req.user_answer)

    return {
        "correct": correct,
        "correct_answer": exercise["goal"],
        "explanation": exercise.get("explanation", ""),
        "ai_explanation": ai_explanation,
    }


@app.get("/knowledge")
def list_knowledge():
    """列出所有知识库文件"""
    if not KNOWLEDGE_DIR.exists():
        return {"files": []}

    files = []
    for f in sorted(KNOWLEDGE_DIR.glob("*.md")):
        files.append({
            "name": f.stem,
            "filename": f.name,
            "size": f.stat().st_size,
        })
    return {"files": files}


@app.get("/knowledge/{filename}")
def get_knowledge(filename: str):
    """获取知识库文件内容"""
    safe_name = Path(filename).name
    file_path = KNOWLEDGE_DIR / safe_name
    if not file_path.exists() or not safe_name.endswith(".md"):
        raise HTTPException(404, "文件不存在")
    return {"filename": safe_name, "content": file_path.read_text(encoding="utf-8")}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8081)
