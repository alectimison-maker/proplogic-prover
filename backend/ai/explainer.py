"""
AI 步骤解释模块 - 适配 GMN Responses API (chuangzuoli.com)
接口格式: POST /v1/responses，使用 input 数组
"""
import os
import re
import requests

GMN_URL = "..."#按需填写
# 模型优先级（按可用性排序）
MODELS = [
    "gpt-5.3-codex",
    "gpt-5.2-codex",
    "gpt-5.2",
    "gpt-5.4",
    "gpt-5.1-codex-mini",
    "gpt-5-codex-mini",
]

SYSTEM_PROMPT = (
    "你是命题逻辑自然推理系统的专业助手，只回答命题逻辑相关问题。"
    "对于证明步骤解释，用简洁的中文说明该推理规则的形式和应用原理（2-4句话）。"
    "【重要格式要求】"
    "1. 使用 Unicode 数学符号：→ ∧ ∨ ¬ ↔ ⊥，不要用 LaTeX 命令。"
    "2. 绝对禁止使用 \\(、\\)、\\[、\\]、$、\\lnot、\\land、\\lor、\\to 等 LaTeX 标记。"
    "3. 直接在中文句子中引用公式，例如：'由 P→Q 和 P，可得 Q'。"
    "4. 规则名称使用标准记法：→-elim、→-intro、∧-intro、∧-elim、∨-intro、∨-elim、"
    "¬¬-elim、¬¬-intro、¬-elim、¬-intro、MT、HS、DS、RAA、↔-elim。"
    "不回答与命题逻辑无关的问题，对无关问题回复：我只能回答命题逻辑相关问题。"
)


def _clean_ai_output(text: str) -> str:
    """清理 AI 输出中的 LaTeX 残留标记"""
    # 移除 \(...\) 行内公式分隔符，保留内容
    text = re.sub(r'\\\(([^)]*)\\\)', r'\1', text)
    # 移除 \[...\] 块级公式分隔符
    text = re.sub(r'\\\[([^\]]*)\\\]', r'\1', text)
    # 移除 $...$ 分隔符
    text = re.sub(r'\$([^$]*)\$', r'\1', text)
    # 替换常见 LaTeX 命令为 Unicode
    replacements = {
        '\\lnot': '¬', '\\neg': '¬', '\\land': '∧', '\\lor': '∨',
        '\\to': '→', '\\rightarrow': '→', '\\leftrightarrow': '↔',
        '\\bot': '⊥', '\\top': '⊤', '\\vdash': '⊢',
        '\\wedge': '∧', '\\vee': '∨', '\\implies': '→',
    }
    for latex, uni in replacements.items():
        text = text.replace(latex, uni)
    # 清理多余反斜杠
    text = text.replace('\\,', ' ').replace('\\;', ' ')
    return text.strip()


def _call_gmn(user_msg: str, api_key: str) -> str:
    """调用 GMN Responses API，自动选择可用模型"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload_base = {
        "input": [
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user_msg}],
            },
        ],
        "max_output_tokens": 300,
    }

    last_err = ""
    for model in MODELS:
        payload = {**payload_base, "model": model}
        try:
            resp = requests.post(GMN_URL, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("output", []):
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "output_text":
                                raw = c.get("text", "").strip()
                                return _clean_ai_output(raw)
                return str(data)[:200]
            else:
                err_data = resp.json().get("error", {})
                last_err = err_data.get("message", resp.text)[:100]
                if resp.status_code != 503:
                    break
        except requests.Timeout:
            last_err = f"模型 {model} 超时"
            continue
        except Exception as e:
            last_err = str(e)[:100]
            break

    return f"（AI 暂时不可用：{last_err}）"


async def explain_step(step: dict, context: dict) -> str:
    """解释证明步骤"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "PLACEHOLDER_API_KEY":
        return _local_explain_step(step)

    premise_str = "\n".join(f"  {p}" for p in context.get("premises", []))
    goal_str = context.get("goal", "")
    related = []
    for ln in step.get("from_lines", []):
        for s in context.get("all_steps", []):
            if s["line"] == ln:
                related.append(f"  第{ln}行: {s['formula']} ({s['rule']})")

    user_msg = (
        f"证明上下文：\n前提：\n{premise_str}\n目标：{goal_str}\n\n"
        f"当前步骤（第{step['line']}行）：\n"
        f"  公式：{step['formula']}\n"
        f"  规则：{step['rule']}\n"
        + (f"  依据行：\n" + "\n".join(related) if related else "")
        + "\n\n请用2-4句话简洁解释这个推理步骤的逻辑依据和规则含义。"
        + "\n注意：直接使用 Unicode 符号（→∧∨¬↔⊥），不要用 LaTeX 格式。"
    )

    result = _call_gmn(user_msg, api_key)
    return result if result else _local_explain_step(step)


