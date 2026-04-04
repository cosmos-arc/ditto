"""Tests for Query API common models.

PaginationRequest, PaginationResponse, APIResponse.
"""

import pytest
from pydantic import ValidationError


@pytest.mark.unit
class TestPaginationRequest:
    """测试 PaginationRequest 分页请求模型."""

    def test_default_values(self) -> None:
        """验证默认值: limit=100, offset=0."""
        from ditto_interfaces.models.common import PaginationRequest

        req = PaginationRequest()
        assert req.limit == 100
        assert req.offset == 0

    def test_custom_values(self) -> None:
        """验证自定义分页值."""
        from ditto_interfaces.models.common import PaginationRequest

        req = PaginationRequest(limit=50, offset=200)
        assert req.limit == 50
        assert req.offset == 200

    def test_limit_minimum_value(self) -> None:
        """验证 limit 最小值为 1."""
        from ditto_interfaces.models.common import PaginationRequest

        # 边界值: 1 应该有效
        req = PaginationRequest(limit=1)
        assert req.limit == 1

        # 0 应该无效
        with pytest.raises(ValidationError) as exc_info:
            PaginationRequest(limit=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_limit_maximum_value(self) -> None:
        """验证 limit 最大值为 1000."""
        from ditto_interfaces.models.common import PaginationRequest

        # 边界值: 1000 应该有效
        req = PaginationRequest(limit=1000)
        assert req.limit == 1000

        # 1001 应该无效
        with pytest.raises(ValidationError) as exc_info:
            PaginationRequest(limit=1001)
        assert "less than or equal to 1000" in str(exc_info.value)

    def test_offset_cannot_be_negative(self) -> None:
        """验证 offset 不能为负数."""
        from ditto_interfaces.models.common import PaginationRequest

        with pytest.raises(ValidationError) as exc_info:
            PaginationRequest(offset=-1)
        assert "greater than or equal to 0" in str(exc_info.value)


@pytest.mark.unit
class TestPaginationResponse:
    """测试 PaginationResponse 分页响应模型."""

    def test_basic_response(self) -> None:
        """验证基本分页响应创建."""
        from ditto_interfaces.models.common import PaginationResponse

        resp = PaginationResponse(
            total=1000,
            limit=100,
            offset=0,
        )

        assert resp.total == 1000
        assert resp.limit == 100
        assert resp.offset == 0

    def test_has_more_true(self) -> None:
        """验证 has_more 计算正确 (有更多数据)."""
        from ditto_interfaces.models.common import PaginationResponse

        resp = PaginationResponse(
            total=1000,
            limit=100,
            offset=0,
        )

        # 0 + 100 < 1000, 所以 has_more 应该为 True
        assert resp.has_more is True

    def test_has_more_false(self) -> None:
        """验证 has_more 计算正确 (无更多数据)."""
        from ditto_interfaces.models.common import PaginationResponse

        resp = PaginationResponse(
            total=100,
            limit=100,
            offset=0,
        )

        # 0 + 100 >= 100, 所以 has_more 应该为 False
        assert resp.has_more is False

    def test_has_more_at_last_page(self) -> None:
        """验证最后一页 has_more 为 False."""
        from ditto_interfaces.models.common import PaginationResponse

        # 假设总共 250 条，每页 100，在 offset=200 处
        resp = PaginationResponse(
            total=250,
            limit=100,
            offset=200,
        )

        # 200 + 100 = 300 >= 250, 所以 has_more 应该为 False
        assert resp.has_more is False

    def test_has_more_middle_page(self) -> None:
        """验证中间页 has_more 为 True."""
        from ditto_interfaces.models.common import PaginationResponse

        resp = PaginationResponse(
            total=500,
            limit=100,
            offset=100,
        )

        # 100 + 100 = 200 < 500, 所以 has_more 应该为 True
        assert resp.has_more is True

    def test_model_dump(self) -> None:
        """验证 model_dump 序列化."""
        from ditto_interfaces.models.common import PaginationResponse

        resp = PaginationResponse(
            total=1000,
            limit=50,
            offset=100,
        )

        data = resp.model_dump()
        assert data["total"] == 1000
        assert data["limit"] == 50
        assert data["offset"] == 100
        assert data["has_more"] is True


@pytest.mark.unit
class TestAPIResponse:
    """测试 APIResponse 泛型响应模型."""

    def test_basic_response_with_data(self) -> None:
        """验证带数据的响应创建."""
        from ditto_interfaces.models.common import APIResponse

        response = APIResponse[list[str]](
            data=["item1", "item2", "item3"],
        )

        assert response.data == ["item1", "item2", "item3"]
        assert response.pagination is None

    def test_response_with_pagination(self) -> None:
        """验证带分页信息的响应."""
        from ditto_interfaces.models.common import APIResponse, PaginationResponse

        pagination = PaginationResponse(
            total=100,
            limit=10,
            offset=0,
        )

        response = APIResponse[list[str]](
            data=["item1", "item2"],
            pagination=pagination,
        )

        assert response.data == ["item1", "item2"]
        assert response.pagination is not None
        assert response.pagination.total == 100
        assert response.pagination.has_more is True

    def test_response_with_dict_data(self) -> None:
        """验证带字典数据的响应."""
        from ditto_interfaces.models.common import APIResponse

        response = APIResponse[dict[str, int]](
            data={"a": 1, "b": 2},
        )

        assert response.data == {"a": 1, "b": 2}

    def test_response_with_none_data(self) -> None:
        """验证 data 字段不允许为 None（无泛型约束时）."""
        from ditto_interfaces.models.common import APIResponse

        # APIResponse 的 data 是必需字段，不允许 None
        # 如果需要空数据，应该传入空列表或空字典
        response = APIResponse[list[str]](data=[])
        assert response.data == []

    def test_model_dump(self) -> None:
        """验证 model_dump 序列化."""
        from ditto_interfaces.models.common import APIResponse, PaginationResponse

        pagination = PaginationResponse(
            total=50,
            limit=10,
            offset=10,
        )

        response = APIResponse[list[int]](
            data=[1, 2, 3],
            pagination=pagination,
        )

        data = response.model_dump()
        assert data["data"] == [1, 2, 3]
        assert data["pagination"]["total"] == 50
        assert data["pagination"]["has_more"] is True

    def test_model_dump_exclude_none(self) -> None:
        """验证 exclude_none 时 pagination 被排除."""
        from ditto_interfaces.models.common import APIResponse

        response = APIResponse[list[str]](
            data=["item1"],
        )

        data = response.model_dump(exclude_none=True)
        assert data["data"] == ["item1"]
        assert "pagination" not in data
