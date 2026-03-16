"""
自然演绎证明引擎 - 前向链推理 + 嵌套子证明
支持规则：→-elim, MT, HS, ∧-intro, ∧-elim, ∨-intro, ∨-elim, ¬¬-elim, ¬¬-intro,
         DS, ↔-elim, →-intro, ¬-elim, ¬-intro, RAA
步骤带 depth 字段用于 logicproof 可视化渲染
"""
import time
from dataclasses import dataclass, field
from typing import Optional
from .parser import Formula, parse


@dataclass
class ProofStep:
    """证明步骤"""
    line: int
    formula: Formula
    rule: str
    from_lines: list = field(default_factory=list)
    justification: str = ""
    latex: str = ""
    depth: int = 0          # 子证明嵌套深度（0=顶层）
    is_assumption: bool = False  # 是否为子证明假设行

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "formula": str(self.formula),
            "rule": self.rule,
            "from_lines": self.from_lines,
            "justification": self.justification,
            "latex": self.latex,
            "depth": self.depth,
            "is_assumption": self.is_assumption,
        }


@dataclass
class ProofResult:
    success: bool
    steps: list
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "steps": [s.to_dict() for s in self.steps],
            "message": self.message,
        }


class NaturalDeductionProver:
    """前向链自然演绎证明器"""
    MAX_STEPS = 50
    MAX_KNOWN = 80       # 已知公式数上限，防止组合爆炸
    MAX_DEPTH = 3        # 子证明最大嵌套深度
    TIME_LIMIT = 10.0    # 秒，超时返回失败

    def prove(self, premises: list, goal: str) -> ProofResult:
        self._start_time = time.monotonic()

        try:
            parsed_premises = [parse(p) for p in premises]
            parsed_goal = parse(goal)
        except Exception as e:
            return ProofResult(False, [], f"解析错误: {e}")

        steps: list[ProofStep] = []
        known: list[tuple[Formula, int]] = []
        line = 1

        # 录入前提（depth=0）
        for pf in parsed_premises:
            step = ProofStep(
                line=line, formula=pf, rule="premise",
                justification="premise", latex=pf.to_latex(), depth=0,
            )
            steps.append(step)
            known.append((pf, line))
            line += 1

        # 检查目标是否已在前提中
        if self._already_known(parsed_goal, known):
            return ProofResult(True, steps, "证明完成")

        # 前向链推理
        steps, known, line, found = self._forward_chain(
            steps, known, line, parsed_goal, depth=0
        )
        if found:
            return ProofResult(True, steps, "证明完成")

        if self._timed_out():
            return ProofResult(False, steps, "证明超时，请简化公式或检查前提是否充分")

        # 尝试子证明（→-intro / ¬-intro / RAA）
        result = self._try_sub_proofs(
            parsed_goal, list(steps), list(known), line, depth=0
        )
        if result is not None:
            return ProofResult(True, result, "证明完成")

        return ProofResult(False, steps, "无法完成证明，请检查前提和目标是否合法")

    # ── 核心方法 ──────────────────────────────────────────────

    def _timed_out(self) -> bool:
        return (time.monotonic() - self._start_time) > self.TIME_LIMIT

    def _already_known(self, f: Formula, known: list) -> bool:
        return any(k == f for k, _ in known)

    def _forward_chain(self, steps, known, line, goal, depth):
        """前向链推理，返回 (steps, known, line, found)"""
        conj_targets, disj_targets, nn_targets = self._collect_targets(known, goal)

        for _ in range(self.MAX_STEPS):
            if self._timed_out():
                break
            progress = False
            new_formulas = self._apply_rules(known, conj_targets, disj_targets, nn_targets)
            for new_f, rule, from_lines, just in new_formulas:
                if not self._already_known(new_f, known):
                    step = ProofStep(
                        line=line, formula=new_f, rule=rule,
                        from_lines=from_lines, justification=just,
                        latex=new_f.to_latex(), depth=depth,
                    )
                    steps.append(step)
                    known.append((new_f, line))
                    line += 1
                    progress = True
                    if new_f == goal:
                        return steps, known, line, True
                    if len(known) >= self.MAX_KNOWN:
                        break
            if not progress or len(known) >= self.MAX_KNOWN:
                break

        return steps, known, line, False

    def _try_sub_proofs(self, goal, steps, known, line, depth):
        """尝试 →-intro / ∨-elim / ¬-intro / RAA 子证明，返回步骤列表或 None"""
        if depth >= self.MAX_DEPTH or self._timed_out():
            return None

        # →-intro: 目标为蕴含时
        if goal.type == 'implies':
            result = self._try_cp(goal, steps, known, line, depth)
            if result is not None:
                return result

        # ∨-elim: 已知中有析取式时，分情况讨论
        result = self._try_or_elim(goal, steps, known, line, depth)
        if result is not None:
            return result

        # ¬-intro: 目标为否定时（assume α, derive ⊥, conclude ¬α）
        if goal.type == 'not':
            result = self._try_neg_intro(goal, steps, known, line, depth)
            if result is not None:
                return result

        # RAA: 反证法（目标为正命题时，assume ¬goal, derive ⊥, conclude goal）
        result = self._try_raa(goal, steps, known, line, depth)
        if result is not None:
            return result

        return None

    # ── 目标收集 ──────────────────────────────────────────────

    def _collect_targets(self, known, goal):
        """收集目标导向的合取、析取和双重否定目标
        返回 (conj_targets: set[str], disj_targets: list[Formula], nn_targets: set[str])
        """
        conj_targets = set()
        disj_targets = []
        nn_targets = set()   # 需要 ¬¬-intro 的公式 repr
        seen_disj = set()

        def add_disj(f):
            key = repr(f)
            if key not in seen_disj:
                seen_disj.add(key)
                disj_targets.append(f)

        def collect_nn(f):
            """收集公式中需要 ¬¬-intro 的子公式"""
            if f.type == 'not' and f.left.type == 'not':
                # ¬¬X → X 需要 ¬¬-intro
                nn_targets.add(repr(f.left.left))
            if f.type == 'and':
                collect_nn(f.left)
                collect_nn(f.right)

        def collect_goal_targets(f):
            """递归收集目标中的子合取/析取，使多步 ∨-intro/∧-intro 可行"""
            if f.type == 'and':
                conj_targets.add(repr(f))
                collect_goal_targets(f.left)
                collect_goal_targets(f.right)
            elif f.type == 'or':
                add_disj(f)
                collect_goal_targets(f.left)
                collect_goal_targets(f.right)

        # 从目标收集
        collect_goal_targets(goal)
        collect_nn(goal)

        for f, _ in known:
            # 蕴含前件中的合取/析取
            if f.type == 'implies':
                if f.left.type == 'and':
                    conj_targets.add(repr(f.left))
                if f.left.type == 'or':
                    add_disj(f.left)
                # 蕴含后件为 ¬X → ¬¬X 可用于 MT
                if f.right.type == 'not':
                    nn_targets.add(repr(f.right.left))
            # 否定内部的合取/析取（用于 RAA 中制造矛盾）
            if f.type == 'not':
                if f.left.type == 'and':
                    conj_targets.add(repr(f.left))
                if f.left.type == 'or':
                    add_disj(f.left)

        return conj_targets, disj_targets, nn_targets

    # ── 推理规则 ──────────────────────────────────────────────

    def _apply_rules(self, known, conj_targets=None, disj_targets=None, nn_targets=None):
        """应用所有推理规则（∧-intro/∨-intro/¬¬-intro 限制为目标导向）"""
        if conj_targets is None:
            conj_targets = set()
        if disj_targets is None:
            disj_targets = []
        if nn_targets is None:
            nn_targets = set()
        results = []

        for i, (fi, li) in enumerate(known):
            # ∧-elim: 合取消除（区分左右）
            if fi.type == 'and':
                results.append((fi.left, '∧-elim_l', [li], "∧-elim_l"))
                results.append((fi.right, '∧-elim_r', [li], "∧-elim_r"))
            # ¬¬-elim: 双重否定消除
            if fi.type == 'not' and fi.left.type == 'not':
                results.append((fi.left.left, '¬¬-elim', [li], "¬¬-elim"))
            # ↔-elim: 双条件消除
            if fi.type == 'iff':
                results.append((
                    Formula('implies', left=fi.left, right=fi.right),
                    '↔-elim', [li], "↔-elim"
                ))
                results.append((
                    Formula('implies', left=fi.right, right=fi.left),
                    '↔-elim', [li], "↔-elim"
                ))

            # ¬¬-intro: 双重否定引入（目标导向）
            if fi.type != 'not' and repr(fi) in nn_targets:
                nn_f = Formula('not', left=Formula('not', left=fi))
                results.append((nn_f, '¬¬-intro', [li], "¬¬-intro"))

            # ∨-intro: 析取引入（目标导向）
            for td in disj_targets:
                if fi == td.left:
                    results.append((td, '∨-intro', [li], "∨-intro"))
                if fi == td.right:
                    results.append((td, '∨-intro', [li], "∨-intro"))

            for j, (fj, lj) in enumerate(known):
                if i == j:
                    continue
                # →-elim: 假言推理 (Modus Ponens)
                if fi.type == 'implies' and fi.left == fj:
                    results.append((fi.right, '→-elim', [li, lj], "→-elim"))
                # MT: 拒取式 (Modus Tollens)
                if fi.type == 'implies' and fj.type == 'not' and fj.left == fi.right:
                    results.append((
                        Formula('not', left=fi.left), 'MT', [li, lj], "MT"
                    ))
                # HS: 假言三段论 (Hypothetical Syllogism)
                if fi.type == 'implies' and fj.type == 'implies' and fi.right == fj.left:
                    results.append((
                        Formula('implies', left=fi.left, right=fj.right),
                        'HS', [li, lj], "HS"
                    ))
                # ∧-intro: 合取引入（目标导向）
                if i < j:
                    conj = Formula('and', left=fi, right=fj)
                    if repr(conj) in conj_targets:
                        results.append((conj, '∧-intro', [li, lj], "∧-intro"))
                    conj_rev = Formula('and', left=fj, right=fi)
                    if repr(conj_rev) in conj_targets:
                        results.append((conj_rev, '∧-intro', [lj, li], "∧-intro"))
                # DS: 析取三段论 (Disjunctive Syllogism)
                if fi.type == 'or' and fj.type == 'not' and fj.left == fi.left:
                    results.append((fi.right, 'DS', [li, lj], "DS"))
                if fi.type == 'or' and fj.type == 'not' and fj.left == fi.right:
                    results.append((fi.left, 'DS', [li, lj], "DS"))
                # ∨-elim: 析取消除
                if fi.type == 'or':
                    for k, (fk, lk) in enumerate(known):
                        if k in (i, j):
                            continue
                        if (fj.type == 'implies' and fj.left == fi.left and
                                fk.type == 'implies' and fk.left == fi.right and
                                fj.right == fk.right):
                            results.append((fj.right, '∨-elim', [li, lj, lk], "∨-elim"))
        return results

    # ── →-intro（条件证明）────────────────────────────────────

    def _try_cp(self, goal, steps, known, line, depth):
        """→-intro：假设前件，推导后件"""
        ant = goal.left
        cons = goal.right
        sub_steps = list(steps)
        sub_known = list(known)
        sub_line = line
        sub_depth = depth + 1

        # 假设前件
        assumption_line = sub_line
        sub_steps.append(ProofStep(
            line=sub_line, formula=ant, rule="assumption",
            justification="assumption",
            latex=ant.to_latex(), depth=sub_depth, is_assumption=True,
        ))
        sub_known.append((ant, sub_line))
        sub_line += 1

        # 后件已在假设中（如 P → P）
        if ant == cons:
            return self._close_cp(
                sub_steps, sub_line, goal, assumption_line,
                assumption_line, depth
            )

        # 前向链
        sub_steps, sub_known, sub_line, found = self._forward_chain(
            sub_steps, sub_known, sub_line, cons, sub_depth
        )
        if found:
            return self._close_cp(
                sub_steps, sub_line, goal, assumption_line,
                sub_line - 1, depth
            )

        # 嵌套子证明
        if depth + 1 < self.MAX_DEPTH and not self._timed_out():
            nested = self._try_sub_proofs(
                cons, sub_steps, sub_known, sub_line, depth + 1
            )
            if nested is not None:
                # 嵌套证明推导出了 cons，需要关闭 →-intro
                last_line = nested[-1].line
                return self._close_cp(
                    nested, last_line + 1, goal, assumption_line,
                    last_line, depth
                )

        return None

    def _close_cp(self, steps, line, goal, assumption_line, cons_line, depth):
        """添加 →-intro 结论步骤"""
        steps.append(ProofStep(
            line=line, formula=goal, rule="→-intro",
            from_lines=[assumption_line, cons_line],
            justification="→-intro",
            latex=goal.to_latex(), depth=depth,
        ))
        return steps

    # ── ∨-elim（析取消除 / 分情况讨论）────────────────────────

    def _try_or_elim(self, goal, steps, known, line, depth):
        """∨-elim 子证明：对已知的 A∨B，分别假设 A 和 B 推导 goal"""
        if depth + 1 >= self.MAX_DEPTH or self._timed_out():
            return None

        # 收集已知中的析取式
        disjunctions = [(f, ln) for f, ln in known if f.type == 'or']
        if not disjunctions:
            return None

        for disj, disj_line in disjunctions:
            if self._timed_out():
                return None

            left_case = disj.left
            right_case = disj.right

            # Case 1: assume left_case, try to derive goal
            case1_steps = list(steps)
            case1_known = list(known)
            case1_line = line
            case1_depth = depth + 1

            case1_assumption_line = case1_line
            case1_steps.append(ProofStep(
                line=case1_line, formula=left_case, rule="assumption",
                justification="assumption",
                latex=left_case.to_latex(), depth=case1_depth, is_assumption=True,
            ))
            case1_known.append((left_case, case1_line))
            case1_line += 1

            # 检查目标是否已在假设中
            if left_case == goal:
                case1_found = True
                case1_goal_line = case1_assumption_line
            else:
                case1_steps, case1_known, case1_line, case1_found = self._forward_chain(
                    case1_steps, case1_known, case1_line, goal, case1_depth
                )
                case1_goal_line = case1_line - 1

            # 如果前向链不够，尝试嵌套子证明
            if not case1_found and depth + 1 < self.MAX_DEPTH and not self._timed_out():
                nested = self._try_sub_proofs(
                    goal, case1_steps, case1_known, case1_line, depth + 1
                )
                if nested is not None:
                    case1_steps = nested
                    case1_found = True
                    case1_goal_line = nested[-1].line
                    case1_line = nested[-1].line + 1

            if not case1_found:
                continue

            case1_last_line = case1_steps[-1].line

            # Case 2: assume right_case, try to derive goal
            case2_steps = list(case1_steps)
            case2_known_base = list(known)  # 从原始 known 开始，不包含 case1 的假设
            case2_line = case1_last_line + 1
            case2_depth = depth + 1

            case2_assumption_line = case2_line
            case2_steps.append(ProofStep(
                line=case2_line, formula=right_case, rule="assumption",
                justification="assumption",
                latex=right_case.to_latex(), depth=case2_depth, is_assumption=True,
            ))
            case2_known_base.append((right_case, case2_line))
            case2_line += 1

            if right_case == goal:
                case2_found = True
                case2_goal_line = case2_assumption_line
            else:
                case2_steps, case2_known_base, case2_line, case2_found = self._forward_chain(
                    case2_steps, case2_known_base, case2_line, goal, case2_depth
                )
                case2_goal_line = case2_line - 1

            if not case2_found and depth + 1 < self.MAX_DEPTH and not self._timed_out():
                nested = self._try_sub_proofs(
                    goal, case2_steps, case2_known_base, case2_line, depth + 1
                )
                if nested is not None:
                    case2_steps = nested
                    case2_found = True
                    case2_goal_line = nested[-1].line
                    case2_line = nested[-1].line + 1

            if not case2_found:
                continue

            case2_last_line = case2_steps[-1].line

            # 两个分支都成功，关闭 ∨-elim
            final_line = case2_last_line + 1
            case2_steps.append(ProofStep(
                line=final_line, formula=goal, rule="∨-elim",
                from_lines=[disj_line,
                            case1_assumption_line, case1_last_line,
                            case2_assumption_line, case2_last_line],
                justification="∨-elim",
                latex=goal.to_latex(), depth=depth,
            ))
            return case2_steps

        return None

    # ── ¬-intro（否定引入）────────────────────────────────────

    def _try_neg_intro(self, goal, steps, known, line, depth):
        """¬-intro：目标为 ¬α 时，假设 α，推出矛盾 ⊥，得 ¬α"""
        alpha = goal.left  # goal = ¬α, so α = goal.left
        sub_steps = list(steps)
        sub_known = list(known)
        sub_line = line
        sub_depth = depth + 1

        # 假设 α
        assumption_line = sub_line
        sub_steps.append(ProofStep(
            line=sub_line, formula=alpha, rule="assumption",
            justification="assumption",
            latex=alpha.to_latex(), depth=sub_depth, is_assumption=True,
        ))
        sub_known.append((alpha, sub_line))
        sub_line += 1

        # 前向链（目标是找到矛盾，但用 alpha 的否定作为辅助目标）
        sub_steps, sub_known, sub_line, _ = self._forward_chain(
            sub_steps, sub_known, sub_line, goal, sub_depth
        )

        # 检查矛盾
        contradiction = self._find_contradiction(sub_known)
        if contradiction:
            return self._close_neg_intro(
                sub_steps, sub_known, sub_line, goal,
                assumption_line, contradiction, sub_depth, depth
            )

        # 嵌套子证明：尝试推导能产生矛盾的中间目标
        if depth + 1 < self.MAX_DEPTH and not self._timed_out():
            result = self._try_intermediate_goals(
                goal, sub_steps, sub_known, sub_line,
                assumption_line, sub_depth, depth, is_neg_intro=True
            )
            if result is not None:
                return result

        return None

    def _close_neg_intro(self, steps, known, line, goal,
                         assumption_line, contradiction, sub_depth, depth):
        """添加 ¬-elim (矛盾) + ¬-intro 结论步骤"""
        f_pos, ln_pos, f_neg, ln_neg = contradiction
        bot = Formula('atom', name='\\bot')
        steps.append(ProofStep(
            line=line, formula=bot, rule='¬-elim',
            from_lines=[ln_pos, ln_neg],
            justification="¬-elim",
            latex='\\bot', depth=sub_depth,
        ))
        line += 1
        steps.append(ProofStep(
            line=line, formula=goal, rule='¬-intro',
            from_lines=[assumption_line, line - 1],
            justification="¬-intro",
            latex=goal.to_latex(), depth=depth,
        ))
        return steps

    # ── RAA（反证法 / Proof by Contradiction）─────────────────

    def _try_raa(self, goal, steps, known, line, depth):
        """RAA：假设 ¬goal，推出矛盾，得 goal"""
        neg_goal = Formula('not', left=goal)
        sub_steps = list(steps)
        sub_known = list(known)
        sub_line = line
        sub_depth = depth + 1

        # 假设 ¬goal
        assumption_line = sub_line
        sub_steps.append(ProofStep(
            line=sub_line, formula=neg_goal, rule="assumption",
            justification="assumption",
            latex=neg_goal.to_latex(), depth=sub_depth, is_assumption=True,
        ))
        sub_known.append((neg_goal, sub_line))
        sub_line += 1

        # 前向链
        sub_steps, sub_known, sub_line, _ = self._forward_chain(
            sub_steps, sub_known, sub_line, goal, sub_depth
        )

        # 检查矛盾
        contradiction = self._find_contradiction(sub_known)
        if contradiction:
            return self._close_raa(
                sub_steps, sub_known, sub_line, goal,
                assumption_line, contradiction, sub_depth, depth
            )

        # 嵌套子证明：尝试推导能产生矛盾的中间目标
        if depth + 1 < self.MAX_DEPTH and not self._timed_out():
            result = self._try_intermediate_goals(
                goal, sub_steps, sub_known, sub_line,
                assumption_line, sub_depth, depth, is_neg_intro=False
            )
            if result is not None:
                return result

        return None

    def _try_intermediate_goals(self, goal, steps, known, line,
                                assumption_line, sub_depth, parent_depth,
                                is_neg_intro=False):
        """在子证明中尝试推导中间目标以产生矛盾"""
        intermediate_goals = []

        for f, _ in known:
            if f.type == 'not':
                target = f.left
                if not self._already_known(target, known):
                    if target.type == 'or':
                        # 析取目标：分别尝试推导各析取支（由 ∨-intro 自动合成）
                        if not self._already_known(target.left, known):
                            intermediate_goals.append(target.left)
                        if not self._already_known(target.right, known):
                            intermediate_goals.append(target.right)
                    else:
                        intermediate_goals.append(target)

        # 去重
        seen = set()
        unique = []
        for g in intermediate_goals:
            key = repr(g)
            if key not in seen:
                seen.add(key)
                unique.append(g)
        intermediate_goals = unique

        for sub_goal in intermediate_goals:
            if self._timed_out():
                return None

            # 尝试嵌套子证明
            nested = self._try_sub_proofs(
                sub_goal, list(steps), list(known), line, parent_depth + 1
            )
            if nested is not None:
                # 嵌套证明成功，sub_goal 已被推导出
                sub_goal_line = None
                for s in reversed(nested):
                    if s.formula == sub_goal and s.depth == sub_depth:
                        sub_goal_line = s.line
                        break
                if sub_goal_line is None:
                    sub_goal_line = nested[-1].line

                # 更新 known
                updated_known = list(known)
                for s in nested[len(steps):]:
                    updated_known.append((s.formula, s.line))

                next_line = nested[-1].line + 1

                # 继续前向链
                nested, updated_known, next_line, _ = self._forward_chain(
                    nested, updated_known, next_line, goal, sub_depth
                )

                # 检查矛盾
                contradiction = self._find_contradiction(updated_known)
                if contradiction:
                    if is_neg_intro:
                        return self._close_neg_intro(
                            nested, updated_known, next_line, goal,
                            assumption_line, contradiction, sub_depth, parent_depth
                        )
                    else:
                        return self._close_raa(
                            nested, updated_known, next_line, goal,
                            assumption_line, contradiction, sub_depth, parent_depth
                        )

        return None

    def _close_raa(self, steps, known, line, goal,
                   assumption_line, contradiction, sub_depth, depth):
        """添加 ¬-elim (矛盾) + RAA 结论步骤"""
        f_pos, ln_pos, f_neg, ln_neg = contradiction
        bot = Formula('atom', name='\\bot')
        steps.append(ProofStep(
            line=line, formula=bot, rule='¬-elim',
            from_lines=[ln_pos, ln_neg],
            justification="¬-elim",
            latex='\\bot', depth=sub_depth,
        ))
        line += 1
        steps.append(ProofStep(
            line=line, formula=goal, rule='RAA',
            from_lines=[assumption_line, line - 1],
            justification="RAA",
            latex=goal.to_latex(), depth=depth,
        ))
        return steps

    def _find_contradiction(self, known: list) -> Optional[tuple]:
        """查找矛盾：同时存在 X 和 ¬X"""
        for i, (fi, li) in enumerate(known):
            for j, (fj, lj) in enumerate(known):
                if i != j and fj.type == 'not' and fj.left == fi:
                    return (fi, li, fj, lj)
        return None
