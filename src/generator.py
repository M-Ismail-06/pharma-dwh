"""Synthetic data generator for Phase 1. One refresh = the next calendar month."""
import argparse
import json
import re

import numpy as np
import pandas as pd

from config import RAW, DROPZONE, ROOT

STATE_FILE = ROOT / "data" / "generator_state.json"
SALES_PCT = 0.05         # new sales rows per refresh, as a share of rows loaded so far
N_PRICE_CHANGES = 5      # medicines whose prices are revised per refresh
RETAIL_MARKUP = 1.32     # retail = wholesale x 1.32 (inferred from the first rows)
TAX_RATE = 0.06          # sales tax = 6% of net sales (inferred from the first rows)
DATE_FMT = "%d-%m-%y"
BATCH_RE = re.compile(r"^B(\d{2})-PLT(\d{2})-(\d{6})$")

H_NUMS = ["ConsumedQuantityPacks", "ClosingStockPacks", "DemandTrendIndex", "AverageLeadTimeDays",
          "EstimatedDiseaseCases", "DiseaseRelatedAdmissions", "OutpatientEncounters"]
H_STATIC = ["HospitalGLN", "HospitalName", "HospitalType", "HospitalPharmacyID", "City", "State",
            "CountryCode", "LicensedBeds", "ICUBeds", "AverageOccupancyRatePct", "TraumaLevel",
            "CatchmentPopulation"]
M_STATIC = ["GTIN14", "GenericName", "DiseaseCategory", "ICD10Category"]


def _read(prefix):
    return pd.read_csv(next(RAW.glob(prefix + "*.csv")), dtype=str)


# ----------------------------------------------------------------- state
def init_state(master, sales, hosp):
    sd = pd.to_datetime(sales["SalesDate"], format=DATE_FMT)
    hd = pd.to_datetime(hosp["DemandMonth"], format=DATE_FMT)
    batch_serial = {}
    for b in sales["ProductionBatchID"].unique():
        m = BATCH_RE.match(b)
        if m:
            batch_serial[m.group(2)] = max(batch_serial.get(m.group(2), 0), int(m.group(3)))
    return {
        "refresh_no": 0,
        "last_month": max(sd.max(), hd.max()).strftime("%Y-%m"),
        "total_sales_rows": int(len(sales)),
        "sales_serial": int(sales["SalesTransactionID"].str[5:].astype(int).max()),
        "hosp_serial": int(hosp["HospitalDemandRecordID"].str[5:].astype(int).max()),
        "lot_serial": int(sales["WarehouseLotID"].str[6:].astype(int).max()),
        "delivery_serial": int(sales["PharmacyDeliveryID"].str[4:].astype(int).max()),        
        "batch_serial": batch_serial,
        "master": {r["MedicineID"]: r for r in master.to_dict("records")},
        "closing": {},
    }


# ----------------------------------------------------------------- master
def revise_master(state, master_cols, month_start, rng):
    meds = [str(m) for m in rng.choice(sorted(state["master"]), size=N_PRICE_CHANGES, replace=False)]
    rows, changes = [], []
    for med in meds:
        r = dict(state["master"][med])
        old_w = float(r["WholesalePriceUSD"])
        f = rng.uniform(1.03, 1.08) if rng.random() < 0.7 else rng.uniform(0.95, 0.98)
        new_w = round(old_w * f, 2)
        if new_w == old_w:
            new_w = round(old_w + 0.01, 2)
        r["WholesalePriceUSD"] = f"{new_w:.2f}"
        r["RecommendedRetailPriceUSD"] = f"{round(new_w * RETAIL_MARKUP, 2):.2f}"
        r["UnitManufacturingCostUSD"] = f"{round(float(r['UnitManufacturingCostUSD']) * rng.uniform(1.0, 1.05), 2):.2f}"
        r["EffectiveFromDate"] = month_start.strftime(DATE_FMT)
        state["master"][med] = r
        rows.append(r)
        changes.append(f"{med}: wholesale {old_w:.2f} -> {new_w:.2f}")
    return pd.DataFrame(rows)[master_cols], changes


