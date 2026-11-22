import sys
import time
import psycopg2
from config import DB, ROOT

SQL_DIR = ROOT / "sql"
TABLES = ["stg_master_data", "stg_hospital_demand", "stg_pharmacy_sales"]  # order matters

RULES = []


def rule(table, idcol, code, reason, predicate):
    """predicate = SQL condition that is TRUE for a BAD row."""
    RULES.append(dict(table=table, idcol=idcol, code=code, reason=reason, pred=predicate))


def dup(table, partition, idcol):
    cols = [c.strip() for c in partition.split(",")]
    eq = " AND ".join(f"o.{c} = s.{c}" for c in cols)
    return (f"EXISTS (SELECT 1 FROM {table} o WHERE {eq} AND o.row_id < s.row_id "
            f"AND o.validation_status IS DISTINCT FROM 'rejected')")


# ------------------------- MASTER -------------------------
T, ID = "stg_master_data", "medicineid"
rule(T, ID, "M01_medicine_id_blank", "MedicineID is blank", "medicineid IS NULL OR trim(medicineid) = ''")
rule(T, ID, "S15_delivery_date", "PharmacyDeliveryDate invalid or after the sales date",
     "safe_date(pharmacydeliverydate) IS NULL OR (safe_date(salesdate) IS NOT NULL "
     "AND safe_date(pharmacydeliverydate) > safe_date(salesdate))")
rule(T, ID, "M02_duplicate_in_batch", "MedicineID appears more than once in the same batch",
     dup(T, "batch_id, medicineid", "medicineid"))
for c in ["unitmanufacturingcostusd", "wholesalepriceusd", "recommendedretailpriceusd"]:
    rule(T, ID, f"M03_{c}", f"{c} is missing or not > 0", f"safe_num({c}) IS NULL OR safe_num({c}) <= 0")
rule(T, ID, "M04_effective_date", "EffectiveFromDate is not a valid dd-mm-yy date", "safe_date(effectivefromdate) IS NULL")
rule(T, ID, "M05_pack_size", "PackSize missing or not > 0", "safe_int(packsize) IS NULL OR safe_int(packsize) <= 0")
rule(T, ID, "M06_storage_temp", "Storage min temperature is not below max temperature",
     "safe_int(storagemintempc) IS NULL OR safe_int(storagemaxtempc) IS NULL OR "
     "safe_int(storagemintempc) >= safe_int(storagemaxtempc)")

# ------------------------- HOSPITAL DEMAND -------------------------
T, ID = "stg_hospital_demand", "hospitaldemandrecordid"
rule(T, ID, "H01_record_id_blank", "HospitalDemandRecordID is blank",
     "hospitaldemandrecordid IS NULL OR trim(hospitaldemandrecordid) = ''")
rule(T, ID, "H02_duplicate_record_id", "HospitalDemandRecordID already exists",
     dup(T, "hospitaldemandrecordid", "hospitaldemandrecordid"))
rule(T, ID, "H03_duplicate_grain", "Second row for the same hospital + medicine + month",
     dup(T, "hospitalid, medicineid, demandmonth", "hospitaldemandrecordid"))
rule(T, ID, "H04_demand_month", "DemandMonth is not a valid dd-mm-yy date on the 1st of a month",
     "safe_date(demandmonth) IS NULL OR extract(day FROM safe_date(demandmonth)) <> 1")
rule(T, ID, "H05_hospital_blank", "HospitalID is blank", "hospitalid IS NULL OR trim(hospitalid) = ''")
rule(T, ID, "H06_medicine_fk", "MedicineID is blank or not in validated master data",
     "NOT EXISTS (SELECT 1 FROM stg_master_data m WHERE m.medicineid = s.medicineid AND m.validation_status = 'valid')")
