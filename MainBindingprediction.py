from fastapi import FastAPI
import pandas as pd
from sqlalchemy import create_engine

app = FastAPI()

# ---------------- DATABASE CONNECTION ----------------

password = "Node%402025"

engine = create_engine(
    f"mysql+pymysql://root:{password}@194.61.31.18:3369/Technode"
)

# ---------------- DASHBOARD API ----------------

@app.get("/meter_dashboard")
def meter_dashboard(mtid: str):

    try:

        query = """
        SELECT GatewayRT, KWH, KVAH, Avg_PF
        FROM todayslive
        WHERE MTID=%s
        AND DATE(GatewayRT)=CURDATE()
        ORDER BY GatewayRT
        """

        df = pd.read_sql(query, engine, params=(mtid,))

        if df.empty:
            return {"message": "No data found for this MTID today"}

        # ---------- DATA CLEANING ---------- #

        df["GatewayRT"] = pd.to_datetime(df["GatewayRT"])
        df["KWH"] = pd.to_numeric(df["KWH"], errors="coerce")
        df["KVAH"] = pd.to_numeric(df["KVAH"], errors="coerce")
        df["Avg_PF"] = pd.to_numeric(df["Avg_PF"], errors="coerce")

        df = df.sort_values("GatewayRT")

        # ---------- POWER FACTOR ---------- #

        avg_pf = round(df["Avg_PF"].mean(), 3)
        max_pf = round(df["Avg_PF"].max(), 3)
        min_pf = round(df["Avg_PF"].min(), 3)

        if avg_pf >= 0.95:
            pf_status = "Good"
        elif avg_pf >= 0.90:
            pf_status = "Moderate"
        else:
            pf_status = "Poor"

        # ---------- INTERVAL ENERGY ---------- #

        df["prev_kwh"] = df["KWH"].shift(1)
        df["interval_kwh"] = df["KWH"] - df["prev_kwh"]

        df["prev_kvah"] = df["KVAH"].shift(1)
        df["prev_time"] = df["GatewayRT"].shift(1)

        df["delta_kvah"] = df["KVAH"] - df["prev_kvah"]

        df["time_diff"] = (df["GatewayRT"] - df["prev_time"]).dt.total_seconds() / 60

        df = df.dropna()

        # ---------- TOTAL ENERGY ---------- #

        total_kwh = round(df["interval_kwh"].sum(), 1)

        # ---------- MAXIMUM DEMAND ---------- #

        # ---------- MAXIMUM DEMAND (15 MIN BLOCK) ---------- #

        df = df.set_index("GatewayRT")
        
        # energy difference
        df["delta_kvah"] = df["KVAH"].diff()
        
        # remove negative or null values
        df = df[df["delta_kvah"] >= 0]
        
        # 15 minute energy blocks
        kvah_15min = df["delta_kvah"].resample("15min").sum()
        
        # convert energy to demand
        demand_15min = kvah_15min * 4
        
        # maximum demand
        maximum_demand_kva = round(demand_15min.max(),1)
        
        df = df.reset_index()

        # ---------- TOD ZONES ---------- #

        hour = df["GatewayRT"].dt.hour

        df["zone"] = "Zone D"

        df.loc[hour < 6, "zone"] = "Zone A"
        df.loc[(hour >= 6) & (hour < 9), "zone"] = "Zone B"
        df.loc[(hour >= 9) & (hour < 17), "zone"] = "Zone C"

        # ---------- ZONE ENERGY ---------- #

        zone_energy = df.groupby("zone")["interval_kwh"].sum()

        zones = {"Zone A": 0, "Zone B": 0, "Zone C": 0, "Zone D": 0}

        for z in zone_energy.index:
            zones[z] = round(zone_energy[z], 1)

        # ---------- ZONE PERCENT ---------- #

        total_energy = sum(zones.values())

        zone_percent = {}

        for z, v in zones.items():
            if total_energy > 0:
                zone_percent[z] = round((v / total_energy) * 100, 2)
            else:
                zone_percent[z] = 0

        # ---------- JSON OUTPUT ---------- #

        return {
            "MTID": mtid,

            "Power Factor": {
                "Average PF": avg_pf,
                "Maximum PF": max_pf,
                "Minimum PF": min_pf,
                "Status": pf_status
            },

            "Energy": {
                "Total Energy Today (kWh)": total_kwh,
                "Maximum Demand (kVA)": maximum_demand_kva
            },

            "TOD Zone Energy": {
                "Zone A": {
                    "Energy (kWh)": zones["Zone A"],
                    "Percent (%)": zone_percent["Zone A"]
                },
                "Zone B": {
                    "Energy (kWh)": zones["Zone B"],
                    "Percent (%)": zone_percent["Zone B"]
                },
                "Zone C": {
                    "Energy (kWh)": zones["Zone C"],
                    "Percent (%)": zone_percent["Zone C"]
                },
                "Zone D": {
                    "Energy (kWh)": zones["Zone D"],
                    "Percent (%)": zone_percent["Zone D"]
                }
            }
        }

    except Exception as e:
        return {"error": str(e)}