"""Ditto 数据模块."""

from ditto_datahub.hub import DataHub
from ditto_datahub.init_providers import register_datahub_providers

__all__ = ["DataHub", "register_datahub_providers"]