for c in ["estimateddiseasecases", "diseaserelatedadmissions", "outpatientencounters", "forecastdemandpacks",
          "requestedquantitypacks", "approvedquantitypacks", "receivedquantitypacks",
          "emergencyrequestquantitypacks", "openingstockpacks", "dispensedquantitypacks",
          "consumedquantitypacks", "wastagequantitypacks", "closingstockpacks",
          "unfulfilleddemandpacks", "stockoutdays", "averageleadtimedays"]:
    rule(T, ID, f"H07_{c}", f"{c} is missing, not a whole number, or negative",
         f"safe_int({c}) IS NULL OR safe_int({c}) < 0")
rule(T, ID, "H08_service_level", "ServiceLevelPct missing or outside 0-100",
     "safe_num(servicelevelpct) IS NULL OR safe_num(servicelevelpct) < 0 OR safe_num(servicelevelpct) > 100")

# ------------------------- SALES -------------------------
T, ID = "stg_pharmacy_sales", "salestransactionid"
rule(T, ID, "S01_transaction_id_blank", "SalesTransactionID is blank",
     "salestransactionid IS NULL OR trim(salestransactionid) = ''")
rule(T, ID, "S02_duplicate_transaction", "SalesTransactionID already exists",
     dup(T, "salestransactionid", "salestransactionid"))
rule(T, ID, "S03_medicine_fk", "MedicineID is blank or not in validated master data",
     "NOT EXISTS (SELECT 1 FROM stg_master_data m WHERE m.medicineid = s.medicineid AND m.validation_status = 'valid')")
rule(T, ID, "S04_pharmacy_blank", "PharmacyID is blank", "pharmacyid IS NULL OR trim(pharmacyid) = ''")
rule(T, ID, "S05_sales_date", "SalesDate is not a valid dd-mm-yy date", "safe_date(salesdate) IS NULL")
rule(T, ID, "S06_date_vs_timestamp", "SalesDate differs from the date in SalesTimestampUTC",
     "safe_date(salesdate) IS NOT NULL AND safe_iso_date(salestimestamputc) IS NOT NULL "
     "AND safe_date(salesdate) <> safe_iso_date(salestimestamputc)")
rule(T, ID, "S07_price", "UnitRetailPriceUSD missing or not > 0",
     "safe_num(unitretailpriceusd) IS NULL OR safe_num(unitretailpriceusd) <= 0")
rule(T, ID, "S08_quantity", "QuantitySoldPacks missing, not a whole number, or negative",
     "safe_int(quantitysoldpacks) IS NULL OR safe_int(quantitysoldpacks) < 0")
for c in ["grosssalesamountusd", "discountamountusd", "netsalesamountusd", "salestaxusd", "costofgoodssoldusd"]:
    rule(T, ID, f"S09_{c}", f"{c} is missing, not numeric, or negative",
         f"safe_num({c}) IS NULL OR safe_num({c}) < 0")
rule(T, ID, "S10_margin_numeric", "GrossMarginUSD missing or not numeric", "safe_num(grossmarginusd) IS NULL")
rule(T, ID, "S11_net_formula", "Net sales does not equal gross minus discount",
     "abs(safe_num(grosssalesamountusd) - safe_num(discountamountusd) - safe_num(netsalesamountusd)) > 0.02")
rule(T, ID, "S12_margin_formula", "Gross margin does not equal net sales minus COGS",
     "abs(safe_num(netsalesamountusd) - safe_num(costofgoodssoldusd) - safe_num(grossmarginusd)) > 0.02")
rule(T, ID, "S13_expiry_date", "BatchExpiryDate invalid or not after the sales date",
     "safe_date(batchexpirydate) IS NULL OR "
     "(safe_date(salesdate) IS NOT NULL AND safe_date(batchexpirydate) <= safe_date(salesdate))")
rule(T, ID, "S14_hospital_fk", "HospitalID not found in validated hospital data",
     "hospitalid IS NOT NULL AND NOT EXISTS (SELECT 1 FROM stg_hospital_demand h "
     "WHERE h.hospitalid = s.hospitalid AND h.validation_status = 'valid')")


