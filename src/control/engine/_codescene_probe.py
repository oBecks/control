"""Throwaway file to check that CodeScene reviews pull requests. Not for merging."""


def probe(a, b, c, d, e):
    result = 0
    if a:
        if b:
            if c:
                if d:
                    if e:
                        for i in range(10):
                            if i % 2:
                                if i > 5:
                                    result += i
                                else:
                                    result -= i
                            else:
                                if i > 3:
                                    result *= 2
                                else:
                                    result += 1
                    else:
                        result = -1
                else:
                    result = -2
            else:
                result = -3
        else:
            result = -4
    else:
        result = -5
    return result