async def explain_exercise_error(exercise: dict, user_answer: str) -> str:
    """解释练习题错误"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "PLACEHOLDER_API_KEY":
        return f"正确答案是 {exercise.get('goal', '?')}，请对照推理规则再思考。"

    user_msg = (
        f"题目：{exercise.get('question', exercise.get('title', ''))}\n"
        f"前提：{', '.join(exercise.get('premises', []))}\n"
        f"正确答案：{exercise.get('goal', '')}\n"
        f"用户答案：{user_answer}\n\n"
        "请用2-3句话解释为什么用户答案不对，以及正确答案的逻辑依据。"
        "\n注意：直接使用 Unicode 符号（→∧∨¬↔⊥），不要用 LaTeX 格式。"
    )

    return _call_gmn(user_msg, api_key)


# ── 本地规则解释（无 AI 时的降级方案）─────────────────────────
_RULE_EXPLANATIONS = {
    "premise": "这是论证的已知条件，直接作为证明的起点。",
    "assumption": "为了使用条件证明(→-intro)或反证法(¬-intro/RAA)，临时引入一个假设命题，后续步骤将在此假设下推理。",
    "→-elim": "→-elim (Modus Ponens)：已知蕴含式 P→Q 和前件 P 均成立，由此推出后件 Q。形式：P→Q, P ⊢ Q。",
    "MT": "MT (Modus Tollens)：已知 P→Q 且 ¬Q 成立，推出 ¬P。形式：P→Q, ¬Q ⊢ ¬P。这是逆否命题的直接应用。",
    "HS": "HS (Hypothetical Syllogism)：两个蕴含链接 P→Q 和 Q→R，推出首尾蕴含 P→R。形式：P→Q, Q→R ⊢ P→R。",
    "DS": "DS (Disjunctive Syllogism)：析取式 P∨Q 成立且 ¬P 成立，推出 Q。形式：P∨Q, ¬P ⊢ Q。",
    "∧-intro": "∧-intro：P 和 Q 分别成立，合并为合取式 P∧Q。形式：P, Q ⊢ P∧Q。",
    "∧-elim_l": "∧-elim_l：从合取式 P∧Q 中提取左支 P。形式：P∧Q ⊢ P。",
    "∧-elim_r": "∧-elim_r：从合取式 P∧Q 中提取右支 Q。形式：P∧Q ⊢ Q。",
    "∨-intro": "∨-intro：P 成立时，可以加入任意命题 Q 构成析取式 P∨Q。形式：P ⊢ P∨Q。",
    "∨-elim": "∨-elim (分情况讨论)：P∨Q 成立，分别假设 P 和 Q 都能推出同一结论 R，则 R 成立。",
    "¬¬-elim": "¬¬-elim：双重否定消除，¬¬P 等价于 P。形式：¬¬P ⊢ P。",
    "¬¬-intro": "¬¬-intro：双重否定引入，P 可以得到 ¬¬P。形式：P ⊢ ¬¬P。",
    "→-intro": "→-intro (条件证明)：在假设前件 P 的子证明中推出了后件 Q，因此断言 P→Q 成立。",
    "¬-intro": "¬-intro：假设 α 后推出矛盾 ⊥，因此断言 ¬α 成立。",
    "RAA": "RAA (反证法)：假设 ¬P 后推出矛盾 ⊥，因此断言 P 成立。",
    "¬-elim": "¬-elim：P 和 ¬P 同时成立，推出矛盾 ⊥。",
    "↔-elim": "↔-elim：从 P↔Q 提取正向蕴含 P→Q 或逆向蕴含 Q→P。",
}


def _local_explain_step(step: dict) -> str:
    rule = step.get("rule", "")
    explanation = _RULE_EXPLANATIONS.get(rule)
    if explanation:
        return f"【本地规则库】{explanation}"
    return f"规则 {rule}：从指定行应用推理规则得出当前公式。"
