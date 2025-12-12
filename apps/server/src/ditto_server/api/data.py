"""数据查询API路由."""

from datetime import datetime
from typing import Any

from ditto_core.data.services import DataReader
from fastapi import APIRouter, HTTPException, Query

# 创建路由器
router = APIRouter(prefix="/api/v1/data", tags=["data"])


def get_data_readers() -> tuple[DataReader, DataReader]:
    """获取数据读取器实例."""
    # 新的DataReader自动管理两个数据库连接
    market_reader = DataReader()  # 用于市场数据(ETF、日线、复权因子等)

    # 对于交易数据, 可以创建另一个DataReader实例
    # 或者扩展DataReader来支持SQLite表
    trading_reader = DataReader()  # 暂时使用同一个实例

    return market_reader, trading_reader


@router.get("/etf/list")
async def get_etf_list() -> dict[str, Any]:
    """获取ETF列表."""
    try:
        daily_reader, _ = get_data_readers()
        df = daily_reader.get_etf_list()
        return {
            "success": True,
            "data": df.to_dicts(),
            "count": len(df),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch ETF list: {e!s}"
        ) from e


@router.get("/etf/{symbol}/daily")
async def get_daily_data(
    symbol: str,
    start_date: str = Query(..., description="开始日期, 格式: YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期, 格式: YYYY-MM-DD"),
    adjusted: bool = Query(True, description="是否使用复权数据"),
) -> dict[str, Any]:
    """
    获取ETF日线数据.

    Args:
        symbol: ETF代码
        start_date: 开始日期
        end_date: 结束日期
        adjusted: 是否使用复权数据

    """
    try:
        # 验证日期格式
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")

        daily_reader, _ = get_data_readers()
        df = daily_reader.get_daily_data(
            symbol=symbol, start_date=start_date, end_date=end_date, adjusted=adjusted
        )

        if df.is_empty():
            return {
                "success": True,
                "data": [],
                "count": 0,
                "message": f"No data found for {symbol} in the specified date range",
            }

        return {
            "success": True,
            "data": df.to_dicts(),
            "count": len(df),
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "adjusted": adjusted,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid date format: {e!s}"
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch daily data: {e!s}"
        ) from e


@router.get("/etf/{symbol}/adjustments")
async def get_adjustment_factors(
    symbol: str,
    start_date: str = Query(None, description="开始日期, 格式: YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期, 格式: YYYY-MM-DD"),
) -> dict[str, Any]:
    """
    获取复权因子.

    Args:
        symbol: ETF代码
        start_date: 可选，开始日期
        end_date: 可选，结束日期

    """
    try:
        # 验证日期格式（如果提供）
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")

        daily_reader, _ = get_data_readers()
        df = daily_reader.get_adjustment_factors(
            symbol=symbol, start_date=start_date, end_date=end_date
        )

        if df.is_empty():
            return {
                "success": True,
                "data": [],
                "count": 0,
                "message": f"No adjustment factors found for {symbol}",
            }

        return {
            "success": True,
            "data": df.to_dicts(),
            "count": len(df),
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid date format: {e!s}"
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch adjustment factors: {e!s}"
        ) from e


@router.get("/trading/calendar")
async def get_trading_calendar(
    start_date: str = Query(..., description="开始日期, 格式: YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期, 格式: YYYY-MM-DD"),
) -> dict[str, Any]:
    """
    获取交易日历.

    Args:
        start_date: 开始日期
        end_date: 结束日期

    """
    try:
        # 验证日期格式
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")

        _, trading_reader = get_data_readers()
        df = trading_reader.get_trading_calendar(
            start_date=start_date, end_date=end_date
        )

        if df.is_empty():
            return {
                "success": True,
                "data": [],
                "count": 0,
                "message": "No trading days found in the specified date range",
            }

        return {
            "success": True,
            "data": df.to_dicts(),
            "count": len(df),
            "start_date": start_date,
            "end_date": end_date,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid date format: {e!s}"
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch trading calendar: {e!s}"
        ) from e


# @router.get("/quality/report")
# async def get_data_quality_report(
#     symbol: str = Query(None, description="可选，特定ETF代码"),
#     start_date: str = Query(None, description="可选，开始日期"),
#     end_date: str = Query(None, description="可选，结束日期"),
# ) -> dict[str, Any]:
#     """
#     获取数据质量报告.
#
#     Args:
#         symbol: 可选，特定ETF代码
#         start_date: 可选，开始日期
#         end_date: 可选，结束日期
#
#     """
#     try:
#         daily_reader, _ = get_data_readers()
#         # TODO: Implement data quality reporter
#         # reporter = DataQualityReporter(daily_reader)
#
#         # 生成报告
#         # if symbol and start_date and end_date:
#         #     # 特定股票的时间段报告
#         #     report = reporter.generate_symbol_report(
#         #         symbol=symbol, start_date=start_date, end_date=end_date
#         #     )
#         # else:
#         #     # 全市场报告
#         #     report = reporter.generate_market_report()
#
#         return {
#             "success": True,
#             "data": {"message": "Data quality report not yet implemented"},
#             "generated_at": datetime.now().isoformat(),
#         }
#     except Exception as e:
#         raise HTTPException(
#             status_code=500, detail=f"Failed to generate data quality report: {e!s}"
#         )
