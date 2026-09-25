import logging

import pytest

from control.__main__ import QuietReads


def access_record(method, status):
    return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                             ("127.0.0.1:5000", method, "/api/devices", "1.1", status), None)


@pytest.mark.parametrize("method, status, logged", [
    ("GET", 200, False),  # the UI's polling
    ("GET", 404, True),
    ("POST", 200, True),  # a change
    ("DELETE", 204, True),
])
def test_access_log_keeps_changes_and_errors(method, status, logged):
    assert QuietReads().filter(access_record(method, status)) is logged
