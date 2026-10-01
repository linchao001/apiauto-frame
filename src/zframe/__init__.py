"""ZFrame — multi-product API automation framework."""

from zframe.__version__ import __version__
from zframe.api import *  # noqa: F403
from zframe.api import __all__ as _api_all

__all__ = ["__version__", *_api_all]
