import dsl
import tomllib
import pytest
from easydict import EasyDict
from typing import Optional

def parse_dsl(text: str,
              ctx: Optional[dsl.Ctx] = None) -> (dsl.Ctx, dsl.DslExpr):
    if ctx is None:
        ctx = dsl.Ctx(is_loud=True, is_trace=True, is_inline=True)
    parse_tree = tomllib.loads(text)["body"]
    ast = dsl.parse_dsl(parse_tree, ctx=ctx)
    return (ctx, ast)

def add_library(ctx: dsl.Ctx, **functions):
    config = {
        k: EasyDict({"body": v})
        for k,v in dict(**functions).items()
    }
    ctx.set_config(EasyDict({"lib": config}))

async def test_infinite_recursion():
    ctx, expr = parse_dsl("""
    body = { recurse = [] }
    """)
    add_library(ctx,
                recurse=expr)
    with pytest.raises(RecursionError):
        await expr.evaluate(ctx)
