"""业务服务层（无框架依赖），被 api/cli/jobs 调用。"""

from ditto_port.services import ingestion

__all__ = ["ingestion"]