# ------------------------- setup + runner -------------------------
def ensure_schema(cur):
    cur.execute((SQL_DIR / "00_validation_functions.sql").read_text(encoding="utf-8"))
    for t in TABLES:
        cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS row_id BIGSERIAL")
        cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS validation_status TEXT")
        cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_status ON {t} (validation_status)")
    cur.execute("ALTER TABLE rejected_records ADD COLUMN IF NOT EXISTS row_id BIGINT")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_rej_lookup ON rejected_records (source_table, row_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sales_txn ON stg_pharmacy_sales (salestransactionid)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_hosp_rec ON stg_hospital_demand (hospitaldemandrecordid)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_hosp_grain ON stg_hospital_demand (hospitalid, medicineid, demandmonth)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_master_batch_med ON stg_master_data (batch_id, medicineid)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_master_med ON stg_master_data (medicineid)")
    parts = [f"""SELECT batch_id, '{t}' AS source_table, count(*) AS rows_staged,
                   count(*) FILTER (WHERE validation_status = 'valid') AS rows_valid,
                   count(*) FILTER (WHERE validation_status = 'rejected') AS rows_rejected,
                   count(*) FILTER (WHERE validation_status IS NULL) AS rows_pending
                 FROM {t} GROUP BY batch_id""" for t in TABLES]
    cur.execute("CREATE OR REPLACE VIEW v_batch_quality AS " + " UNION ALL ".join(parts))
    cur.execute("""CREATE OR REPLACE VIEW v_rejection_summary AS
                   SELECT source_table, rule_name, min(reason) AS reason,
                          count(*) AS violations, count(DISTINCT row_id) AS rows_affected
                   FROM rejected_records GROUP BY source_table, rule_name""")


def run(reset=False):
    conn = psycopg2.connect(**DB, options="-c statement_timeout=900000")  # 15 min safety net
    cur = conn.cursor()
    try:
        ensure_schema(cur)
        if reset:
            cur.execute("DELETE FROM rejected_records")
            for t in TABLES:
                cur.execute(f"UPDATE {t} SET validation_status = NULL")
            print("Reset: all rows set back to pending.")
        conn.commit()
        for t in TABLES:
            cur.execute(f"ANALYZE {t}")      # fresh statistics for the query planner
        conn.commit()

        for table in TABLES:
            cur.execute(f"SELECT count(*) FROM {table} WHERE validation_status IS NULL")
            pending = cur.fetchone()[0]
            print(f"\n=== {table}: {pending:,} pending rows ===")
            if pending == 0:
                continue
            for r in [x for x in RULES if x["table"] == table]:
                t0 = time.time()
                cur.execute(f"""
                    INSERT INTO rejected_records
                      (batch_id, source_table, row_id, record_id, rule_name, reason, raw_row)
                    SELECT s.batch_id, %s, s.row_id, s.{r['idcol']}, %s, %s,
                           to_jsonb(s) - 'validation_status' - 'row_id'
                    FROM {table} s
                    WHERE s.validation_status IS NULL AND ({r['pred']})""",
                    (table, r["code"], r["reason"]))
                print(f"  {r['code']:<42} {cur.rowcount:>8,} violations   ({time.time()-t0:.1f}s)", flush=True)
            cur.execute(f"""
                UPDATE {table} t SET validation_status = CASE WHEN EXISTS (
                    SELECT 1 FROM rejected_records r
                    WHERE r.source_table = %s AND r.row_id = t.row_id)
                  THEN 'rejected' ELSE 'valid' END
                WHERE t.validation_status IS NULL""", (table,))
            conn.commit()
            cur.execute(f"""SELECT count(*) FILTER (WHERE validation_status='valid'),
                                   count(*) FILTER (WHERE validation_status='rejected')
                            FROM {table}""")
            ok, bad = cur.fetchone()
            print(f"  -> total valid: {ok:,}   total rejected: {bad:,}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(reset="--reset" in sys.argv)