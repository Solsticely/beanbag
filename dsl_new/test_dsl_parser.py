import pytest

from test_dsl_tokeniser import TESTSTRING
from dsl_tokeniser import Tokens
from dsl_parser import parse_funcvars, parse_funclist, parse_expr
from dsl_ast import Var, Call, FuncVars, RetVal, Const, ArgCapture, Func, Exprs, Jump

t = Tokens


def test_parse_funcvars():
    with pytest.raises(SyntaxError):
        parse_funcvars(t('$a, $b=\'2\', $c }'))
        parse_funcvars(t('$a, *, $b, $c }'))
        parse_funcvars(t('$a $b, $c }'))
        parse_funcvars(t('$a, $b, $c=\'d\', * }'))
        parse_funcvars(t('$a, $b, $c, *, * }'))
        parse_funcvars(t(', $a, $b, $c }'))
        parse_funcvars(t('$a, $b=\'ananas\', $c=2 }'))
    assert FuncVars() == parse_funcvars(t('}'))
    assert FuncVars(
        [Var("a"), Var("b", "2"), Var("c", "a")], capture_rest=True
    ) == parse_funcvars(t("$a, $b='2'; $c='a' }"))
    assert FuncVars(capture_rest=True) == parse_funcvars(t('* , }'))


def test_correct_syntax():
    parse_funclist(t(TESTSTRING))


def test_parse_funclist():
    all_funcs = parse_funclist(t('doc[]func a{}{}func b{}{}doc[meow]func a{}{}'))
    for i in all_funcs:
        # All functions must be different from one another
        assert 1 == sum((1 for j in all_funcs if j==i))


def test_parse_func():
    assert [
        Func("name", FuncVars(), Exprs([ArgCapture()]), docstring="docstr")
    ] == parse_funclist(t("doc[docstr]func name{}{*}"))


def test_parse_call():
    assert Call("a", Exprs([Const("boop"), ArgCapture()])) == parse_expr(
        t("a{'boop', *}")
    )


def test_parse_format():
    assert Call("format", Exprs([Const("%s%s"), ArgCapture()])) == parse_expr(
        t("'%s%s' % {*}")
    )


def test_parse_return():
    assert RetVal(Const('hi :)')) == parse_expr(t("return 'hi :)'"))

def test_parse_var_assign():
    assert Call("set", Exprs([Const("var"), Const("value")])) == parse_expr(
        t("$var='value'")
    )

def test_parse_var_retrieve():
    assert Call("get", Exprs([Const("var")]) == parse_expr(t("$var")))


def test_parse_if():
    assert Jump('true', Exprs([Const("if")]), Exprs([Const("else")])) == parse_expr(t("if 'true' { 'if' } else { 'else' }"))
    assert Jump('false', Exprs([Const("there can only be one")])) == parse_expr(t("if 'false' { 'there can only be one' }"))


# Vague LL(1) syntax:
# (verified with https://www.cs.princeton.edu/courses/archive/spring20/cos320/LL1/)

# Funcl ::= ''
# Funcl ::= Func Funcl

# Seps ::= <separator>
# SeplistFuncVar ::= }
# SeplistFuncVar ::= FuncVar Seps SeplistFuncVar
# SeplistExpr ::= }
# SeplistExpr ::= Expr Seps SeplistExpr

# FuncVar ::= doll id FuncVarTail
# FuncVar ::= *
# FuncVarTail ::= ''
# FuncVarTail ::= = str

# Func ::= doc str func id { SeplistFuncVar CallArg
# Func ::= func id { SeplistFuncVar CallArg

# Call ::= id CallArg
# CallArg ::= { SeplistExpr
# CallArg ::= Expr

# Expr ::= Call
# Expr ::= *
# Expr ::= StrOrFormat
# Expr ::= return Expr
# Expr ::= VarOrAssign
# Expr ::= IfExpr

# VarOrAssign ::= doll id VarOrAssign'
# VarOrAssign' ::= ''
# VarOrAssign' ::= = Expr

# StrOrFormat ::= str StrOrFormat'
# StrOrFormat' ::= ''
# StrOrFormat' ::= % CallArg

# IfExpr ::= if Expr { SeplistExpr ElseExpr
# ElseExpr ::= ''
# ElseExpr ::= else { SeplistExpr
