"""Throwaway file to check that the new review bot comments on pull requests. Not for merging."""


def describe(devices, mode, verbose, retries, fallback):
    out = []
    for d in devices:
        if mode == "a":
            if verbose:
                if d.get("online"):
                    out.append(d["name"] + " is online")
                elif retries > 0:
                    out.append(d["name"] + " retry")
                else:
                    out.append(fallback)
            elif d.get("online"):
                out.append(d["name"])
        elif mode == "b":
            if verbose and d.get("online") and retries > 0:
                out.append(d["name"] + " b-online")
            elif not d.get("online") and fallback:
                out.append(fallback)
        elif mode == "c":
            try:
                out.append(d["name"].upper())
            except Exception:
                pass
    return out
