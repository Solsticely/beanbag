import dataclasses
# from dsl_ast import Var, Call, FuncVars, RetVal, Const, ArgCapture, Func, Exprs, Jump

class Expr:
	pass


@dataclasses.dataclass
class Var:
	name: str
	default: str = ''


@dataclasses.dataclass
class Exprs:
	exprs: list[Expr] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class FuncVars:
	vars: list[Var] = dataclasses.field(default_factory=list)
	capture_rest: bool = False


@dataclasses.dataclass
class Const(Expr):
	value: str


@dataclasses.dataclass
class RetVal(Expr):
	value: Expr = dataclasses.field(default_factory=lambda:Const(""))


@dataclasses.dataclass
class ArgCapture(Expr):
	pass


@dataclasses.dataclass
class Func:
	name: str
	vars: FuncVars = dataclasses.field(default_factory=Exprs)
	exprs: Exprs = dataclasses.field(default_factory=Exprs)
	docstring: str = ''


@dataclasses.dataclass
class Call(Expr):
	func_name: str
	exprs: Exprs = dataclasses.field(default_factory=Exprs)


@dataclasses.dataclass
class Jump(Expr):
    condition: Expr
    expr_true: Exprs
    expr_false: Exprs = dataclasses.field(default_factory=Exprs)
