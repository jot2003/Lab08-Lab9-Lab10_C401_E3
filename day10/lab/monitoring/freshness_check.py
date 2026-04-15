"""
Freshness & Volume Monitor — Day 10 Lab
Giám sát 5 trụ cột observability:
  Freshness · Volume · Distribution · Schema · Lineage

Chạy độc lập hoặc gọi từ ETL pipeline.
Output: dict report + in ra console với màu (PASS/WARN/FAIL).
"""

from __future__ import annotations

import io
import json
import os
import sys
from dataclasses import dataclass, field

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd


# Ngưỡng SLA
FRESHNESS_SLA_HOURS = 24
FRESHNESS_WARN_HOURS = 12
VOLUME_MIN_ROWS = 10
VOLUME_MAX_ROWS = 100_000
VOLUME_WARN_DROP_PCT = 20.0   # Cảnh báo nếu volume giảm hơn 20% so với lần trước

ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED = "\033[91m"
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"


@dataclass
class MonitorResult:
    check: str
    status: str        # "PASS" | "WARN" | "FAIL"
    message: str
    value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {"check": self.check, "status": self.status, "message": self.message, "value": self.value}

    def colored_status(self) -> str:
        if self.status == "PASS":
            return f"{ANSI_GREEN}PASS{ANSI_RESET}"
        if self.status == "WARN":
            return f"{ANSI_YELLOW}WARN{ANSI_RESET}"
        return f"{ANSI_RED}FAIL{ANSI_RESET}"


@dataclass
class MonitorReport:
    run_id: str
    checked_at: str
    source_file: str
    results: List[MonitorResult] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        statuses = {r.status for r in self.results}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        return "PASS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "checked_at": self.checked_at,
            "source_file": self.source_file,
            "overall_status": self.overall_status,
            "results": [r.to_dict() for r in self.results],
        }

    def print_dashboard(self) -> None:
        overall_color = {
            "PASS": ANSI_GREEN, "WARN": ANSI_YELLOW, "FAIL": ANSI_RED
        }.get(self.overall_status, "")
        print(f"\n{ANSI_BOLD}{'='*65}{ANSI_RESET}")
        print(f"{ANSI_BOLD}  Data Observability Dashboard{ANSI_RESET}")
        print(f"  run_id     : {self.run_id}")
        print(f"  checked_at : {self.checked_at}")
        print(f"  source     : {self.source_file}")
        print(f"  status     : {overall_color}{ANSI_BOLD}{self.overall_status}{ANSI_RESET}")
        print(f"{ANSI_BOLD}{'-'*65}{ANSI_RESET}")
        for r in self.results:
            line = f"  {r.colored_status()}  {r.check:<40} {r.message}"
            print(line)
        print(f"{ANSI_BOLD}{'='*65}{ANSI_RESET}\n")

    def save_json(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"Monitor report saved → {path}")


def _check_freshness(df: pd.DataFrame, source_file: str) -> MonitorResult:
    """Kiểm tra freshness: dữ liệu có được cập nhật trong SLA không?"""
    if "timestamp" not in df.columns or not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        return MonitorResult(
            "freshness.latest_record_age",
            "WARN",
            "Cột timestamp không phải datetime — không thể đo freshness",
        )

    latest = df["timestamp"].max()
    if pd.isna(latest):
        return MonitorResult("freshness.latest_record_age", "FAIL",
                             "Tất cả timestamp đều null — không có dữ liệu hợp lệ")

    now = pd.Timestamp.now()
    age_hours = (now - latest).total_seconds() / 3600

    if age_hours <= FRESHNESS_WARN_HOURS:
        status, msg = "PASS", f"Dữ liệu mới nhất cách nay {age_hours:.1f}h ✓"
    elif age_hours <= FRESHNESS_SLA_HOURS:
        status, msg = "WARN", f"Dữ liệu cách nay {age_hours:.1f}h — gần ngưỡng SLA {FRESHNESS_SLA_HOURS}h"
    else:
        status, msg = "FAIL", f"Freshness breach: dữ liệu cách nay {age_hours:.1f}h — vượt SLA {FRESHNESS_SLA_HOURS}h"

    return MonitorResult("freshness.latest_record_age", status, msg, value=round(age_hours, 2))


