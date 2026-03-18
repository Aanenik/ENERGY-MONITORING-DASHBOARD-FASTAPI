from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import pandas as pd
from sqlalchemy import create_engine

app = FastAPI()

# ---------------- DATABASE CONNECTION ----------------

password = "Node%402025"

engine = create_engine(
    f"mysql+pymysql://root:{password}@194.61.31.18:3369/Technode"
)

# ---------------- HOME PAGE ----------------

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<html>
<head>
<title>Energy Monitoring Dashboard</title>
</head>
<body>

<h2>Enter MTID</h2>

<form action="/meter_dashboard">
<input type="text" name="mtid" placeholder="Enter MTID">
<button type="submit">Check</button>
</form>

</body>
</html>
"""

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
            return {"message": "No data found"}

        # ---------- DATA CLEANING ---------- #

        df["GatewayRT"] = pd.to_datetime(df["GatewayRT"])
        df["KWH"] = pd.to_numeric(df["KWH"], errors="coerce")
        df["KVAH"] = pd.to_numeric(df["KVAH"], errors="coerce")
        df["Avg_PF"] = pd.to_numeric(df["Avg_PF"], errors="coerce")

        df = df.sort_values("GatewayRT")

        # ----------  15-MIN RESAMPLING ---------- #

        df = df.set_index("GatewayRT")

        df_15 = df.resample("15min").agg({
            "KWH": "max",
            "KVAH": "max",
            "Avg_PF": "mean"  
        })

        # ---------- INTERVAL CALCULATION ---------- #

        df_15["interval_kwh"] = df_15["KWH"].diff()
        df_15["delta_kvah"] = df_15["KVAH"].diff()

        # ---------- CLEAN DATA ---------- #

        df_15 = df_15[
            (df_15["interval_kwh"].notna()) &
            (df_15["interval_kwh"] >= 0) &
            (df_15["delta_kvah"] >= 0)
        ]

        if df_15.empty:
            return {"message": "No valid resampled data"}

        # ---------- POWER FACTOR ---------- #

        avg_pf = round(df_15["Avg_PF"].mean(), 2)
        max_pf = round(df_15["Avg_PF"].max(), 2)
        min_pf = round(df_15["Avg_PF"].min(), 2)

        if avg_pf >= 0.95:
            pf_status = "Good"
        elif avg_pf >= 0.90:
            pf_status = "Moderate"
        else:
            pf_status = "Poor"

        # ---------- TOTAL ENERGY ---------- #

        total_kwh = round(df_15["interval_kwh"].sum(), 1)

        # ---------- MAXIMUM DEMAND (15 MIN) ---------- #

        df_15["demand_kva"] = df_15["delta_kvah"] * 4
        maximum_demand_kva = round(df_15["demand_kva"].max(), 1)

        # ---------- TOD ZONES ---------- #

        hour = df_15.index.hour

        df_15["zone"] = "Zone D"
        df_15.loc[hour < 6, "zone"] = "Zone A"
        df_15.loc[(hour >= 6) & (hour < 9), "zone"] = "Zone B"
        df_15.loc[(hour >= 9) & (hour < 17), "zone"] = "Zone C"

        # ---------- ZONE ENERGY ---------- #

        zone_energy = df_15.groupby("zone")["interval_kwh"].sum()

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
            "Interval": "15 Minutes (Resampled)",
            "Power_Factor": {
                "Average_PF": avg_pf,
                "Maximum_PF": max_pf,
                "Minimum_PF": min_pf,
                "Status": pf_status
            },
            "Energy": {
                "Total_Energy_kWh": total_kwh,
                "Maximum_Demand_kVA": maximum_demand_kva
            },
            "TOD_Zone_Energy": {
                "Zone_A": {
                    "Energy_kWh": zones["Zone A"],
                    "Percent": zone_percent["Zone A"]
                },
                "Zone_B": {
                    "Energy_kWh": zones["Zone B"],
                    "Percent": zone_percent["Zone B"]
                },
                "Zone_C": {
                    "Energy_kWh": zones["Zone C"],
                    "Percent": zone_percent["Zone C"]
                },
                "Zone_D": {
                    "Energy_kWh": zones["Zone D"],
                    "Percent": zone_percent["Zone D"]
                }
            }
        }

    except Exception as e:
        return {"error": str(e)}