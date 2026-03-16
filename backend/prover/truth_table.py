"""
真值表生成器
"""
from itertools import product
from .parser import Formula, parse


def evaluate(formula: Formula, assignment: dict) -> bool:
    """在给定赋值下求公式真值"""
    if formula.type == 'atom':
        return assignment.get(formula.name, False)
    elif formula.type == 'not':
        return not evaluate(formula.left, assignment)
    elif formula.type == 'and':
        return evaluate(formula.left, assignment) and evaluate(formula.right, assignment)
    elif formula.type == 'or':
        return evaluate(formula.left, assignment) or evaluate(formula.right, assignment)
    elif formula.type == 'implies':
        return (not evaluate(formula.left, assignment)) or evaluate(formula.right, assignment)
    elif formula.type == 'iff':
        return evaluate(formula.left, assignment) == evaluate(formula.right, assignment)
    return False


def generate_truth_table(premises: list[str], goal: str) -> dict:
    """生成真值表，返回结构化数据"""
    parsed_premises = [parse(p) for p in premises]
    parsed_goal = parse(goal)

    # 收集所有变量
    atoms = set()
    for pf in parsed_premises:
        atoms |= pf.atoms()
    atoms |= parsed_goal.atoms()
    atoms = sorted(atoms)

    headers = atoms + [str(pf) for pf in parsed_premises] + [str(parsed_goal)]
    rows = []
    is_valid = True
    counterexample = None

    for values in product([False, True], repeat=len(atoms)):
        assignment = dict(zip(atoms, values))

        premise_vals = [evaluate(pf, assignment) for pf in parsed_premises]
        goal_val = evaluate(parsed_goal, assignment)

        all_premises_true = all(premise_vals)

        row = {
            "values": {atom: v for atom, v in assignment.items()},
            "premises": {str(pf): v for pf, v in zip(parsed_premises, premise_vals)},
            "goal": goal_val,
            "all_premises_true": all_premises_true,
            "valid_row": not all_premises_true or goal_val,
        }
        rows.append(row)

        if all_premises_true and not goal_val:
            is_valid = False
            if counterexample is None:
                counterexample = assignment.copy()

    return {
        "atoms": atoms,
        "headers": headers,
        "rows": rows,
        "is_valid": is_valid,
        "counterexample": counterexample,
        "summary": "论证有效：所有前提为真时结论必然为真" if is_valid
                   else f"论证无效：存在反例 {counterexample}",
    }