def _check_volume(df: pd.DataFrame) -> List[MonitorResult]:
    """Kiểm tra volume: số dòng có trong ngưỡng bình thường không?"""
    results = []
    n = len(df)

    if n < VOLUME_MIN_ROWS:
        results.append(MonitorResult(
            "volume.row_count_min",
            "FAIL",
            f"Chỉ có {n} dòng — thấp hơn ngưỡng tối thiểu {VOLUME_MIN_ROWS}",
            value=n,
        ))
    elif n > VOLUME_MAX_ROWS:
        results.append(MonitorResult(
            "volume.row_count_max",
            "WARN",
            f"{n} dòng — vượt ngưỡng thông thường {VOLUME_MAX_ROWS}. Kiểm tra lại ingestion.",
            value=n,
        ))
    else:
        results.append(MonitorResult(
            "volume.row_count",
            "PASS",
            f"{n} dòng — nằm trong ngưỡng bình thường [{VOLUME_MIN_ROWS}, {VOLUME_MAX_ROWS}]",
            value=n,
        ))
    return results


def _check_schema(df: pd.DataFrame) -> List[MonitorResult]:
    """Kiểm tra schema: có đủ cột bắt buộc không?"""
    required = ["ticket_id", "message", "timestamp", "channel", "priority", "resolution_minutes"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [MonitorResult(
            "schema.required_columns_present",
            "FAIL",
            f"Thiếu cột: {missing}",
            value=missing,
        )]
    return [MonitorResult(
        "schema.required_columns_present",
        "PASS",
        "Đủ tất cả cột bắt buộc",
        value=required,
    )]


def _check_distribution(df: pd.DataFrame) -> List[MonitorResult]:
    """Kiểm tra phân phối: null rate cho các cột quan trọng."""
    results = []
    for col in ["channel", "priority", "timestamp"]:
        if col not in df.columns:
            continue
        null_rate = df[col].isna().mean()
        if null_rate > 0.3:
            status, msg = "FAIL", f"Null rate={null_rate:.1%} > 30% — vấn đề nghiêm trọng"
        elif null_rate > 0.1:
            status, msg = "WARN", f"Null rate={null_rate:.1%} > 10% — cần xem xét"
        else:
            status, msg = "PASS", f"Null rate={null_rate:.1%} — trong ngưỡng chấp nhận"
        results.append(MonitorResult(
            f"distribution.null_rate.{col}",
            status,
            msg,
            value=round(null_rate, 4),
        ))
    return results


def _check_lineage(source_file: str) -> MonitorResult:
    """Kiểm tra lineage: file source có tồn tại và có thể đọc không?"""
    path = Path(source_file)
    if not path.exists():
        return MonitorResult("lineage.source_file_exists", "FAIL",
                             f"File nguồn không tồn tại: {source_file}")
    size_kb = path.stat().st_size / 1024
    return MonitorResult(
        "lineage.source_file_exists",
        "PASS",
        f"Source file tồn tại ({size_kb:.1f} KB): {source_file}",
        value=round(size_kb, 2),
    )


def run_monitor(df: pd.DataFrame, source_file: str = "unknown", run_id: str | None = None) -> MonitorReport:
    """Chạy toàn bộ 5 trụ cột monitoring và trả về MonitorReport."""
    if run_id is None:
        run_id = datetime.now().strftime("monitor-%Y%m%dT%H%M%S")

    report = MonitorReport(
        run_id=run_id,
        checked_at=datetime.now(timezone.utc).isoformat(),
        source_file=str(source_file),
    )

    report.results.append(_check_lineage(source_file))
    report.results.extend(_check_schema(df))
    report.results.append(_check_freshness(df, source_file))
    report.results.extend(_check_volume(df))
    report.results.extend(_check_distribution(df))

    return report


if __name__ == "__main__":
    import sys
    source = sys.argv[1] if len(sys.argv) > 1 else "data/raw/helpdesk_tickets_dirty.csv"
    try:
        df = pd.read_csv(source, parse_dates=["timestamp"])
    except Exception as e:
        print(f"Không thể đọc file: {e}")
        sys.exit(1)

    report = run_monitor(df, source_file=source)
    report.print_dashboard()
    report.save_json("artifacts/monitor_report.json")
    sys.exit(0 if report.overall_status != "FAIL" else 1)
