import pytest
from dsl_tokeniser import Tokens, STRING, IDENT, ParsingException, END
from typing import Union

TESTSTRING = """
func download_github_artifact { $repo, $regex, $output_file } suppress_tty {
	echo 'Downloading github artifact in %s that matches %s into file %s' % {
		$repo, $regex, $output_file
	}

	# Get release info
	$releaseinfo = curl { 'https://api.github.com/repos/%s/releases/latest' % $repo }
	$nonce = jsonquote randomstr '42'
	$url = jq { '([.assets[]|select(.name|test(%s)).url]+[%s])' % {jsonquote $regex; jsonquote $nonce}; $releaseinfo }
	
	assert_neq { $nonce; $url; 'No suitable github release found for %s' % $repo }
	echo 'Found URL %s' % $url

	# Download the payload
	curl {
		'-H'; 'Accept: application/octet-stream'
		jsonunquote $url
		'--output'; $output_file
	}
	echo 'Finished downloading github artifact to %s'%$output_file
}

func jq { $pattern, $json } {
	# Download Jaq, the rust jq clone
	# TODO: mkdirp, temp dir and temp file names
	if not_exists 'jaq' {
		echo 'First call to jq, downloading jaq...'

		curl{'-o'; 'jaq'; 'https://github.com/01mf02/jaq/releases/latest/download/jaq-%s-unknown-linux-gnu' % $arch}
		chmod{'+x'; 'jaq'}

		echo 'Jaq binary cached!'
	}

	shell_exec 'printf -- \\'%%s\\' %s | ./jaq -- %s | tee' % {shquote $json, shquote $pattern}
}

doc 'Tests the functionality of the tokeniser, parser, and runner :)'
func
test_all_features { $a, $b='tea'
* } cat suppress_tty cat
{
	$c
	=
	'12_%s_%s'
	%
	{cat *, $a, $b}
	assert_neq{$c,'13_%s_%s_%s'%{cat *,$a;$b,
	'a'}};;;;;;;;;
	return cat {$a,[
		multiline string
	]}
	
	# Comment
	
}

# Token types:
#  <identifier> <string> * $ % { } 
"""

@pytest.mark.parametrize("case", ['a\nb', 'a;b', 'a,b','a\nb;\n\n;\n', 'a;;b'])
def test_take_sep(case):
	tokens = Tokens(case)
	tokens.take(IDENT)
	tokens.take_sep()
	tokens.take(IDENT)
	tokens.take(END)


@pytest.mark.parametrize("case", ['a b', 'a b\nb', "a','b", "a,,{\nb}"])
def test_bad_take_sep(case):
	with pytest.raises(ParsingException):
		test_take_sep(case)

def test_tokenisation_result():
    input = """
        doc [ Tests the functionality of the tokeniser, parser, and runner :) ]
        func
        test_all_features { $a, $b='tea'
        * } cat suppress_tty cat
        {
        	$c
        	=
            '12_\\'%s\\'_%s'
        	%
        	{cat *, $a, $b}
            assert_neq{$c,'13_%s_%s_%s'%{cat *,$a;$b,
            'a'}};;;;;;;;;
        	return cat {$a,[\n\t\tmultiline string\n\t]}
	
        	# Comment
	
        }

        # Token types:
        #  <identifier> <string> * $ % { } 
    """
    expected_result = [
        (IDENT,True,'doc'),
        (STRING,False,' Tests the functionality of the tokeniser, parser, and runner :) '),
        (IDENT,True,'func'),(IDENT,True,'test_all_features'),('{',False,'{'),
        ('$',False,'$'),(IDENT,False,'a'),('$',True,'$'),(IDENT,False,'b'),
        ('=',False,'='),(STRING,False,'tea'),('*',True,'*'),('}',False,'}'),
        (IDENT,False,'cat'),(IDENT,False,'suppress_tty'),(IDENT,False,'cat'),
        ('{',True,'{'),('$',True,'$'),(IDENT,False,'c'),('=',True,'='),
        (STRING,True,'12_\'%s\'_%s'),('%',True,'%'),('{',True,'{'),
        (IDENT,False,'cat'),('*',False,'*'),('$',True,'$'),(IDENT,False,'a'),
        ('$',True,'$'),(IDENT,False,'b'),('}',False,'}'),
        (IDENT,True,'assert_neq'),('{',False,'{'),('$',False,'$'),
        (IDENT,False,'c'),(STRING,True,'13_%s_%s_%s'),('%',False,'%'),
        ('{',False,'{'),(IDENT,False,'cat'),('*',False,'*'),('$',True,'$'),
        (IDENT,False,'a'),('$',True,'$'),(IDENT,False,'b'),(STRING,True,'a'),
        ('}',False,'}'),('}',False,'}'),(IDENT,True,'return'),(IDENT,False,'cat'),
        ('{',False,'{'),('$',False,'$'),(IDENT,False,'a'),
        (STRING,True,'\n\t\tmultiline string\n\t'),('}',False,'}'),('}',True,'}')
    ]
    tokens = Tokens(input)
    for i in expected_result:
        assert i == (
            tokens.peek_type, tokens.peek_sep(), tokens.take(tokens.peek_type)
        )


def print_all_tokens(tokens: Union[str, Tokens]):
	if isinstance(tokens, str):
		tokens = Tokens(tokens)

	all_tokens = []
	token_names = {
		STRING: 'str',
		IDENT: 'id',
		END: '$',
		'$': 'doll',
		**{i:i for i in '{}%=*'}
	}
	keywords = {*'return func if not else doc'.split()}

	while True:
		nexttoken = tokens.peek_type
		nexttokenstr = tokens.take(nexttoken)

		if nexttokenstr not in keywords:
			nexttokenstr = token_names[nexttoken]

		all_tokens.append(nexttokenstr)

		if nexttoken == END:
			break

	print(" ".join(all_tokens))
