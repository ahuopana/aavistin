"""A minimal, safe JSONLogic-subset interpreter.

Hard rule (CLAUDE.md): rule expressions in requirement packages are
evaluated by a safe interpreter, never Python eval/exec. This module is
that interpreter: a fixed whitelist of operators, no access to Python
builtins, names or attributes — an expression can only do what the
operators below let it do.

An expression is either a JSON literal (bool/str/int/float/None), or a
single-key object ``{"op": args}`` where ``op`` is one of the operators
below and ``args`` is a list of sub-expressions (or a single one for
unary operators). ``{"var": "question_id"}`` looks the id up in the data
dict passed to :func:`evaluate`.
"""

from numbers import Number
from typing import Any


class RuleEngineError(Exception):
    pass


def _get_var(args, data):
    if isinstance(args, list):
        name = args[0]
        default = args[1] if len(args) > 1 else None
    else:
        name = args
        default = None
    if not isinstance(name, str):
        raise RuleEngineError(f"'var' name must be a string, got {name!r}")
    return data.get(name, default)


def _as_list(args):
    return args if isinstance(args, list) else [args]


def _eval_and(args, data):
    result: Any = True
    for sub in _as_list(args):
        result = evaluate(sub, data)
        if not result:
            return result
    return result


def _eval_or(args, data):
    result: Any = False
    for sub in _as_list(args):
        result = evaluate(sub, data)
        if result:
            return result
    return result


def _eval_not(args, data):
    values = _as_list(args)
    if len(values) != 1:
        raise RuleEngineError("'!' takes exactly one argument")
    return not evaluate(values[0], data)


def _eval_if(args, data):
    values = _as_list(args)
    if len(values) != 3:
        raise RuleEngineError("'if' takes exactly [condition, then, else]")
    condition, then, otherwise = values
    return evaluate(then, data) if evaluate(condition, data) else evaluate(otherwise, data)


def _binary(op):
    def handler(args, data):
        values = _as_list(args)
        if len(values) != 2:
            raise RuleEngineError(f"{op.__name__} takes exactly two arguments")
        a, b = (evaluate(v, data) for v in values)
        return op(a, b)

    return handler


def _arithmetic(op):
    def handler(args, data):
        values = _as_list(args)
        if len(values) != 2:
            raise RuleEngineError("arithmetic operators take exactly two arguments")
        a, b = (evaluate(v, data) for v in values)
        for v in (a, b):
            if not isinstance(v, Number) or isinstance(v, bool):
                raise RuleEngineError(f"expected a number, got {v!r}")
        return op(a, b)

    return handler


def _comparison(op):
    def handler(args, data):
        values = _as_list(args)
        if len(values) != 2:
            raise RuleEngineError("comparison operators take exactly two arguments")
        a, b = (evaluate(v, data) for v in values)
        # An unanswered question (None) fails a numeric threshold rather
        # than raising: "rated_power_watts > 80" is simply not yet true
        # when the question hasn't been answered.
        if a is None or b is None:
            return False
        for v in (a, b):
            if not isinstance(v, Number) or isinstance(v, bool):
                raise RuleEngineError(f"expected a number, got {v!r}")
        return op(a, b)

    return handler


def _eval_in(args, data):
    values = _as_list(args)
    if len(values) != 2:
        raise RuleEngineError("'in' takes exactly [needle, haystack]")
    needle, haystack = (evaluate(v, data) for v in values)
    return needle in haystack


OPERATORS = {
    "var": _get_var,
    "and": _eval_and,
    "or": _eval_or,
    "!": _eval_not,
    "if": _eval_if,
    "in": _eval_in,
    "==": _binary(lambda a, b: a == b),
    "!=": _binary(lambda a, b: a != b),
    "<": _comparison(lambda a, b: a < b),
    "<=": _comparison(lambda a, b: a <= b),
    ">": _comparison(lambda a, b: a > b),
    ">=": _comparison(lambda a, b: a >= b),
    "+": _arithmetic(lambda a, b: a + b),
    "-": _arithmetic(lambda a, b: a - b),
    "*": _arithmetic(lambda a, b: a * b),
    "/": _arithmetic(lambda a, b: a / b),
}


def evaluate(expression, data: dict) -> Any:
    """Evaluate a JSONLogic-subset ``expression`` against ``data``.

    ``data`` maps question id -> answer value. Never raises anything but
    RuleEngineError for a malformed expression; there is no code path
    that executes arbitrary Python.
    """
    if expression is None or isinstance(expression, (bool, int, float, str)):
        return expression
    if isinstance(expression, list):
        return [evaluate(item, data) for item in expression]
    if not isinstance(expression, dict):
        raise RuleEngineError(f"unsupported expression type: {type(expression).__name__}")
    if len(expression) != 1:
        raise RuleEngineError(f"expression object must have exactly one key: {expression!r}")

    op, args = next(iter(expression.items()))
    handler = OPERATORS.get(op)
    if handler is None:
        raise RuleEngineError(f"unknown operator: {op!r}")
    return handler(args, data)
