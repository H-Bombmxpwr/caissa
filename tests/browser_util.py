"""Helpers shared by the Playwright browser suites.

`page.wait_for_function` cannot be trusted with an `async` predicate: it awaits the
promise once and then treats the settled value as satisfying the wait, so
`async()=>false` "succeeds" after one round trip. Every wait that has to ask the
server a question therefore looks like a wait and behaves like a single delay, which
is how a test can pass against a half-built index.

`wait_until` polls with `page.evaluate`, which does await promises and does hand back
the real value, and fails loudly when the condition never becomes true.
"""
import time


def wait_until(page, expression, arg=None, timeout=30.0, every=0.15, what=None):
    """Poll an expression — sync or async — until it returns something truthy."""
    deadline = time.monotonic() + timeout
    last = None
    while True:
        last = page.evaluate(expression, arg) if arg is not None else page.evaluate(expression)
        if last:
            return last
        if time.monotonic() > deadline:
            raise AssertionError('timed out after %gs waiting for %s (last value: %r)'
                                 % (timeout, what or expression.strip()[:90], last))
        time.sleep(every)


def wait_for_index(page, timeout=60.0):
    """Wait for position indexing to finish, not merely to have started."""
    return wait_until(page, '''async()=>{const s=await Caissa.api('study/index');
        return !s.running && s.total>0 && s.done===s.total;}''',
                      timeout=timeout, what='position indexing to finish')
