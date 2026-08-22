from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from call_analytics.bootstrap import MSK, build_application
from call_analytics.infra.adapters.reporting import ReportLabReportRenderer
from call_analytics.service import DashboardService
from call_analytics.service.dashboard import CallPageRequest, DashboardFilter
from domain import RecordingId

_STATIC_DIR = Path(__file__).parent / "web_static"
_SATISFACTION = Literal["satisfied", "neutral", "dissatisfied"]


@dataclass(slots=True)
class _State:
    factory: Callable[[], DashboardService]
    clock: Callable[[], datetime]
    dashboard: DashboardService | None = None


def create_app(
    factory: Callable[[], DashboardService] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    state = _State(
        factory=factory or _build_dashboard,
        clock=clock or (lambda: datetime.now(MSK)),
    )
    renderer = ReportLabReportRenderer()
    app = FastAPI(title="MFC Call Quality Dashboard", version="1.0.0")

    def dashboard() -> DashboardService:
        if state.dashboard is None:
            state.dashboard = state.factory()
        return state.dashboard

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/dashboard/summary")
    async def dashboard_summary(
        date_from: date | None = None,
        date_to: date | None = None,
        operator_id: int | None = None,
        satisfaction: _SATISFACTION | None = None,
        query: str = "",
    ) -> dict[str, object]:
        filters = _filters(
            date_from,
            date_to,
            operator_id,
            satisfaction,
            query,
            state.clock(),
        )
        return dict(asdict(await dashboard().summary(filters)))

    @app.get("/api/operators")
    async def list_operators(
        date_from: date | None = None,
        date_to: date | None = None,
        operator_id: int | None = None,
        satisfaction: _SATISFACTION | None = None,
        query: str = "",
    ) -> list[dict[str, object]]:
        filters = _filters(
            date_from,
            date_to,
            operator_id,
            satisfaction,
            query,
            state.clock(),
        )
        return [
            {
                "operator_id": item.id,
                "operator_extension": item.extension,
                "operator_name": item.name,
                "total_calls": item.total_calls,
                "satisfied_percent": item.satisfied_percent,
                "attention_calls": item.attention_calls,
            }
            for item in await dashboard().operators(filters)
        ]

    @app.get("/api/calls")
    async def list_calls(
        date_from: date | None = None,
        date_to: date | None = None,
        operator_id: int | None = None,
        satisfaction: _SATISFACTION | None = None,
        query: str = "",
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, object]:
        filters = _filters(
            date_from,
            date_to,
            operator_id,
            satisfaction,
            query,
            state.clock(),
        )
        result = await dashboard().calls(
            CallPageRequest(filters=filters, page=page, page_size=page_size)
        )
        return {
            "items": [
                {
                    **asdict(item),
                    "started_at": item.started_at.isoformat(),
                }
                for item in result.items
            ],
            "page": result.page,
            "page_size": result.page_size,
            "total_items": result.total_items,
        }

    @app.get("/api/calls/{call_id}/report")
    async def get_report(call_id: str) -> dict[str, object]:
        payload = await dashboard().report(RecordingId(call_id))
        if payload is None:
            raise HTTPException(status_code=404, detail="report not found")
        return payload

    @app.get("/api/calls/{call_id}/report.pdf")
    async def get_report_pdf(call_id: str) -> Response:
        payload = await dashboard().report(RecordingId(call_id))
        if payload is None:
            raise HTTPException(status_code=404, detail="report not found")
        content = await renderer.render_payload(payload)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="call-report.pdf"'},
        )

    @app.get("/api/sync/status")
    async def sync_status() -> dict[str, object]:
        status = await dashboard().sync_status()
        if status is None:
            return {"status": "never"}
        return {
            **asdict(status),
            "window_start": status.window_start.isoformat(),
            "window_end": status.window_end.isoformat(),
            "started_at": status.started_at.isoformat(),
            "finished_at": status.finished_at.isoformat() if status.finished_at else None,
        }

    if _STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(_STATIC_DIR / "index.html")

    return app


def _filters(
    date_from: date | None,
    date_to: date | None,
    operator_id: int | None,
    satisfaction: str | None,
    query: str,
    now: datetime,
) -> DashboardFilter:
    end_date = date_to or now.date()
    start_date = date_from or (end_date - timedelta(days=29))
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    return DashboardFilter(
        date_from=datetime.combine(start_date, time.min, tzinfo=MSK),
        date_to=datetime.combine(end_date, time.max, tzinfo=MSK),
        operator_id=operator_id,
        satisfaction=satisfaction,
        query=query.strip(),
    )


def _build_dashboard() -> DashboardService:
    return build_application().dashboard


app = create_app()

__all__ = ["app", "create_app"]
