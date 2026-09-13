from __future__ import annotations

import os
import warnings


def test_configure_runtime_environment_suppresses_known_runtime_warning(monkeypatch) -> None:
    from app.services.agent_runtime import configure_runtime_environment

    monkeypatch.delenv('OPENHANDS_SUPPRESS_BANNER', raising=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        configure_runtime_environment()
        warnings.warn_explicit(
            'Core Pydantic V1 functionality isn\'t compatible with Python 3.14 or greater.',
            category=UserWarning,
            filename='zai/core/_base_compat.py',
            lineno=48,
            module='zai.core._base_compat',
        )

    assert os.environ['OPENHANDS_SUPPRESS_BANNER'] == '1'
    assert caught == []
