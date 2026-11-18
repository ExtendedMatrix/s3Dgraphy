"""ESEMPIO INVENTATO (D-5) — non citare. / INVENTED EXAMPLE — not to be cited.

A plugin stub: it proposes nothing. W1 never runs it; it is here so the
envelope has a code section to partition."""


def setup(ctx):
    return None


def teardown(ctx):
    return None


plugin = type("Plugin", (), {"setup": staticmethod(setup), "teardown": staticmethod(teardown)})