# ----------------------------------------------------------------- hospital demand
def gen_hospital(h, state, month_start, rng):
    cols = list(h.columns)
    med_col = "MED003" if "MED003" in cols else "MedicineID"   # keep the source system's header quirk
    h = h.copy()
    for c in H_NUMS:
        h[c] = pd.to_numeric(h[c])
    h["_m"] = pd.to_datetime(h["DemandMonth"], format=DATE_FMT)
    h = h.sort_values("_m")
    hs = h.drop_duplicates("HospitalID").set_index("HospitalID")[H_STATIC].to_dict("index")
    ms = h.drop_duplicates(med_col).set_index(med_col)[M_STATIC].to_dict("index")
    source_system = h["SourceSystem"].iloc[0]

    rows, serial = [], state["hosp_serial"]
    for (hid, med), g in h.groupby(["HospitalID", med_col]):
        key = f"{hid}|{med}"
        serial += 1
        mean_idx = g["DemandTrendIndex"].mean()
        idx = float(rng.choice(g["DemandTrendIndex"].values))
        ratio = idx / mean_idx
        level = g["ConsumedQuantityPacks"].mean() * ratio * rng.normal(1, 0.04)
        target_stock = g["ClosingStockPacks"].mean()
        opening = int(state["closing"].get(key, g["ClosingStockPacks"].iloc[-1]))

        forecast = max(1, int(round(level * rng.normal(1, 0.08))))
        emergency = int(round(forecast * rng.uniform(0.1, 0.5))) if rng.random() < 0.03 else 0
        wanted = max(forecast + 0.25 * (target_stock - opening), 0.5 * forecast)   # stock mean-reverts
        requested = max(1, int(round(wanted * rng.uniform(1.0, 1.1)))) + emergency
        approved = max(1, int(round(requested * rng.uniform(0.95, 1.0))))
        received = max(1, int(round(approved * rng.uniform(0.96, 1.0))))
        wastage = 0 if rng.random() < 0.92 else int(rng.integers(1, 5))
        dispense_want = max(1, int(round(level * rng.uniform(0.98, 1.04))))
        available = opening + received - wastage
        if dispense_want > available:
            dispensed, unfulfilled = max(available, 0), dispense_want - max(available, 0)
        else:
            dispensed, unfulfilled = dispense_want, 0
        closing = opening + received - dispensed - wastage
        consumed = max(0, int(round(dispensed * rng.uniform(0.96, 1.0))))
        stockout_days = 0 if unfulfilled == 0 else int(min(8, max(1, np.ceil(30 * unfulfilled / dispense_want))))
        service = 100.0 if unfulfilled == 0 else round(100 * dispensed / dispense_want, 2)

        row = {**hs[hid], **ms[med]}
        row.update({
            "HospitalDemandRecordID": f"HDEM-{serial:08d}",
            "DemandMonth": month_start.strftime(DATE_FMT),
            "HospitalID": hid, med_col: med,
            "EstimatedDiseaseCases": int(round(g["EstimatedDiseaseCases"].mean() * ratio * rng.normal(1, 0.05))),
            "DiseaseRelatedAdmissions": int(round(g["DiseaseRelatedAdmissions"].mean() * ratio * rng.normal(1, 0.05))),
            "OutpatientEncounters": int(round(g["OutpatientEncounters"].mean() * ratio * rng.normal(1, 0.05))),
            "ForecastDemandPacks": forecast, "RequestedQuantityPacks": requested,
            "ApprovedQuantityPacks": approved, "ReceivedQuantityPacks": received,
            "EmergencyRequestQuantityPacks": emergency, "OpeningStockPacks": opening,
            "DispensedQuantityPacks": dispensed, "ConsumedQuantityPacks": consumed,
            "WastageQuantityPacks": wastage, "ClosingStockPacks": closing,
            "UnfulfilledDemandPacks": unfulfilled, "StockoutDays": stockout_days,
            "ServiceLevelPct": service,
            "MedicationRequestStatus": "Completed" if unfulfilled == 0 else "Partially fulfilled",
            "FormularyStatus": g["FormularyStatus"].iloc[-1],
            "AverageLeadTimeDays": int(rng.choice(g["AverageLeadTimeDays"].values)),
            "DemandTrendIndex": round(idx * rng.normal(1, 0.01), 3),
            "SourceSystem": source_system,
        })
        state["closing"][key] = int(closing)
        rows.append(row)
    state["hosp_serial"] = serial
    return pd.DataFrame(rows)[cols]


