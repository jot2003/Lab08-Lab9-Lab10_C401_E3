"""
ETL Pipeline — Day 10 Lab
Trợ lý IT nội bộ CS + IT Helpdesk

Flow: Ingest → Clean → Validate → Embed-ready output
  1. Ingest    : đọc CSV từ data/raw/
  2. Clean     : gọi transform/cleaning_rules.py
  3. Validate  : gọi quality/expectations.py
  4. Monitor   : gọi monitoring/freshness_check.py
  5. Output    : ghi data/cleaned/ và artifacts/before_after_eval.csv

Chạy:
    python etl_pipeline.py
    python etl_pipeline.py --input data/raw/helpdesk_tickets_dirty.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Đảm bảo stdout nhận được tiếng Việt trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import pandas as pd

from transform.cleaning_rules import run_all as clean_all
from quality.expectations import run_suite, PASS_THRESHOLD
from monitoring.freshness_check import run_monitor


def ingest(input_path: str) -> pd.DataFrame:
    """Bước 1 — Ingest: đọc CSV và ghi log số dòng ban đầu."""
    print(f"\n[Ingest] Đọc dữ liệu từ: {input_path}")
    df = pd.read_csv(input_path)
    print(f"         raw_records = {len(df)}")
    return df


def clean(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Bước 2 — Clean: áp dụng cleaning rules, ghi log từng bước."""
    print("\n[Clean] Áp dụng cleaning rules...")
    df_clean, logs = clean_all(df_raw)
    for log in logs:
        step = log.get("step", "?")
        key_metrics = {k: v for k, v in log.items() if k not in ("step", "before", "after")}
        print(f"         {step}: {key_metrics}")
    print(f"         cleaned_records = {len(df_clean)}")
    return df_clean, logs


def validate(df_clean: pd.DataFrame, run_id: str) -> dict:
    """Bước 3 — Validate: chạy expectation suite và trả về report."""
    print("\n[Validate] Chạy expectation suite...")
    report = run_suite(df_clean, run_id=run_id)
    report.print_summary()
    if report.pass_rate < PASS_THRESHOLD:
        print(f"\n[Validate] CẢNH BÁO: pass_rate={report.pass_rate:.1%} thấp hơn ngưỡng {PASS_THRESHOLD:.1%}")
        print("           Pipeline vẫn tiếp tục nhưng cần xem xét dữ liệu.\n")
    return report.to_dict()


def monitor(df_clean: pd.DataFrame, source_file: str, run_id: str) -> dict:
    """Bước 4 — Monitor: chạy freshness & volume checks."""
    print("\n[Monitor] Chạy freshness & volume checks...")
    report = run_monitor(df_clean, source_file=source_file, run_id=run_id)
    report.print_dashboard()
    return report.to_dict()


def build_before_after_eval(df_raw: pd.DataFrame, df_clean: pd.DataFrame, clean_logs: list) -> list:
    """
    Xây dựng bằng chứng trước/sau: so sánh data quality metrics.
    Mỗi dòng là 1 chiều đánh giá (metric).
    """
    rows = []

    rows.append({
        "metric": "total_records",
        "before": len(df_raw),
        "after": len(df_clean),
        "delta": len(df_clean) - len(df_raw),
        "note": "Số dòng sau khi xoá duplicate và dòng thiếu required fields",
    })

    for log in clean_logs:
        step = log.get("step", "")
        if step == "remove_duplicates":
            rows.append({
                "metric": "duplicate_ticket_ids",
                "before": log.get("dropped", 0),
                "after": 0,
                "delta": -log.get("dropped", 0),
                "note": "Số ticket_id bị trùng lặp — xoá hết sau bước dedup",
            })
        if step == "normalize_channel":
            invalid_before = log.get("flagged_invalid", 0)
            invalid_after = 0
            rows.append({
                "metric": "invalid_channel_values",
                "before": invalid_before,
                "after": invalid_after,
                "delta": -(invalid_before - invalid_after),
                "note": "Giá trị channel không hợp lệ (EMAIL, Chat, e-mail…)",
            })
        if step == "normalize_priority":
            remapped = log.get("remapped_values", 0)
            rows.append({
                "metric": "priority_remapped",
                "before": remapped,
                "after": 0,
                "delta": -remapped,
                "note": "urgent/critical → high, sau đó chuẩn hoá lowercase",
            })
        if step == "fix_resolution_time":
            neg = log.get("negative_values_fixed", 0)
            rows.append({
                "metric": "negative_resolution_minutes",
                "before": neg,
                "after": 0,
                "delta": -neg,
                "note": "Số phút xử lý âm — đặt về NaN",
            })
        if step == "drop_missing_required":
            rows.append({
                "metric": "missing_required_field_rows",
                "before": log.get("dropped", 0),
                "after": 0,
                "delta": -log.get("dropped", 0),
                "note": "Dòng thiếu ticket_id hoặc message — xoá",
            })

    # Proxy metrics cho answer quality (dựa trên completeness của dữ liệu vào RAG)
    null_msg_before = int(df_raw["message"].isna().sum())
    null_msg_after = int(df_clean["message"].isna().sum())
    rows.append({
        "metric": "null_message_count",
        "before": null_msg_before,
        "after": null_msg_after,
        "delta": null_msg_after - null_msg_before,
        "note": "Ticket không có nội dung — không thể embed vào vector store",
    })

    channel_null_before = int(df_raw["channel"].isna().sum())
    channel_null_after = int(df_clean["channel"].isna().sum())
    rows.append({
        "metric": "null_channel_count",
        "before": channel_null_before,
        "after": channel_null_after,
        "delta": channel_null_after - channel_null_before,
        "note": "Thiếu channel metadata ảnh hưởng routing và retrieval filter",
    })

    # Estimated answer quality proxy (clean data → better retrieval → better answer)
    completeness_before = round(1.0 - (null_msg_before / max(len(df_raw), 1)), 3)
    completeness_after = round(1.0 - (null_msg_after / max(len(df_clean), 1)), 3)
    rows.append({
        "metric": "estimated_retrieval_completeness",
        "before": completeness_before,
        "after": completeness_after,
        "delta": round(completeness_after - completeness_before, 3),
        "note": "Tỷ lệ ticket có đủ nội dung để embed — proxy cho retrieval quality",
    })

    return rows


