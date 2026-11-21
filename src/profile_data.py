from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "profile_report.txt"

lines = []

def log(text=""):
    print(text)
    lines.append(str(text))

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)

csv_files = sorted(RAW.glob("*.csv"))
if not csv_files:
    log(f"No CSV files found in {RAW}")

for f in csv_files:
    log("=" * 80)
    log(f"FILE: {f.name}")
    log("=" * 80)

    df = pd.read_csv(f, low_memory=False)
    log(f"Rows: {len(df):,}   Columns: {df.shape[1]}")
    log("")

    # Column summary
    summary = pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "nulls": df.isna().sum(),
        "null_%": (df.isna().mean() * 100).round(2),
        "unique": df.nunique(),
    })
    log("COLUMN SUMMARY")
    log(summary.to_string())
    log("")

    # Duplicate rows
    log(f"Fully duplicated rows: {df.duplicated().sum():,}")
    log("")

    # Date columns (guess by column name)
    for col in df.columns:
        if "date" in col.lower() or "time" in col.lower() or "month" in col.lower():
            parsed = pd.to_datetime(df[col], errors="coerce")
            bad = parsed.isna().sum() - df[col].isna().sum()
            log(f"DATE RANGE [{col}]: {parsed.min()}  ->  {parsed.max()}   (unparseable values: {bad})")
    log("")

    # Low-cardinality columns: show the values
    for col in df.columns:
        n = df[col].nunique()
        if 1 < n <= 25:
            log(f"VALUES [{col}] ({n} distinct):")
            log(df[col].value_counts(dropna=False).to_string())
            log("")

    # Numeric stats
    num = df.select_dtypes("number")
    if not num.empty:
        log("NUMERIC STATS")
        log(num.describe().T.round(2).to_string())
        log("")

    # Sample rows
    log("FIRST 5 ROWS")
    log(df.head(5).to_string())
    log("")

OUT.parent.mkdir(exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"\nReport saved to {OUT}")