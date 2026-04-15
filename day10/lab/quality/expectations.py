"""
Expectation suite — Day 10 Lab
Kiểm tra chất lượng dữ liệu helpdesk_tickets theo 6 chiều:
  Completeness · Accuracy · Consistency · Validity · Uniqueness · Timeliness

Chạy như unit test trong CI/CD: nếu pass_rate < PASS_THRESHOLD thì raise RuntimeError.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from datetime import datetime, timezone
from typing import Dict, List, Any

import pandas as pd


PASS_THRESHOLD = 0.85        # Ngưỡng tối thiểu để pipeline tiếp tục
MAX_FRESHNESS_HOURS = 48     # Dữ liệu không được cũ hơn 48 giờ
VALID_CHANNELS = {"email", "chat", "phone"}
VALID_PRIORITIES = {"low", "medium", "high"}


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    detail: str
    severity: str = "error"   # "error" | "warning"
    value: Any = None


@dataclass
class SuiteReport:
    run_id: str
    checked_at: str
    rows_total: int
    results: List[ExpectationResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return len(self.results) - self.passed_count

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return self.passed_count / len(self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "checked_at": self.checked_at,
            "rows_total": self.rows_total,
            "total_checks": len(self.results),
            "passed": self.passed_count,
            "failed": self.failed_count,
            "pass_rate": round(self.pass_rate, 4),
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "detail": r.detail,
                    "severity": r.severity,
                    "value": r.value,
                }
                for r in self.results
            ],
        }

    def print_summary(self) -> None:
        status = "PASS" if self.pass_rate >= PASS_THRESHOLD else "FAIL"
        print(f"\n{'='*60}")
        print(f"Quality Suite Report  [{status}]  run_id={self.run_id}")
        print(f"Checked at: {self.checked_at}")
        print(f"Rows: {self.rows_total}  |  Checks: {len(self.results)}  "
              f"|  Passed: {self.passed_count}  |  Failed: {self.failed_count}  "
              f"|  Pass rate: {self.pass_rate:.1%}")
        print("-"*60)
        for r in self.results:
            icon = "✓" if r.passed else "✗"
            print(f"  {icon}  [{r.severity.upper():7s}]  {r.name}")
            if not r.passed:
                print(f"           → {r.detail}")
        print("="*60)


def _expect(name: str, condition: bool, detail_pass: str, detail_fail: str,
            severity: str = "error", value: Any = None) -> ExpectationResult:
    return ExpectationResult(
        name=name,
        passed=condition,
        detail=detail_pass if condition else detail_fail,
        severity=severity,
        value=value,
    )


def run_suite(df: pd.DataFrame, run_id: str | None = None) -> SuiteReport:
    """Chạy toàn bộ expectation suite và trả về SuiteReport."""
    if run_id is None:
        run_id = datetime.now().strftime("suite-%Y%m%dT%H%M%S")
    checked_at = datetime.now(timezone.utc).isoformat()
    report = SuiteReport(run_id=run_id, checked_at=checked_at, rows_total=len(df))

    required_cols = ["ticket_id", "message", "timestamp", "channel", "priority", "resolution_minutes"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"DataFrame thiếu cột bắt buộc: {missing_cols}")

    # --- Completeness ---
    null_ticket = int(df["ticket_id"].isna().sum())
    report.results.append(_expect(
        "completeness.ticket_id_not_null",
        null_ticket == 0,
        "Tất cả ticket_id không null",
        f"{null_ticket} dòng thiếu ticket_id",
        value=null_ticket,
    ))

    null_msg = int(df["message"].isna().sum())
    report.results.append(_expect(
        "completeness.message_not_null",
        null_msg == 0,
        "Tất cả message không null",
        f"{null_msg} dòng thiếu message",
        value=null_msg,
    ))

    null_ts = int(df["timestamp"].isna().sum())
    report.results.append(_expect(
        "completeness.timestamp_not_null",
        null_ts == 0,
        "Tất cả timestamp không null",
        f"{null_ts} dòng thiếu timestamp",
        severity="warning",
        value=null_ts,
    ))

    # --- Validity ---
    invalid_channel = int((~df["channel"].isin(VALID_CHANNELS) & df["channel"].notna()).sum())
    report.results.append(_expect(
        "validity.channel_in_allowed_set",
        invalid_channel == 0,
        f"Tất cả channel nằm trong {VALID_CHANNELS}",
        f"{invalid_channel} dòng có channel không hợp lệ",
        value=invalid_channel,
    ))

    invalid_priority = int((~df["priority"].isin(VALID_PRIORITIES) & df["priority"].notna()).sum())
    report.results.append(_expect(
        "validity.priority_in_allowed_set",
        invalid_priority == 0,
        f"Tất cả priority nằm trong {VALID_PRIORITIES}",
        f"{invalid_priority} dòng có priority không hợp lệ",
        value=invalid_priority,
    ))

    neg_res = int((df["resolution_minutes"] < 0).sum()) if "resolution_minutes" in df else 0
    report.results.append(_expect(
        "validity.resolution_minutes_non_negative",
        neg_res == 0,
        "Tất cả resolution_minutes >= 0",
        f"{neg_res} dòng có resolution_minutes âm",
        value=neg_res,
    ))

    # --- Uniqueness ---
    dup_ids = int(df["ticket_id"].duplicated().sum())
    report.results.append(_expect(
        "uniqueness.ticket_id_unique",
        dup_ids == 0,
        "Tất cả ticket_id là duy nhất",
        f"{dup_ids} ticket_id bị trùng lặp",
        value=dup_ids,
    ))

    # --- Timeliness (freshness) ---
    if df["timestamp"].dtype == "datetime64[ns]" or pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        now = pd.Timestamp.now()
        oldest = df["timestamp"].min()
        hours_old = (now - oldest).total_seconds() / 3600 if pd.notna(oldest) else float("inf")
        report.results.append(_expect(
            "timeliness.data_freshness_within_sla",
            hours_old <= MAX_FRESHNESS_HOURS,
            f"Dữ liệu mới nhất trong {MAX_FRESHNESS_HOURS}h (oldest={hours_old:.1f}h ago)",
            f"Dữ liệu cũ nhất cách nay {hours_old:.1f}h — vượt SLA {MAX_FRESHNESS_HOURS}h",
            severity="warning",
            value=round(hours_old, 1),
        ))

    # --- Volume ---
    min_rows = 5
    report.results.append(_expect(
        "volume.minimum_row_count",
        len(df) >= min_rows,
        f"Đủ số dòng tối thiểu (>= {min_rows}): {len(df)} dòng",
        f"Chỉ có {len(df)} dòng — thấp hơn ngưỡng tối thiểu {min_rows}",
        severity="error",
        value=len(df),
    ))

    return report


def assert_suite_passes(df: pd.DataFrame, run_id: str | None = None) -> SuiteReport:
    """Chạy suite và raise RuntimeError nếu pass_rate < PASS_THRESHOLD."""
    report = run_suite(df, run_id)
    report.print_summary()
    if report.pass_rate < PASS_THRESHOLD:
        raise RuntimeError(
            f"Quality suite FAILED: pass_rate={report.pass_rate:.1%} < threshold={PASS_THRESHOLD:.1%}. "
            f"Pipeline bị dừng. Kiểm tra failed checks ở trên."
        )
    return report
