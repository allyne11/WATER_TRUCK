import os, math
from datetime import datetime, timedelta
from typing import Optional, List

import pandas as pd
import numpy as np
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Water Truck Dispatch", page_icon="🚚", layout="wide")

DB_URL = os.environ.get("WATERTRUCK_DB_URL", "sqlite:///watertruck.db")

@st.cache_resource
def get_engine() -> Engine:
    engine = create_engine(DB_URL, future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS customers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          address TEXT NOT NULL,
          phone TEXT,
          latitude REAL,
          longitude REAL,
          last_filled DATE,
          avg_interval_days REAL,
          notes TEXT
        );""")
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS fills (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER NOT NULL,
          filled_at DATE NOT NULL,
          gallons REAL,
          FOREIGN KEY(customer_id) REFERENCES customers(id)
        );""")
    return engine

engine = get_engine()

@st.cache_resource
def geocoder():
    geolocator = Nominatim(user_agent="watertruck_mvp")
    return RateLimiter(geolocator.geocode, min_delay_seconds=1)

def geocode_address(addr: str):
    try:
        loc = geocoder()(addr)
        if loc:
            return loc.latitude, loc.longitude
    except Exception:
        pass
    return None, None

def fetch_df(query: str, **params) -> pd.DataFrame:
    with engine.begin() as conn:
        return pd.read_sql_query(text(query), conn, params=params)

def add_customer(name, address, phone, last_filled, notes):
    lat, lon = geocode_address(address)
    with engine.begin() as conn:
        conn.execute(text("""
          INSERT INTO customers(name,address,phone,latitude,longitude,last_filled,avg_interval_days,notes)
          VALUES(:n,:a,:p,:lat,:lon,:lf,:avg,:notes)
        """), {"n": name, "a": address, "p": phone, "lat": lat, "lon": lon,
               "lf": last_filled.date() if last_filled else None, "avg": None, "notes": notes})

def record_fill(customer_id: int, filled_at: datetime, gallons: Optional[float] = None):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO fills(customer_id, filled_at, gallons) VALUES(:cid,:dt,:gal)"),
                     {"cid": customer_id, "dt": filled_at.date(), "gal": gallons})
        conn.execute(text("UPDATE customers SET last_filled=:dt WHERE id=:cid"),
                     {"cid": customer_id, "dt": filled_at.date()})

def compute_intervals(customer_id: int) -> List[int]:
    fills = fetch_df("SELECT filled_at FROM fills WHERE customer_id=:cid ORDER BY filled_at ASC", cid=customer_id)
    if len(fills) < 2:
        return []
    days = pd.to_datetime(fills["filled_at"]).diff().dropna().dt.days.astype(int)
    return days.tolist()

def global_median_interval() -> Optional[float]:
    all_deltas = []
    for cid in fetch_df("SELECT id FROM customers")["id"].tolist():
        all_deltas += compute_intervals(cid)
    return float(np.median(all_deltas)) if all_deltas else None

def next_due_date_for_customer(row: pd.Series, today: datetime):
    cid = int(row["id"])
    intervals = compute_intervals(cid)
    if intervals:
        interval = float(np.median(intervals))
    else:
        interval = row.get("avg_interval_days") or global_median_interval() or 14.0
    last = row["last_filled"]
    due = (today if pd.isna(last) else pd.to_datetime(last)) + timedelta(days=int(round(interval)))
    days_over = (today - pd.to_datetime(due)).days
    risk = 1 / (1 + math.exp(-days_over / max(3.0, interval / 6)))
    return due, float(risk)

st.title("🚚 Water Truck – Customers, Map & Refill Predictions")

with st.sidebar:
    st.header("Add / Update Customer")
    name = st.text_input("Name")
    address = st.text_area("Address")
    phone = st.text_input("Phone")
    last_filled = st.date_input("Last filled (optional)", value=None)
    notes = st.text_area("Notes", height=80)
    if st.button("➕ Add customer") and name and address:
        add_customer(name, address, phone, pd.to_datetime(last_filled) if last_filled else None, notes)
        st.success("Customer added. Geocoding may take a moment.")

    st.divider()
    st.header("Record Fill")
    custs = fetch_df("SELECT id, name FROM customers ORDER BY name")
    if not custs.empty:
        selected = st.selectbox("Customer", custs["name"].tolist())
        cid = int(custs[custs["name"] == selected]["id"].iloc[0])
        dt = st.date_input("Fill date", value=datetime.today())
        gallons = st.number_input("Gallons (optional)", min_value=0.0, step=100.0, value=0.0)
        if st.button("🧾 Save fill"):
            record_fill(cid, pd.to_datetime(dt), gallons if gallons > 0 else None)
            st.success("Fill recorded and last date updated.")

tab1, tab2, tab3 = st.tabs(["Customers", "Map", "Predictions"])

with tab1:
    st.subheader("Customers")
    df = fetch_df("SELECT * FROM customers ORDER BY name")
    st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Customer Map")
    df = fetch_df("SELECT id,name,address,latitude,longitude,last_filled FROM customers")
    if not df.empty and df["latitude"].notna().any():
        center_lat = df["latitude"].dropna().mean()
        center_lon = df["longitude"].dropna().mean()
    else:
        center_lat, center_lon = 30.2672, -97.7431
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
    for _, r in df.iterrows():
        if pd.notna(r["latitude"]) and pd.notna(r["longitude"]):
            popup = f"<b>{r['name']}</b><br>{r['address']}<br>Last filled: {r['last_filled']}"
            folium.Marker([r["latitude"], r["longitude"]], popup=popup).add_to(m)
    st_folium(m, height=520, width=None)

with tab3:
    st.subheader("Predicted Next Fills")
    today = datetime.today()
    df = fetch_df("SELECT * FROM customers ORDER BY name")
    if df.empty:
        st.info("No customers yet.")
    else:
        df["due_date"], df["risk_score"] = zip(*df.apply(lambda r: next_due_date_for_customer(r, today), axis=1))
        df["days_until_due"] = (pd.to_datetime(df["due_date"]) - today).dt.days
        df_sorted = df.sort_values(["risk_score", "days_until_due"], ascending=[False, True])
        st.dataframe(df_sorted[["name","address","phone","last_filled","due_date","days_until_due","risk_score"]],
                     use_container_width=True)
