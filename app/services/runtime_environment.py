from __future__ import annotations

import os
import warnings


def configure_runtime_environment() -> None:
    os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')
    warnings.filterwarnings(
        'ignore',
        message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater\.",
        category=UserWarning,
        module=r'zai\.core\._base_compat',
    )
