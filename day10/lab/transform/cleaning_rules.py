"""
Quy tắc làm sạch dữ liệu — Day 10 Lab
Áp dụng cho dataset helpdesk_tickets của trợ lý IT nội bộ.

Mỗi hàm trả về (df_mới, log_dict) để ETL pipeline ghi lại bằng chứng trước/sau.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple, Dict, Any

import pandas as pd


VALID_CHANNELS = {"email", "chat", "phone"}
VALID_PRIORITIES = {"low", "medium", "high"}
MAX_RESOLUTION_MINUTES = 10_080   # 7 ngày
MIN_RESOLUTION_MINUTES = 0


def normalize_channel(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Chuẩn hoá channel về lowercase và chỉ giữ email/chat/phone."""
    df = df.copy()
    before = df["channel"].value_counts(dropna=False).to_dict()
    df["channel"] = df["channel"].str.strip().str.lower()
    channel_map = {
        "e-mail": "email",
        "email": "email",
        "chat": "chat",
        "phone": "phone",
    }
    df["channel"] = df["channel"].map(lambda x: channel_map.get(x, x) if pd.notna(x) else x)
    invalid_mask = ~df["channel"].isin(VALID_CHANNELS)
    flagged = int(invalid_mask.sum())
    df.loc[invalid_mask, "channel"] = None
    after = df["channel"].value_counts(dropna=False).to_dict()
    return df, {"step": "normalize_channel", "flagged_invalid": flagged, "before": before, "after": after}


def normalize_priority(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Chuẩn hoá priority về lowercase; urgent/critical → high; giữ low/medium/high."""
    df = df.copy()
    before_counts = df["priority"].value_counts(dropna=False).to_dict()
    df["priority"] = df["priority"].str.strip().str.lower()
    priority_map = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "urgent": "high",
        "critical": "high",
    }
    original = df["priority"].copy()
    df["priority"] = df["priority"].map(lambda x: priority_map.get(x, x) if pd.notna(x) else x)
    remapped = int((original != df["priority"]).sum())
    invalid_mask = ~df["priority"].isin(VALID_PRIORITIES)
    flagged = int(invalid_mask.sum())
    df.loc[invalid_mask, "priority"] = None
    after_counts = df["priority"].value_counts(dropna=False).to_dict()
    return df, {
        "step": "normalize_priority",
        "remapped_values": remapped,
        "flagged_invalid": flagged,
        "before": before_counts,
        "after": after_counts,
    }


def fix_resolution_time(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Đặt resolution_minutes âm hoặc quá lớn về NaN để tránh số liệu sai."""
    df = df.copy()
    df["resolution_minutes"] = pd.to_numeric(df["resolution_minutes"], errors="coerce")
    too_low = (df["resolution_minutes"] < MIN_RESOLUTION_MINUTES).sum()
    too_high = (df["resolution_minutes"] > MAX_RESOLUTION_MINUTES).sum()
    df.loc[df["resolution_minutes"] < MIN_RESOLUTION_MINUTES, "resolution_minutes"] = None
    df.loc[df["resolution_minutes"] > MAX_RESOLUTION_MINUTES, "resolution_minutes"] = None
    return df, {
        "step": "fix_resolution_time",
        "negative_values_fixed": int(too_low),
        "oversized_values_fixed": int(too_high),
    }


def parse_timestamps(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Chuyển cột timestamp sang datetime; ghi lại số dòng không parse được."""
    df = df.copy()
    before_null = int(df["timestamp"].isna().sum())
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    after_null = int(df["timestamp"].isna().sum())
    new_nulls = after_null - before_null
    return df, {
        "step": "parse_timestamps",
        "already_null": before_null,
        "unparseable_rows": new_nulls,
        "total_null_after": after_null,
    }


def remove_duplicates(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Xoá dòng trùng ticket_id (giữ lần xuất hiện đầu tiên)."""
    df = df.copy()
    before = len(df)
    df = df.drop_duplicates(subset=["ticket_id"], keep="first")
    dropped = before - len(df)
    return df, {"step": "remove_duplicates", "rows_before": before, "rows_after": len(df), "dropped": dropped}


def drop_missing_required(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Xoá dòng thiếu ticket_id hoặc message (không thể xử lý downstream)."""
    df = df.copy()
    before = len(df)
    df = df.dropna(subset=["ticket_id", "message"])
    dropped = before - len(df)
    return df, {
        "step": "drop_missing_required",
        "rows_before": before,
        "rows_after": len(df),
        "dropped": dropped,
    }


def run_all(df: pd.DataFrame) -> Tuple[pd.DataFrame, list]:
    """Áp dụng toàn bộ cleaning steps theo thứ tự chuẩn. Trả về (df_clean, [logs])."""
    steps = [
        parse_timestamps,
        normalize_channel,
        normalize_priority,
        fix_resolution_time,
        remove_duplicates,
        drop_missing_required,
    ]
    logs = []
    for step_fn in steps:
        df, log = step_fn(df)
        logs.append(log)
    return df, logs
