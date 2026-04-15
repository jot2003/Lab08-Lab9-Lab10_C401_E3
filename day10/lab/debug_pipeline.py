#!/usr/bin/env python3
"""
Debug script — phân tích từng stage của ETL pipeline.
Chạy: python debug_pipeline.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw" / "policy_export_dirty.csv"
DOCS_DIR = ROOT / "data" / "docs"

SEP = "=" * 60


def section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  STAGE: {title}")
    print(SEP)


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


# ─────────────────────────────────────────────
# STAGE 0: Kiểm tra file đầu vào
# ─────────────────────────────────────────────
section("STAGE 0 — Input files")

if RAW.is_file():
    ok(f"Raw CSV: {RAW.name}")
else:
    fail(f"Raw CSV MISSING: {RAW}")
    sys.exit(1)

txt_files = list(DOCS_DIR.glob("*.txt"))
if txt_files:
    ok(f"Docs TXT files ({len(txt_files)}): {[f.name for f in txt_files]}")
else:
    warn("Không tìm thấy .txt docs — corpus sẽ rất nghèo nàn")

# ─────────────────────────────────────────────
# STAGE 1: Ingest — đọc raw CSV
# ─────────────────────────────────────────────
section("STAGE 1 — Ingest (load_raw_csv)")

sys.path.insert(0, str(ROOT))
from transform.cleaning_rules import load_raw_csv

raw_rows = load_raw_csv(RAW)
print(f"  Raw rows loaded: {len(raw_rows)}")

doc_id_counts: dict[str, int] = {}
for r in raw_rows:
    d = r.get("doc_id", "(empty)")
    doc_id_counts[d] = doc_id_counts.get(d, 0) + 1

print("  Doc ID distribution:")
for d, c in sorted(doc_id_counts.items()):
    print(f"    {d}: {c} chunk(s)")

empty_text = [r for r in raw_rows if not (r.get("chunk_text") or "").strip()]
if empty_text:
    warn(f"Rows với chunk_text rỗng: {len(empty_text)}")
else:
    ok("Không có chunk_text rỗng trong raw")

missing_exported_at = [r for r in raw_rows if not (r.get("exported_at") or "").strip()]
if missing_exported_at:
    warn(f"Rows thiếu exported_at: {len(missing_exported_at)}")
else:
    ok("Tất cả rows có exported_at")

# ─────────────────────────────────────────────
# STAGE 2: Cleaning
# ─────────────────────────────────────────────
section("STAGE 2 — Cleaning (clean_rows)")

from transform.cleaning_rules import clean_rows, ALLOWED_DOC_IDS

cleaned, quarantine = clean_rows(raw_rows, apply_refund_window_fix=True)

print(f"  Input rows:      {len(raw_rows)}")
print(f"  Cleaned rows:    {len(cleaned)}")
print(f"  Quarantine rows: {len(quarantine)}")
print(f"  Drop rate:       {len(quarantine)/len(raw_rows)*100:.1f}%")

if not cleaned:
    fail("CRITICAL: cleaned rỗng — pipeline sẽ halt ở expectations!")
elif len(cleaned) < 3:
    warn(f"Rất ít cleaned rows ({len(cleaned)}) — corpus retrieval sẽ rất hạn chế")
else:
    ok(f"Cleaned OK — {len(cleaned)} rows")

# Phân tích lý do quarantine
print("\n  Quarantine reasons:")
reasons: dict[str, int] = {}
for q in quarantine:
    r = q.get("reason", "unknown")
    reasons[r] = reasons.get(r, 0) + 1
for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
    print(f"    {r}: {c}")

# Kiểm tra cleaned doc coverage
cleaned_docs = set(r.get("doc_id") for r in cleaned)
missing_docs = ALLOWED_DOC_IDS - cleaned_docs
if missing_docs:
    warn(f"Docs hoàn toàn không có chunk sau clean: {missing_docs}")
else:
    ok(f"Tất cả allowed docs có ít nhất 1 chunk: {cleaned_docs}")

# Kiểm tra refund fix
refund_fixed = [r for r in cleaned if "[cleaned: stale_refund_window]" in (r.get("chunk_text") or "")]
if refund_fixed:
    ok(f"Refund window fix applied: {len(refund_fixed)} chunk(s)")
else:
    ok("Không có chunk nào cần refund fix (đã clean hoặc không tồn tại)")

# ─────────────────────────────────────────────
# STAGE 3: Validation / Expectations
# ─────────────────────────────────────────────
section("STAGE 3 — Expectations (run_expectations)")

from quality.expectations import run_expectations

results, should_halt = run_expectations(cleaned)

for r in results:
    sym = ok if r.passed else (fail if r.severity == "halt" else warn)
    sym(f"[{r.severity.upper()}] {r.name}: {'PASS' if r.passed else 'FAIL'} — {r.detail}")

if should_halt:
    fail("should_halt=True → pipeline sẽ dừng nếu không có --skip-validate")
else:
    ok("All halt-severity expectations passed — pipeline tiếp tục embed")

# ─────────────────────────────────────────────
# STAGE 4: Embed (ChromaDB)
# ─────────────────────────────────────────────
section("STAGE 4 — Embed (ChromaDB inspection)")

try:
    import chromadb
    from chromadb.utils import embedding_functions
    db_path = os.environ.get("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
    collection_name = os.environ.get("CHROMA_COLLECTION", "day10_kb")
    model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    client = chromadb.PersistentClient(path=db_path)
    emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)

    try:
        col = client.get_collection(name=collection_name, embedding_function=emb)
        all_items = col.get(include=["metadatas", "documents"])
        total_in_db = len(all_items.get("ids") or [])
        print(f"  Collection '{collection_name}': {total_in_db} chunks hiện có")

        # Breakdown by doc_id
        meta_list = all_items.get("metadatas") or []
        docs_in_db: dict[str, int] = {}
        for m in meta_list:
            d = (m or {}).get("doc_id", "(no meta)")
            docs_in_db[d] = docs_in_db.get(d, 0) + 1

        print("  Chunks per doc_id in ChromaDB:")
        for d, c in sorted(docs_in_db.items()):
            status = ok if c >= 1 else warn
            print(f"    {d}: {c} chunk(s)")

        # Check docs missing from DB
        docs_in_db_set = set(docs_in_db.keys())
        allowed_missing = ALLOWED_DOC_IDS - docs_in_db_set
        if allowed_missing:
            warn(f"Allowed docs KHÔNG có trong ChromaDB: {allowed_missing}")

        # Check TXT docs coverage
        txt_doc_ids = {f.stem for f in txt_files}
        txt_missing = txt_doc_ids - docs_in_db_set
        if txt_missing:
            fail(f"TXT docs chưa được embed: {txt_missing}")
            fail("→ Đây là ROOT CAUSE #1: retrieval thiếu corpus")
        else:
            ok("Tất cả TXT docs đã được embed")

        # Sample preview
        print("\n  Sample chunks (first 3):")
        ids = all_items.get("ids") or []
        docs = all_items.get("documents") or []
        metas = all_items.get("metadatas") or []
        for i in range(min(3, len(ids))):
            print(f"    [{ids[i]}]")
            print(f"      doc_id: {(metas[i] or {}).get('doc_id', '?')}")
            preview = (docs[i] or "")[:100].replace("\n", " ")
            print(f"      text:   {preview}...")

        # Chunk length analysis
        chunk_lens = [len(d or "") for d in docs]
        if chunk_lens:
            avg_len = sum(chunk_lens) / len(chunk_lens)
            min_len = min(chunk_lens)
            max_len = max(chunk_lens)
            print(f"\n  Chunk length stats: min={min_len}, avg={avg_len:.0f}, max={max_len}")
            short_chunks = [(ids[i], chunk_lens[i]) for i in range(len(ids)) if chunk_lens[i] < 50]
            if short_chunks:
                warn(f"Chunks qua ngan (<50 chars): {len(short_chunks)}")
                for cid, clen in short_chunks:
                    print(f"    {cid}: {clen} chars")
            else:
                ok("Tat ca chunks co do dai hop ly (>=50 chars)")

    except Exception as e:
        fail(f"Collection '{collection_name}' không tồn tại hoặc lỗi: {e}")
        fail("→ Chạy: python etl_pipeline.py run  để tạo collection")

except ImportError:
    fail("chromadb chưa cài — pip install -r requirements.txt")

# ─────────────────────────────────────────────
# STAGE 5: Retrieval quality — spot check
# ─────────────────────────────────────────────
section("STAGE 5 — Retrieval spot-check (5 probe queries)")

PROBES = [
    {
        "label": "refund_7d [easy]",
        "query": "hoàn tiền bao nhiêu ngày",
        "want_any": ["7 ngày", "7 ngay"],
        "want_not": ["14 ngày", "14 ngay"],
        "want_doc": "policy_refund_v4",
    },
    {
        "label": "p1_resolution [hard: same chunk]",
        "query": "SLA xử lý ticket P1 bao lâu",
        "want_any": ["4 giờ"],
        "want_not": ["15 phút"],  # hard: same chunk có cả 2
        "want_doc": "sla_p1_2026",
    },
    {
        "label": "hr_12d [medium: version]",
        "query": "nhân viên dưới 3 năm được bao nhiêu ngày phép",
        "want_any": ["12 ngày"],
        "want_not": ["10 ngày phép năm"],
        "want_doc": "hr_leave_policy",
    },
    {
        "label": "access_control [missing corpus]",
        "query": "ai phê duyệt elevated access level 3",
        "want_any": ["it admin", "it security", "line manager"],
        "want_not": [],
        "want_doc": "access_control_sop",
    },
    {
        "label": "password_expiry [missing detail]",
        "query": "mật khẩu hết hạn sau bao lâu",
        "want_any": ["90 ngày"],
        "want_not": [],
        "want_doc": "it_helpdesk_faq",
    },
]

try:
    col  # reuse from stage 4
    probe_pass = 0
    probe_fail = 0
    for p in PROBES:
        res = col.query(query_texts=[p["query"]], n_results=5)
        docs_returned = (res.get("documents") or [[]])[0]
        metas_returned = (res.get("metadatas") or [[]])[0]
        top1_doc = (metas_returned[0] or {}).get("doc_id", "") if metas_returned else ""
        blob = " ".join(docs_returned).lower()

        got_any = any(w.lower() in blob for w in p["want_any"]) if p["want_any"] else True
        got_bad = any(w.lower() in blob for w in p["want_not"]) if p["want_not"] else False
        top1_ok = top1_doc == p["want_doc"]

        passed = got_any and not got_bad and top1_ok
        status = "✓ PASS" if passed else "✗ FAIL"
        if passed:
            probe_pass += 1
        else:
            probe_fail += 1

        print(f"\n  [{status}] {p['label']}")
        print(f"    query: {p['query']}")
        print(f"    top1_doc: {top1_doc} (want: {p['want_doc']}) → {'✓' if top1_ok else '✗'}")
        print(f"    contains_expected: {'yes' if got_any else 'no'} → {'✓' if got_any else '✗'}")
        print(f"    hits_forbidden: {'yes' if got_bad else 'no'} → {'✓' if not got_bad else '✗ PROBLEM'}")
        top1_preview = (docs_returned[0] or "")[:120].replace("\n", " ") if docs_returned else ""
        print(f"    top1_preview: {top1_preview}")

    print(f"\n  Retrieval probe results: {probe_pass}/5 PASS, {probe_fail}/5 FAIL")

except NameError:
    warn("Bỏ qua stage 5 (ChromaDB chưa init từ stage 4)")
except Exception as e:
    fail(f"Lỗi trong retrieval probe: {e}")

# ─────────────────────────────────────────────
# STAGE 6: Freshness check
# ─────────────────────────────────────────────
section("STAGE 6 — Freshness check")

from monitoring.freshness_check import check_manifest_freshness

man_dir = ROOT / "artifacts" / "manifests"
manifests = sorted(man_dir.glob("manifest_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
if not manifests:
    warn("Không tìm thấy manifest — chạy pipeline trước")
else:
    latest = manifests[0]
    print(f"  Latest manifest: {latest.name}")
    status, detail = check_manifest_freshness(latest, sla_hours=24.0)
    age = detail.get("age_hours", "?")
    if status == "PASS":
        ok(f"freshness={status}, age={age}h")
    elif status == "WARN":
        warn(f"freshness={status}, age={age}h")
    else:
        fail(f"freshness={status}, age={age}h — data stale! reason={detail.get('reason','')}")

    # Parse manifest content
    data = json.loads(latest.read_text(encoding="utf-8"))
    print(f"  run_id:           {data.get('run_id')}")
    print(f"  raw_records:      {data.get('raw_records')}")
    print(f"  cleaned_records:  {data.get('cleaned_records')}")
    print(f"  quarantine_records: {data.get('quarantine_records')}")
    print(f"  latest_exported_at: {data.get('latest_exported_at')}")

# ─────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────
section("FINAL SUMMARY — Điểm yếu phát hiện")

print("""
  ┌─────────────────────────────────────────────────────┐
  │  Stage             │ Tình trạng  │ Vấn đề chính     │
  ├─────────────────────────────────────────────────────┤
  │  Stage 1 Ingest    │ OK          │ CSV chỉ 10 dòng  │
  │  Stage 2 Cleaning  │ OK          │ Quarantine đúng  │
  │  Stage 3 Validate  │ OK          │ 6 expectations   │
  │  Stage 4 Embed     │ ⚠ PARTIAL   │ Chỉ embed CSV    │
  │  Stage 5 Retrieval │ ⚠ POOR      │ Corpus thiếu     │
  │  Stage 6 Freshness │ ⚠ FAIL      │ Data > 24h cũ    │
  └─────────────────────────────────────────────────────┘

  Top 3 vấn đề cần fix:
  1. [CRITICAL] Stage 4: pipeline không embed .txt docs → 5 docs thiếu corpus
  2. [HIGH]     Stage 5: Chunk P1 SLA chứa 2 fact (15ph + 4h) → contamination
  3. [MEDIUM]   Stage 6: Freshness FAIL vì data/exported_at là 2026-04-10 (cũ)
""")
