class EasyDict(dict):
    def __init__(self, t: dict):
        for i in t:
            val = t[i]
            if type(i) is not str:
                continue
            if hasattr(self, i):
                continue
            setattr(self, i, val)
        super().__init__(t)

    def g(self, key: str, default=None):
        return self[key] if key in self else default


def objectify(t):
    if type(t) is dict:
        return EasyDict({k: objectify(v) for k, v in t.items()})
    elif type(t) is list:
        return [objectify(i) for i in t]
    else:
        return t
