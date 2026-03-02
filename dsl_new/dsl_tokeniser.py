from typing import Union, Optional
# import dsl
import re
# import printutils

# An identifier, of type [a-zA-Z][a-zA-Z0-9]*
IDENT = 1
# End of file
END = 2
# A string, multiline or not doesn't matter
STRING = 4
# A separator. This is only for error handling and is not meant to be an actual
# token.
SEP = 5

TokenType = Union[int, str]

TOKEN_TYPE_NAMES = {
    IDENT: "identifier",
    END: "EOF",
    STRING: "string",
    SEP: "comma, semicolon, newline"
}


def x(**args):
    return dict(args)


# This list is ordered!
TOKEN_SKIP_ARGS = [
    x(type=IDENT, regex=re.compile(r'[a-zA-Z_][a-zA-Z0-9_]*(?![a-zA-Z0-9_])')),
    # Single quote string
    x(type=STRING, regex=re.compile(r"'(([^\\'\n]*(\\.))*[^\\'\n]*)'"), group=1, unescape=True),
    # Multiline string
    x(type=STRING, regex=re.compile(r"\[(([^\\\]]*(\\.))*[^\\\]]*)\]"), group=1, unescape=True),
    x(type=None, regex=re.compile(r'[\*\$\%\{\}\=]'))
]
WHITESPACE_REGEX = re.compile(r'[\t ]*(?![\t \n,;\#])')
IS_AT_SEP_REGEX = re.compile(r'[\t ]*(([\n,;]|#[^\n]+\n)[\t ]*)+(?![\t \n,;\#])')


def token_type_to_str(token: TokenType) -> str:
    return token if isinstance(token, str) else TOKEN_TYPE_NAMES[token]


# class ParsingException(dsl.DslException):
    # pass
class ParsingException(Exception):
    pass


class Tokens:
    def __init__(self, text: str):
        self.text: str = text
        # Index of the character representing the character after the end of the current peek token
        self.peek_end_inx: int = 0
        self.is_at_sep: bool = True
        self.peek_type: TokenType = None
        # Text value of next token, as is read during runtime (e.g. '{', 'string', 'identifier')
        self.peek_text: str
        # Text value of next token, without processing (e.g. '{', "'string'", 'identifier')
        self.peek_true_text: str
        self.expect: list[TokenType] = []
        self.skip()

    def peek_sep(self) -> bool:
        self.expect.append(SEP)
        return self.is_at_sep

    def take_sep(self) -> None:
        if not self.peek_sep():
            self.raise_expect()
        # No need to skip :)

    def skip(self) -> None:
        self.expect = []
        
        # To set: is_at_sep, peek_type, peek_text, peek_true_text, peek_end_inx
        # EOF handling
        if self.peek_type == END:
            return

        # If we can match is_at_sep_regex, we're at a newline.
        self.is_at_sep = self._skip_regex(IS_AT_SEP_REGEX, alter_state=False)
        if not self.is_at_sep:
            self._skip_regex(WHITESPACE_REGEX, alter_state=False)

        for args in TOKEN_SKIP_ARGS:
            if self._skip_regex(**args):
                return

        if self.peek_end_inx >= len(self.text):
            self.peek_type = END
            self.peek_text = ''
            self.peek_true_text = ''
            self.peek_end_inx = len(self.text)
            return
        
        raise ParsingException("Unrecognised token at %s" % self.text[self.peek_end_inx:self.peek_end_inx+10])

    def _skip_regex(self,
                    regex: re.Pattern,
                    type: Optional[TokenType] = None,
                    alter_state: bool = True,
                    group: Union[str, int] = 0,
                    unescape: bool = False) -> bool:
        result = regex.match(self.text, self.peek_end_inx)
        # No match :<
        if result is None:
            return False

        # If not whitespace:
        if alter_state:
            self.peek_true_text = result[0]
            self.peek_text = result[group]
            if unescape:
                self.peek_text = self.peek_text.encode('utf8').decode('unicode_escape')
            
            self.peek_type = self.peek_true_text if type is None else type

        # Adjust pointer for next time :D
        self.peek_end_inx = result.end()
        return True

    def peek(self, expected: Union[int, str], take: bool = False) -> bool:
        self.expect.append(expected)

        if isinstance(expected, str):
            result = expected == self.peek_true_text
        else:
            result = expected == self.peek_type

        if take and result:
            self.skip()

        return result

    def take(self, expected: Union[int, str]) -> str:
        peek_text = self.peek_text

        if not self.peek(expected, take=True):
            self.raise_expect()

        return peek_text

    def raise_expect(self) -> None:
        all_expected = ', '.join(token_type_to_str(i) for i in self.expect)
        raise ParsingException("Expected one of %s, got %s" % (all_expected, token_type_to_str(self.peek_type)))