def save_outputs(df_clean: pd.DataFrame, eval_rows: list,
                 quality_report: dict, monitor_report: dict,
                 run_id: str, output_dir: str = "data/cleaned") -> None:
    """Ghi tất cả outputs ra file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path("artifacts").mkdir(parents=True, exist_ok=True)

    clean_path = f"{output_dir}/helpdesk_tickets_clean_{run_id}.csv"
    df_clean.to_csv(clean_path, index=False)
    print(f"\n[Output] Cleaned data → {clean_path}")

    eval_path = "artifacts/before_after_eval.csv"
    with open(eval_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "before", "after", "delta", "note"])
        writer.writeheader()
        writer.writerows(eval_rows)
    print(f"[Output] Before/after eval → {eval_path}")

    quality_path = "artifacts/quality_report.json"
    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, ensure_ascii=False, indent=2)
    print(f"[Output] Quality report   → {quality_path}")

    monitor_path = "artifacts/monitor_report.json"
    with open(monitor_path, "w", encoding="utf-8") as f:
        json.dump(monitor_report, f, ensure_ascii=False, indent=2)
    print(f"[Output] Monitor report   → {monitor_path}")


def run_pipeline(input_path: str) -> None:
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    print(f"\n{'='*65}")
    print(f"  ETL Pipeline — Day 10 Lab")
    print(f"  run_id = {run_id}")
    print(f"{'='*65}")

    df_raw = ingest(input_path)

    df_clean, clean_logs = clean(df_raw)

    quality_report = validate(df_clean, run_id)

    monitor_report = monitor(df_clean, source_file=input_path, run_id=run_id)

    eval_rows = build_before_after_eval(df_raw, df_clean, clean_logs)

    save_outputs(df_clean, eval_rows, quality_report, monitor_report, run_id)

    print(f"\n{'='*65}")
    print(f"  Pipeline hoàn thành  |  run_id = {run_id}")
    raw_count = len(df_raw)
    clean_count = len(df_clean)
    dropped = raw_count - clean_count
    print(f"  raw_records    = {raw_count}")
    print(f"  cleaned_records= {clean_count}")
    print(f"  dropped_records= {dropped}")
    print(f"  pass_rate      = {quality_report.get('pass_rate', 'N/A'):.0%}")
    print(f"  monitor_status = {monitor_report.get('overall_status', 'N/A')}")
    print(f"{'='*65}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL Pipeline — Day 10 Lab")
    parser.add_argument(
        "--input",
        default="data/raw/helpdesk_tickets_dirty.csv",
        help="Đường dẫn file CSV đầu vào (mặc định: data/raw/helpdesk_tickets_dirty.csv)",
    )
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"[Error] Không tìm thấy file: {args.input}")
        sys.exit(1)

    run_pipeline(args.input)


if __name__ == "__main__":
    main()
