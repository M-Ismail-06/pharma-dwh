import pandas as pd
from config import RAW, DROPZONE

df = pd.read_csv(next(RAW.glob("05_pharmacy_sales_data*.csv")), dtype=str).sample(100, random_state=1).reset_index(drop=True)

# give every row a fresh, unique ID so only the deliberate defects fail
df["SalesTransactionID"] = [f"SALE-9{i:08d}" for i in range(len(df))]

df.loc[0, "UnitRetailPriceUSD"] = "-5"                                   # price not > 0
df.loc[1, "MedicineID"] = ""                                             # blank medicine
df.loc[2, "MedicineID"] = "MED999"                                       # not in master
df.loc[3, "SalesDate"] = "31-02-24"                                      # impossible date
df.loc[4, "QuantitySoldPacks"] = "-1"                                    # negative quantity
df.loc[5, "NetSalesAmountUSD"] = str(float(df.loc[5, "NetSalesAmountUSD"]) + 1)  # formulas break
df.loc[6, "SalesTransactionID"] = "SALE-000000001"                       # duplicate of loaded row
df.loc[7, "SalesTransactionID"] = "SALE-000000002"                       # duplicate of loaded row

out = DROPZONE / "05_pharmacy_sales_data_test.csv"
df.to_csv(out, index=False)
print("written", out)