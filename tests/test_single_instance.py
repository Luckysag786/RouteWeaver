import sys
import uuid

import pytest

from routeweaver.platform.windows_single_instance import acquire_single_instance


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named mutex only")
def test_named_mutex_allows_only_one_process_instance():
    name = rf"Local\RouteWeaver-Test-{uuid.uuid4()}"
    first = acquire_single_instance(name)
    assert first is not None
    try:
        assert acquire_single_instance(name) is None
    finally:
        first.close()

    replacement = acquire_single_instance(name)
    assert replacement is not None
    replacement.close()