# ----------------------------------------------------------------- sales
def gen_sales(pool, state, month_start, month_end, n, rng):
    wk = np.bincount(pd.to_datetime(pool["SalesDate"], format=DATE_FMT).dt.weekday, minlength=7).astype(float)
    s = pool.iloc[rng.integers(0, len(pool), n)].reset_index(drop=True)

    days = pd.date_range(month_start, month_end)
    p = wk[days.weekday]
    sale_dt = pd.Series(days[rng.choice(len(days), n, p=p / p.sum())])
    time_part = s["SalesTimestampUTC"].str[11:19]

    out = s.copy()
    serial = state["sales_serial"] + 1 + np.arange(n)
    out["SalesTransactionID"] = [f"SALE-{x:09d}" for x in serial]
    out["SalesDate"] = sale_dt.dt.strftime(DATE_FMT)
    out["SalesTimestampUTC"] = sale_dt.dt.strftime("%Y-%m-%d") + "T" + time_part + "Z"
    out["PrescriptionID"] = np.where(s["PrescriptionRequiredFlag"] == "Y",
                                     [f"RX-{x:09d}" for x in serial], "")

    # new warehouse lots / production batches, each with one expiry date
    key = s["WarehouseLotID"] + "|" + s["ProductionBatchID"] + "|" + s["SourceWarehouseID"]
    first = s.assign(_k=key).drop_duplicates("_k")
    lot_map, batch_map, exp_map = {}, {}, {}
    for _, r in first.iterrows():
        k = r["_k"]
        state["lot_serial"] += 1
        lot_map[k] = f"WHLOT-{state['lot_serial']:07d}"
        plant = BATCH_RE.match(r["ProductionBatchID"]).group(2)
        state["batch_serial"][plant] = state["batch_serial"].get(plant, 0) + 1
        batch_map[k] = f"B{month_start.year % 100:02d}-PLT{plant}-{state['batch_serial'][plant]:06d}"
        d = min(max(int(r["DaysToExpiryAtSale"]), 180), 1075)
        exp_map[k] = month_start + pd.Timedelta(days=d)
    expiry = key.map(exp_map)
    out["WarehouseLotID"] = key.map(lot_map)
    out["ProductionBatchID"] = key.map(batch_map)
    out["BatchExpiryDate"] = expiry.dt.strftime(DATE_FMT)
    out["DaysToExpiryAtSale"] = (expiry - sale_dt).dt.days.astype(str)
        # new delivery/order IDs (one per original delivery), delivered shortly before this month
    orig_gap = (pd.to_datetime(s["SalesDate"], format=DATE_FMT)
                - pd.to_datetime(s["PharmacyDeliveryDate"], format=DATE_FMT)).dt.days.clip(lower=1, upper=120)
    dfirst = s.assign(_gap=orig_gap).drop_duplicates("PharmacyDeliveryID").set_index("PharmacyDeliveryID")["_gap"]
    state.setdefault("delivery_serial", 0)
    dnum, ddate = {}, {}
    for did, gap in dfirst.items():
        state["delivery_serial"] += 1
        dnum[did] = state["delivery_serial"]
        ddate[did] = month_start - pd.Timedelta(days=int(gap))
    num = s["PharmacyDeliveryID"].map(dnum)
    out["PharmacyDeliveryID"] = num.map(lambda x: f"PHD-{x:07d}")
    out["PharmacyOrderID"] = num.map(lambda x: f"PHO-{x:07d}")
    out["PharmacyDeliveryDate"] = s["PharmacyDeliveryID"].map(ddate).dt.strftime(DATE_FMT)

    # money: prices come from the current master (so revised prices flow into sales)
    master = state["master"]
    retail = s["MedicineID"].map(lambda m: float(master[m]["RecommendedRetailPriceUSD"]))
    wholesale = s["MedicineID"].map(lambda m: float(master[m]["WholesalePriceUSD"]))
    qty = s["QuantitySoldPacks"].astype(int)
    pct = s["PromotionCode"].fillna("").str.extract(r"(\d+)$")[0].astype(float).fillna(0)
    gross = (qty * retail).round(2)
    disc = (gross * pct / 100).round(2)
    net = (gross - disc).round(2)
    cogs = (qty * wholesale).round(2)
    money = {"UnitRetailPriceUSD": retail, "GrossSalesAmountUSD": gross, "DiscountAmountUSD": disc,
             "NetSalesAmountUSD": net, "SalesTaxUSD": (net * TAX_RATE).round(2),
             "CostOfGoodsSoldUSD": cogs, "GrossMarginUSD": (net - cogs).round(2)}
    for col, ser in money.items():
        out[col] = ser.map("{:.2f}".format)

    state["sales_serial"] += n
    return out[pool.columns]


# ----------------------------------------------------------------- runner
def run_refresh(sales_pct=SALES_PCT, reset=False):
    if reset and STATE_FILE.exists():
        STATE_FILE.unlink()
    master, sales, hosp = _read("01_master_data"), _read("05_pharmacy_sales_data"), _read("06_hospital_demand_data")
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else init_state(master, sales, hosp)

    y, m = map(int, state["last_month"].split("-"))
    month_start = pd.Timestamp(y, m, 1) + pd.DateOffset(months=1)
    month_end = month_start + pd.offsets.MonthEnd(0)
    rng = np.random.default_rng(1000 + state["refresh_no"])
    tag = month_start.strftime("%Y_%m")
    n_sales = int(round(state["total_sales_rows"] * sales_pct))

    m_df, changes = revise_master(state, list(master.columns), month_start, rng)
    h_df = gen_hospital(hosp, state, month_start, rng)
    s_df = gen_sales(sales, state, month_start, month_end, n_sales, rng)

    DROPZONE.mkdir(parents=True, exist_ok=True)
    m_df.to_csv(DROPZONE / f"01_master_data_rev_{tag}.csv", index=False)
    h_df.to_csv(DROPZONE / f"06_hospital_demand_data_{tag}.csv", index=False)
    s_df.to_csv(DROPZONE / f"05_pharmacy_sales_data_{tag}.csv", index=False)

    state["last_month"] = month_start.strftime("%Y-%m")
    state["refresh_no"] += 1
    state["total_sales_rows"] += n_sales
    STATE_FILE.write_text(json.dumps(state))

    summary = {"month": state["last_month"], "master_rows": len(m_df), "hospital_rows": len(h_df),
               "sales_rows": len(s_df), "price_changes": changes}
    print(summary)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct", type=float, default=SALES_PCT, help="sales rows per refresh as share of existing rows")
    ap.add_argument("--reset", action="store_true", help="forget previous refreshes and start again from the raw files")
    a = ap.parse_args()
    run_refresh(a.pct, a.reset)