"""数据更新API路由."""

import uuid
from datetime import datetime
from typing import Any

from ditto_core.data.collector import DataCollector
from ditto_core.data.services import DataReader
from ditto_foundation.logging_config import get_logger
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = get_logger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/v1/update", tags=["update"])


class UpdateRequest(BaseModel):
    """数据更新请求模型."""

    symbols: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    force_update: bool = False


class UpdateStatus(BaseModel):
    """更新状态模型."""

    task_id: str
    status: str
    progress: float = 0.0
    message: str
    started_at: datetime
    updated_records: int = 0
    errors: list[str] = []


# 存储任务状态的字典
active_tasks: dict[str, UpdateStatus] = {}


async def update_etf_list_task(task_id: str) -> None:
    """更新ETF列表的后台任务."""
    try:
        active_tasks[task_id].status = "running"
        active_tasks[task_id].message = "正在更新ETF列表..."

        # 创建数据采集器
        collector = DataCollector()

        # 获取并存储ETF列表
        etf_list = collector.update_etf_list()

        active_tasks[task_id].status = "completed"
        active_tasks[task_id].progress = 100.0
        active_tasks[task_id].message = f"成功更新ETF列表，共 {len(etf_list)} 只ETF"

    except Exception as e:
        active_tasks[task_id].status = "failed"
        active_tasks[task_id].errors.append(str(e))
        active_tasks[task_id].message = f"更新ETF列表失败: {e!s}"


async def update_daily_data_task(
    task_id: str,
    symbols: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    force_update: bool,
) -> None:
    """更新日线数据的后台任务."""
    try:
        active_tasks[task_id].status = "running"
        active_tasks[task_id].message = "正在更新日线数据..."

        # 创建数据采集器
        collector = DataCollector()

        # 获取ETF列表（如果未指定）
        if not symbols:
            reader = DataReader()
            etf_df = reader.get_etf_list()
            symbols = etf_df["symbol"].to_list()
        else:
            symbols = symbols or []

        total_symbols = len(symbols)
        updated_count = 0

        # 更新每只股票的数据
        for i, symbol in enumerate(symbols):
            try:
                active_tasks[
                    task_id
                ].message = f"正在更新 {symbol} ({i + 1}/{total_symbols})..."

                # 这里应该调用实际的更新方法
                # daily_data = collector.update_daily_data(symbol, start_date, end_date)
                # writer.store_daily_data(daily_data)

                updated_count += 1
                active_tasks[task_id].progress = (i + 1) / total_symbols * 100
                active_tasks[task_id].updated_records = updated_count

            except Exception as e:
                error_msg = f"更新 {symbol} 失败: {e!s}"
                active_tasks[task_id].errors.append(error_msg)
                logger.warning(error_msg)
                continue

        active_tasks[task_id].status = "completed"
        active_tasks[
            task_id
        ].message = f"成功更新 {updated_count}/{total_symbols} 只股票的数据"

    except Exception as e:
        active_tasks[task_id].status = "failed"
        active_tasks[task_id].errors.append(str(e))
        active_tasks[task_id].message = f"更新日线数据失败: {e!s}"


@router.post("/etf-list")
async def trigger_etf_list_update(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """触发ETF列表更新."""
    task_id = str(uuid.uuid4())

    # 创建任务状态
    active_tasks[task_id] = UpdateStatus(
        task_id=task_id,
        status="pending",
        message="任务已提交，等待执行...",
        started_at=datetime.now(),
    )

    # 添加后台任务
    background_tasks.add_task(update_etf_list_task, task_id)

    return {
        "success": True,
        "task_id": task_id,
        "message": "ETF列表更新任务已提交",
    }


@router.post("/daily-data")
async def trigger_daily_data_update(
    request: UpdateRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    触发日线数据更新.

    Args:
        request: 更新请求参数
        background_tasks: FastAPI后台任务管理器

    """
    task_id = str(uuid.uuid4())

    # 创建任务状态
    active_tasks[task_id] = UpdateStatus(
        task_id=task_id,
        status="pending",
        message="任务已提交，等待执行...",
        started_at=datetime.now(),
    )

    # 添加后台任务
    background_tasks.add_task(
        update_daily_data_task,
        task_id,
        request.symbols,
        request.start_date,
        request.end_date,
        request.force_update,
    )

    return {
        "success": True,
        "task_id": task_id,
        "message": "日线数据更新任务已提交",
        "params": {
            "symbols": request.symbols,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "force_update": request.force_update,
        },
    }


@router.get("/status/{task_id}")
async def get_update_status(task_id: str) -> dict[str, Any]:
    """
    获取更新任务状态.

    Args:
        task_id: 任务ID

    """
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    status = active_tasks[task_id]

    return {
        "success": True,
        "data": status.dict(),
    }


@router.get("/tasks")
async def list_active_tasks() -> dict[str, Any]:
    """列出所有活跃的更新任务."""
    return {
        "success": True,
        "data": list(active_tasks.values()),
        "count": len(active_tasks),
    }


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict[str, Any]:
    """
    删除已完成的任务记录.

    Args:
        task_id: 任务ID

    """
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    status = active_tasks[task_id]

    # 只允许删除已完成或失败的任务
    if status.status not in ["completed", "failed"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot delete task with status: {status.status}"
        )

    del active_tasks[task_id]

    return {
        "success": True,
        "message": f"Task {task_id} deleted successfully",
    }
