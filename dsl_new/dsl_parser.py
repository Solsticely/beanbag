#from dsl_parser import parse_funcvars, Var, Call, FuncVars, RetVal, parse_funclist, Const, ArgCapture, Func, Exprs, parse_expr, Jump
from dsl_ast import Var, Call, FuncVars, RetVal, Const, ArgCapture, Func, Exprs, Jump, Expr
from dsl_tokeniser import END, Tokens

def parse_func(tokens: Tokens) -> Func:
	raise NotImplementedError("AAAAA")
	# tokens.take('func')
	# docstring = tokens.take(STRING) if tokens.peek('doc', take=True) else ""
	# command_name = tokens.take(IDENT)
	# args = parse_sep_list_body(tokens, parse_command_def_argument)
	# body = parse_command_args(tokens)
	# return DslCommandDef(
	#     docstring=docstring,
	#     name=command_name,
	#     args=args,
	#     body=body,
    # )


def parse_funclist(tokens: Tokens) -> list[Func]:
	funcs = []
	while tokens.peek_type != END:
		funcs.append(parse_func(tokens))

	return funcs


def parse_funcvars(tokens: Tokens) -> FuncVars:
	
	raise NotImplementedError("AAAA")

# def parse_sep_list_body(tokens, take_function):
# 	result = []
# 	if tokens.peek('}'): return result
	
# 	while True:
# 		result.append(take_function(tokens))
# 		if tokens.peek('}'):
# 			return result
# 		tokens.take_sep()
# 		if tokens.peek('}'):
# 			return result

def parse_expr(tokens: Tokens) -> Expr:
	"""
		Parses function calls, strings, variables, variable assignments,
		%-expressions, star-expansions, and if statements
	"""
	raise NotImplementedError("AAA")

# Compiled vague LL(1) syntax:
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
