def truncate(text: str, length: int = 85) -> str:
    return text[:length] + (" [···]" if len(text) > length else "")


def shrink_lines(text: str) -> str:
    return text.replace("\n", '\u23ce')


def clean(text: str, trunc_length: int = 85) -> str:
    return shrink_lines(truncate(text, trunc_length))

