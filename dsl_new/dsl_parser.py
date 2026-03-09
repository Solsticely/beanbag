#from dsl_parser import parse_funcvars, Var, Call, FuncVars, RetVal, parse_funclist, Const, ArgCapture, Func, Exprs, parse_expr, Jump
from dsl_ast import Var, Call, FuncVars, RetVal, Const, ArgCapture, Func, Exprs, Jump, Expr
from dsl_tokeniser import END, STRING, IDENT, Tokens

def parse_func(tokens: Tokens) -> Func:
	if tokens.peek('doc', take=True):
		docstring = tokens.take(STRING)
	else:
		docstring = ""

	tokens.take('func')
	func_name = tokens.take(IDENT)
	tokens.take('{')
	vars = parse_funcvars(tokens)
	tokens.take('}')

	if tokens.peek(IDENT):
		body = Exprs([parse_call(tokens)])
	else:
		tokens.take('{')
		body = parse_exprs(tokens)
		tokens.take('}')

	return Func(
		name=func_name,
		vars=vars,
		exprs=body,
		docstring=docstring
	)


def parse_call_args(tokens: Tokens) -> Exprs:
	if tokens.peek('{', take=True):
		args = parse_exprs(tokens)
		tokens.take('}')
	else:
		args = Exprs([parse_expr(tokens)])

	return args


def parse_call(tokens: Tokens) -> Call:
	func_name = tokens.take(IDENT)
	args = parse_call_args(tokens)

	return Call(func_name=func_name, exprs=args)


def parse_funclist(tokens: Tokens) -> list[Func]:
	funcs = []
	while tokens.peek_type != END:
		funcs.append(parse_func(tokens))

	return funcs


def parse_funcvars(tokens: Tokens) -> FuncVars:
	reached_kw = False
	vars = []
	
	while tokens.peek('$', take=True):
		var_name = tokens.take(IDENT)
		var_default = ''
		if tokens.peek('=', take=True) or reached_kw:
			reached_kw = True
			var_default = tokens.take(STRING)

		vars.append(Var(name=var_name, default=var_default))
		
		if not tokens.peek_sep():
			break

	capture_rest = tokens.peek('*', take=True)

	return FuncVars(vars=vars, capture_rest=capture_rest)


def parse_expr(tokens: Tokens) -> Expr:
	"""
		Parses function calls, strings, variables, variable assignments,
		%-expressions, star-expansions, and if statements
	"""
	if tokens.peek('return'):
		return parse_return(tokens)
	elif tokens.peek('if'):
		return parse_if(tokens)
	elif tokens.peek(IDENT):
		return parse_call(tokens)
	elif tokens.peek('$'):
		return parse_var_or_assign(tokens)
	elif tokens.peek(STRING):
		return parse_string_or_format(tokens)
	else:
		tokens.take('*')
		return ArgCapture()


def parse_return(tokens: Tokens) -> Expr:
	tokens.take('return')
	if tokens.peek_sep():
		return RetVal()
	return RetVal(parse_expr(tokens))


def parse_string_or_format(tokens: Tokens) -> Expr:
	string = Const(tokens.take(STRING))
	if not tokens.peek('%', take=True):
		return string

	args = parse_call_args(tokens)
	args.exprs = [string] + args.exprs

	return Call(func_name="format", exprs=args)


def parse_if(tokens: Tokens) -> Expr:
	tokens.take('if')
	cond = parse_expr(tokens)

	tokens.take('{')
	true_path = parse_exprs(tokens)
	tokens.take('}')

	if not tokens.peek('else', take=True):
		return Jump(cond, true_path)

	if tokens.peek('if'):
		false_path = Exprs([parse_if(tokens)])
	else:
		tokens.take('{')
		false_path = parse_exprs(tokens)
		tokens.take('}')

	return Jump(cond, true_path, false_path)


def parse_var_or_assign(tokens: Tokens) -> Expr:
	tokens.take('$')
	name = Const(tokens.take(IDENT))

	if not tokens.peek('=', take=True):
		return Call(func_name='get', exprs=Exprs([name]))

	value = parse_expr(tokens)

	return Call(func_name='set', exprs=Exprs([name, value]))


def parse_exprs(tokens: Tokens) -> Exprs:
	exprs = []
	while not tokens.peek('}'):
		exprs.append(parse_expr(tokens))

		if not tokens.peek_sep():
			break

	return Exprs(exprs=exprs)

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
