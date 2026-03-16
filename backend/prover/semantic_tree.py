"""
语义树（Tableau 方法）- 用于判定命题逻辑有效性
"""
from dataclasses import dataclass, field
from typing import Optional
from .parser import Formula, parse


@dataclass
class TableauNode:
    formula: Formula
    signed: bool  # True=T-signed, False=F-signed


@dataclass
class TableauBranch:
    nodes: list[TableauNode] = field(default_factory=list)
    closed: bool = False
    close_reason: str = ""


def tableau_expand(branch: TableauBranch) -> list[TableauBranch]:
    """展开 tableau 分支，返回新分支列表"""
    for i, node in enumerate(branch.nodes):
        if getattr(node, '_expanded', False):
            continue

        f = node.formula
        s = node.signed
        node._expanded = True

        # T-signed rules (formula is True)
        if s:
            if f.type == 'not':
                # T(¬A) → F(A)
                new_node = TableauNode(f.left, False)
                b = TableauBranch(list(branch.nodes) + [new_node])
                return [b]
            elif f.type == 'and':
                # T(A∧B) → T(A), T(B) on same branch
                new_nodes = [TableauNode(f.left, True), TableauNode(f.right, True)]
                b = TableauBranch(list(branch.nodes) + new_nodes)
                return [b]
            elif f.type == 'or':
                # T(A∨B) → split: T(A) | T(B)
                b1 = TableauBranch(list(branch.nodes) + [TableauNode(f.left, True)])
                b2 = TableauBranch(list(branch.nodes) + [TableauNode(f.right, True)])
                return [b1, b2]
            elif f.type == 'implies':
                # T(A→B) → split: F(A) | T(B)
                b1 = TableauBranch(list(branch.nodes) + [TableauNode(f.left, False)])
                b2 = TableauBranch(list(branch.nodes) + [TableauNode(f.right, True)])
                return [b1, b2]
            elif f.type == 'iff':
                # T(A↔B) → split: T(A),T(B) | F(A),F(B)
                b1 = TableauBranch(list(branch.nodes) + [
                    TableauNode(f.left, True), TableauNode(f.right, True)])
                b2 = TableauBranch(list(branch.nodes) + [
                    TableauNode(f.left, False), TableauNode(f.right, False)])
                return [b1, b2]

        # F-signed rules (formula is False)
        else:
            if f.type == 'not':
                # F(¬A) → T(A)
                new_node = TableauNode(f.left, True)
                b = TableauBranch(list(branch.nodes) + [new_node])
                return [b]
            elif f.type == 'and':
                # F(A∧B) → split: F(A) | F(B)
                b1 = TableauBranch(list(branch.nodes) + [TableauNode(f.left, False)])
                b2 = TableauBranch(list(branch.nodes) + [TableauNode(f.right, False)])
                return [b1, b2]
            elif f.type == 'or':
                # F(A∨B) → F(A), F(B) on same branch
                new_nodes = [TableauNode(f.left, False), TableauNode(f.right, False)]
                b = TableauBranch(list(branch.nodes) + new_nodes)
                return [b]
            elif f.type == 'implies':
                # F(A→B) → T(A), F(B) on same branch
                new_nodes = [TableauNode(f.left, True), TableauNode(f.right, False)]
                b = TableauBranch(list(branch.nodes) + new_nodes)
                return [b]
            elif f.type == 'iff':
                # F(A↔B) → split: T(A),F(B) | F(A),T(B)
                b1 = TableauBranch(list(branch.nodes) + [
                    TableauNode(f.left, True), TableauNode(f.right, False)])
                b2 = TableauBranch(list(branch.nodes) + [
                    TableauNode(f.left, False), TableauNode(f.right, True)])
                return [b1, b2]

    return [branch]  # 无可展开节点


def check_closed(branch: TableauBranch) -> tuple[bool, str]:
    """检查分支是否封闭（含矛盾）"""
    atoms_t = {}  # atom_name -> node
    atoms_f = {}

    for node in branch.nodes:
        if node.formula.type == 'atom':
            name = node.formula.name
            if node.signed:
                atoms_t[name] = node
            else:
                atoms_f[name] = node

            if name in atoms_t and name in atoms_f:
                return True, f"矛盾：{name} 同时为真和假"

    return False, ""


def semantic_tableau(premises: list[str], goal: str) -> dict:
    """语义树证明，返回结构化结果"""
    parsed_premises = [parse(p) for p in premises]
    parsed_goal = parse(goal)

    # 初始化：假设所有前提为真，目标为假
    initial_nodes = [TableauNode(pf, True) for pf in parsed_premises]
    initial_nodes.append(TableauNode(parsed_goal, False))
    initial_branch = TableauBranch(initial_nodes)

    branches = [initial_branch]
    steps = []
    step_num = 1
    max_iter = 100

    for _ in range(max_iter):
        all_done = True
        new_branches = []

        for branch in branches:
            if branch.closed:
                new_branches.append(branch)
                continue

            # 检查是否封闭
            closed, reason = check_closed(branch)
            if closed:
                branch.closed = True
                branch.close_reason = reason
                new_branches.append(branch)
                steps.append({
                    "step": step_num,
                    "action": "封闭",
                    "reason": reason,
                })
                step_num += 1
                continue

            # 尝试展开
            expanded = tableau_expand(branch)
            if len(expanded) == 1 and expanded[0] is branch:
                new_branches.append(branch)  # 无法展开
            else:
                new_branches.extend(expanded)
                all_done = False
                steps.append({
                    "step": step_num,
                    "action": f"展开为 {len(expanded)} 支",
                    "formulas": [str(n.formula) for n in expanded[0].nodes[-2:]],
                })
                step_num += 1

        branches = new_branches

        if all(b.closed for b in branches):
            return {
                "valid": True,
                "steps": steps,
                "summary": "所有分支封闭，论证有效（目标被否定导致矛盾）",
            }

        if all_done:
            break

    open_branches = [b for b in branches if not b.closed]
    return {
        "valid": False,
        "steps": steps,
        "open_branches": len(open_branches),
        "summary": f"存在 {len(open_branches)} 个开放分支，论证无效",
    }
