def parse_command_def(tokens):
	tokens.take('func')
	docstring = tokens.take(STRING) if tokens.peek('doc', take=True) else ""
	command_name = tokens.take(IDENT)
	args = parse_sep_list_body(tokens, parse_command_def_argument)
	body = parse_command_args(tokens)
	return DslCommandDef(
	    docstring=docstring,
	    name=command_name,
	    args=args,
	    body=body,
    )

def parse_command_def_argument(tokens):
	raise NotImplementedException("AAA")

def parse_sep_list_body(tokens, take_function):
	result = []
	if tokens.peek('}'): return result
	
	while True:
		result.append(take_function(tokens))
		if tokens.peek('}'):
			return result
		tokens.take_sep()
		if tokens.peek('}'):
			return result

def parse_expr(tokens):
	"""
		Parses function calls, strings, variables, variable assignments,
		%-expressions, star-expansions, and if statements
	"""
	raise NotImplementedException("AAA")


def parse_command_args(tokens):
	if not tokens.peek('{', take=True):
		return [parse_expr()]
	body = parse_body(tokens)
	tokens.take('}')
	return body



