"""
命题逻辑公式解析器 - 递归下降解析
支持: -> (蕴含), <-> (双条件), | (析取), & (合取), ~ (否定)
优先级: ~ > & > | > -> > <->
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Formula:
    """命题逻辑公式节点"""
    type: str  # 'atom', 'not', 'and', 'or', 'implies', 'iff'
    left: Optional['Formula'] = None
    right: Optional['Formula'] = None
    name: Optional[str] = None  # 仅 atom 使用

    def __repr__(self):
        return self.to_str()

    def to_str(self, parent_prec: int = 0) -> str:
        prec_map = {'iff': 1, 'implies': 2, 'or': 3, 'and': 4, 'not': 5}
        if self.type == 'atom':
            return self.name
        elif self.type == 'not':
            inner = self.left.to_str(prec_map['not'])
            return f'¬{inner}'
        elif self.type == 'and':
            prec = prec_map['and']
            left = self.left.to_str(prec)
            right = self.right.to_str(prec + 1)
            s = f'{left} ∧ {right}'
            return f'({s})' if parent_prec > prec else s
        elif self.type == 'or':
            prec = prec_map['or']
            left = self.left.to_str(prec)
            right = self.right.to_str(prec + 1)
            s = f'{left} ∨ {right}'
            return f'({s})' if parent_prec > prec else s
        elif self.type == 'implies':
            prec = prec_map['implies']
            left = self.left.to_str(prec + 1)
            right = self.right.to_str(prec)
            s = f'{left} → {right}'
            return f'({s})' if parent_prec > prec else s
        elif self.type == 'iff':
            prec = prec_map['iff']
            left = self.left.to_str(prec + 1)
            right = self.right.to_str(prec + 1)
            s = f'{left} ↔ {right}'
            return f'({s})' if parent_prec > prec else s
        return '?'

    def to_latex(self) -> str:
        if self.type == 'atom':
            return self.name
        elif self.type == 'not':
            return f'\\lnot {self.left.to_latex()}'
        elif self.type == 'and':
            return f'({self.left.to_latex()} \\land {self.right.to_latex()})'
        elif self.type == 'or':
            return f'({self.left.to_latex()} \\lor {self.right.to_latex()})'
        elif self.type == 'implies':
            return f'({self.left.to_latex()} \\rightarrow {self.right.to_latex()})'
        elif self.type == 'iff':
            return f'({self.left.to_latex()} \\leftrightarrow {self.right.to_latex()})'
        return '?'

    def atoms(self) -> set:
        """获取公式中所有命题变量"""
        if self.type == 'atom':
            return {self.name}
        result = set()
        if self.left:
            result |= self.left.atoms()
        if self.right:
            result |= self.right.atoms()
        return result

    def __eq__(self, other):
        if not isinstance(other, Formula):
            return False
        return (self.type == other.type and
                self.name == other.name and
                self.left == other.left and
                self.right == other.right)

    def __hash__(self):
        return hash(repr(self))


class ParseError(Exception):
    pass


class Parser:
    """递归下降公式解析器"""

    def __init__(self, text: str):
        # 规范化输入
        self.tokens = self._tokenize(text.strip())
        self.pos = 0

    def _tokenize(self, text: str) -> list:
        tokens = []
        i = 0
        while i < len(text):
            c = text[i]
            if c.isspace():
                i += 1
            elif c == '<' and text[i:i+3] == '<->':
                tokens.append('<->')
                i += 3
            elif c == '-' and text[i:i+2] == '->':
                tokens.append('->')
                i += 2
            elif c in '~!':
                tokens.append('~')
                i += 1
            elif c in '&∧':
                tokens.append('&')
                i += 1
            elif c in '|∨':
                tokens.append('|')
                i += 1
            elif c == '↔':
                tokens.append('<->')
                i += 1
            elif c == '→':
                tokens.append('->')
                i += 1
            elif c == '¬':
                tokens.append('~')
                i += 1
            elif c in '()':
                tokens.append(c)
                i += 1
            elif c.isalpha():
                j = i
                while j < len(text) and (text[j].isalnum() or text[j] == '_'):
                    j += 1
                tokens.append(text[i:j])
                i = j
            else:
                raise ParseError(f"未知字符: '{c}'")
        return tokens

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected=None):
        tok = self.peek()
        if expected and tok != expected:
            raise ParseError(f"期望 '{expected}'，得到 '{tok}'")
        self.pos += 1
        return tok

    def parse(self) -> Formula:
        f = self.parse_iff()
        if self.pos < len(self.tokens):
            raise ParseError(f"意外的 token: '{self.tokens[self.pos]}'")
        return f

    def parse_iff(self) -> Formula:
        left = self.parse_implies()
        while self.peek() == '<->':
            self.consume()
            right = self.parse_implies()
            left = Formula('iff', left=left, right=right)
        return left

    def parse_implies(self) -> Formula:
        left = self.parse_or()
        if self.peek() == '->':
            self.consume()
            right = self.parse_implies()  # 右结合
            return Formula('implies', left=left, right=right)
        return left

    def parse_or(self) -> Formula:
        left = self.parse_and()
        while self.peek() == '|':
            self.consume()
            right = self.parse_and()
            left = Formula('or', left=left, right=right)
        return left

    def parse_and(self) -> Formula:
        left = self.parse_not()
        while self.peek() == '&':
            self.consume()
            right = self.parse_not()
            left = Formula('and', left=left, right=right)
        return left

    def parse_not(self) -> Formula:
        if self.peek() == '~':
            self.consume()
            operand = self.parse_not()
            return Formula('not', left=operand)
        return self.parse_atom()

    def parse_atom(self) -> Formula:
        tok = self.peek()
        if tok == '(':
            self.consume('(')
            f = self.parse_iff()
            self.consume(')')
            return f
        elif tok and tok[0].isalpha():
            self.consume()
            return Formula('atom', name=tok)
        elif tok is None:
            raise ParseError("意外的公式结尾")
        else:
            raise ParseError(f"期望原子命题或括号，得到 '{tok}'")


def parse(text: str) -> Formula:
    """解析公式字符串，返回 Formula 树"""
    return Parser(text).parse()
