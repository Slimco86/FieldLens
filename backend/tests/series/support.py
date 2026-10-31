"""Synthetic fixtures for the series tests (invented wells/values; no Volve content)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL, Engine

from tests.profile_support import xlsx_bytes
from tests.upload_support import Api, make_api

NULL = -999.25


def las_text(
    rows: list[list[float | str]],
    *,
    curves: tuple[tuple[str, str], ...] = (("DEPT", "M"), ("GR", "GAPI"), ("RHOB", "----")),
    well: str = "15/9-F-99",
    null: str = "-999.25",
    index_unit: str | None = None,
) -> str:
    cur = "".join(
        f" {n}.{index_unit if i == 0 and index_unit is not None else u}   : {n} curve\n"
        for i, (n, u) in enumerate(curves)
    )
    data = "".join(" " + " ".join(str(v) for v in row) + "\n" for row in rows)
    return (
        "~VERSION INFORMATION\n VERS.   2.0 : CWLS\n WRAP.   NO  : ONE LINE\n"
        f"~WELL INFORMATION\n STRT.M   1.0 : S\n STOP.M   9.0 : E\n NULL.    {null} : NULL\n"
        f" WELL.    {well} : WELL\n DATE.    : LOG DATE\n~CURVE INFORMATION\n{cur}~A\n{data}"
    )


DAILY_HEAD = [
    "DATEPRD",
    "WELL_BORE_CODE",
    "NPD_WELL_BORE_NAME",
    "NPD_WELL_BORE_CODE",
    "ON_STREAM_HRS",
    "BORE_OIL_VOL",
    "BORE_GAS_VOL",
    "BORE_WAT_VOL",
    "BORE_WI_VOL",
    "FLOW_KIND",
    "WELL_TYPE",
]
MONTHLY_HEAD = ["Wellbore name", "NPDCode", "Year", "Month", "On Stream", "Oil", "Gas", "Water"]


def day_row(serial: int, bore: str, code: int, oil: Any, hours: Any = 24) -> list[Any]:
    return [("date", serial), f"NO {bore}", bore, code, hours, oil, "NULL", None, None, "production", "OP"]


def workbook_bytes(daily: list[list[Any]]) -> bytes:
    return xlsx_bytes(
        {
            "Daily Production Data": [DAILY_HEAD, *daily],
            "Monthly Production Data": [MONTHLY_HEAD, [None, None, None, None, "Hrs", "Sm3", "Sm3", "Sm3"]],
        }
    )


class Lane:
    """A project with uploaded documents driven through extraction (PostgreSQL)."""

    def __init__(self, url: URL, tmp_path: Path, engine: Engine, **overrides: Any) -> None:
        self.url = url
        self.tmp_path = tmp_path
        self.engine = engine
        self.api: Api = make_api(url, tmp_path, **overrides)
        self.pid = self.api.project()

    def upload(self, files: list[tuple[str, bytes]]) -> list[str]:
        parent = self.api.latest(self.pid)
        r = self.api.upload(self.pid, files, parent=parent)
        assert r.status_code in (200, 201, 202), r.text
        while self.api.worker.run_once():
            pass
        return [str(d) for d in r.json()["created_document_ids"]]

    def drain(self) -> int:
        n = 0
        while self.api.worker.extraction.run_once():
            n += 1
        return n

    def get(self, path: str, **params: Any) -> Any:
        return self.api.client.get(f"/api/v1/projects/{self.pid}/series{path}", params=params)

    def series(self, **params: Any) -> list[dict[str, Any]]:
        r = self.get("", limit=500, **params)
        assert r.status_code == 200, r.text
        return list(r.json()["items"])

    def sql(self, statement: str, **params: Any) -> list[Any]:
        with self.engine.begin() as conn:
            result = conn.execute(text(statement), params)
            return list(result.all()) if result.returns_rows else []
