"""数据更新API测试."""

from unittest.mock import Mock, patch

import pytest
from ditto_server.api.update import UpdateStatus, active_tasks
from ditto_server.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """测试客户端."""
    return TestClient(app)


class TestETFListUpdateAPI:
    """ETF列表更新API测试."""

    @patch("ditto_server.api.update.update_etf_list_task")
    def test_trigger_etf_list_update(self, mock_task, client):
        """测试触发ETF列表更新."""
        mock_task.return_value = None

        response = client.post("/api/v1/update/etf-list")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data
        assert data["message"] == "ETF列表更新任务已提交"

        # 检查任务是否已创建
        task_id = data["task_id"]
        assert task_id in active_tasks
        assert active_tasks[task_id].status == "pending"


class TestDailyDataUpdateAPI:
    """日线数据更新API测试."""

    @patch("ditto_server.api.update.update_daily_data_task")
    def test_trigger_daily_data_update(self, mock_task, client):
        """测试触发日线数据更新."""
        mock_task.return_value = None

        request_data = {
            "symbols": ["510300", "159915"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "force_update": True,
        }

        response = client.post("/api/v1/update/daily-data", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data
        assert data["params"] == request_data

        # 检查任务是否已创建
        task_id = data["task_id"]
        assert task_id in active_tasks
        assert active_tasks[task_id].status == "pending"

    @patch("ditto_server.api.update.update_daily_data_task")
    def test_trigger_daily_data_update_all_symbols(self, mock_task, client):
        """测试触发日线数据更新（所有股票）."""
        mock_task.return_value = None

        request_data = {
            "symbols": None,  # 所有股票
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "force_update": False,
        }

        response = client.post("/api/v1/update/daily-data", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["params"]["symbols"] is None


class TestUpdateStatusAPI:
    """更新状态API测试."""

    def test_get_update_status(self, client):
        """测试获取更新状态."""
        # 创建一个测试任务
        task_id = "test_task_001"
        active_tasks[task_id] = UpdateStatus(
            task_id=task_id,
            status="running",
            progress=50.0,
            message="正在更新数据...",
            started_at="2024-01-01T00:00:00",
            updated_records=100,
        )

        response = client.get(f"/api/v1/update/status/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["task_id"] == task_id
        assert data["data"]["status"] == "running"
        assert data["data"]["progress"] == 50.0

    def test_get_update_status_not_found(self, client):
        """测试获取不存在的任务状态."""
        response = client.get("/api/v1/update/status/non_existent_task")

        assert response.status_code == 404
        assert "Task non_existent_task not found" in response.json()["detail"]


class TestActiveTasksAPI:
    """活跃任务API测试."""

    def test_list_active_tasks(self, client):
        """测试列出活跃任务."""
        # 创建多个测试任务
        for i in range(3):
            task_id = f"test_task_{i:03d}"
            active_tasks[task_id] = UpdateStatus(
                task_id=task_id,
                status="running",
                message=f"Task {i}",
                started_at="2024-01-01T00:00:00",
            )

        response = client.get("/api/v1/update/tasks")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 3
        assert len(data["data"]) == 3


class TestDeleteTaskAPI:
    """删除任务API测试."""

    def test_delete_completed_task(self, client):
        """测试删除已完成的任务."""
        # 创建一个已完成的任务
        task_id = "completed_task_001"
        active_tasks[task_id] = UpdateStatus(
            task_id=task_id,
            status="completed",
            message="任务已完成",
            started_at="2024-01-01T00:00:00",
        )

        response = client.delete(f"/api/v1/update/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert task_id not in active_tasks

    def test_delete_running_task(self, client):
        """测试删除运行中的任务（应该失败）."""
        # 创建一个运行中的任务
        task_id = "running_task_001"
        active_tasks[task_id] = UpdateStatus(
            task_id=task_id,
            status="running",
            message="正在运行",
            started_at="2024-01-01T00:00:00",
        )

        response = client.delete(f"/api/v1/update/tasks/{task_id}")

        assert response.status_code == 400
        assert "Cannot delete task with status: running" in response.json()["detail"]
        assert task_id in active_tasks

    def test_delete_nonexistent_task(self, client):
        """测试删除不存在的任务."""
        response = client.delete("/api/v1/update/tasks/non_existent_task")

        assert response.status_code == 404
        assert "Task non_existent_task not found" in response.json()["detail"]


@pytest.mark.asyncio
class TestUpdateTasks:
    """更新任务测试."""

    async def test_update_etf_list_task_success(self):
        """测试ETF列表更新任务成功."""
        task_id = "test_etf_task"

        # 创建任务状态
        active_tasks[task_id] = UpdateStatus(
            task_id=task_id,
            status="pending",
            message="等待执行...",
            started_at="2024-01-01T00:00:00",
        )

        # 模拟数据采集器
        mock_collector = Mock()
        mock_collector.update_etf_list.return_value = [
            {"symbol": "510300", "name": "沪深300ETF"},
            {"symbol": "159915", "name": "创业板ETF"},
        ]

        with patch(
            "ditto_server.api.update.DataCollector", return_value=mock_collector
        ):
            from ditto_server.api.update import update_etf_list_task

            await update_etf_list_task(task_id)

        # 验证任务状态
        assert active_tasks[task_id].status == "completed"
        assert active_tasks[task_id].progress == 100.0
        assert "成功更新ETF列表，共 2 只ETF" in active_tasks[task_id].message

    async def test_update_etf_list_task_failure(self):
        """测试ETF列表更新任务失败."""
        task_id = "test_etf_task_failed"

        # 创建任务状态
        active_tasks[task_id] = UpdateStatus(
            task_id=task_id,
            status="pending",
            message="等待执行...",
            started_at="2024-01-01T00:00:00",
        )

        # 模拟失败的数据采集器
        mock_collector = Mock()
        mock_collector.update_etf_list.side_effect = Exception("API限流")

        with patch(
            "ditto_server.api.update.DataCollector", return_value=mock_collector
        ):
            from ditto_server.api.update import update_etf_list_task

            await update_etf_list_task(task_id)

        # 验证任务状态
        assert active_tasks[task_id].status == "failed"
        assert "更新ETF列表失败: API限流" in active_tasks[task_id].message
        assert len(active_tasks[task_id].errors) > 0
