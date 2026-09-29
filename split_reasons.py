"""
One-time script: split the big `top_reasons` column into one tiny parquet file
per forecast date, so the API never has to scan the 2.1M-row table.

Run from the project root (bust-detect/) on your own computer:

    python split_reasons.py

Then commit the new models/reasons/ folder and push.
"""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

SRC = Path("models/confidence_table.parquet")
OUT = Path("models/reasons")

names = pq.ParquetFile(SRC).schema_arrow.names
if "top_reasons" not in names:
    raise SystemExit("No top_reasons column in confidence_table.parquet - nothing to do.")

OUT.mkdir(parents=True, exist_ok=True)

df = pd.read_parquet(SRC, columns=["init_date", "region_id", "lead_day", "top_reasons"])
df["init_date"] = pd.to_datetime(df["init_date"])
df["region_id"] = df["region_id"].astype(str)
df["lead_day"] = df["lead_day"].astype("int8")

days = df["init_date"].dt.strftime("%Y-%m-%d")
count = 0
for day, g in df.groupby(days):
    g[["region_id", "lead_day", "top_reasons"]].to_parquet(
        OUT / f"{day}.parquet", index=False, compression="zstd"
    )
    count += 1

total = sum(f.stat().st_size for f in OUT.glob("*.parquet")) / 1e6
print(f"Wrote {count} files to {OUT} ({total:.1f} MB total)")