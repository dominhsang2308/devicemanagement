"""
Streamlit app with sidebar menu:
- Dashboard (Device Management)  -> uses /api/dashboard/summary and /api/dashboard/snapshots
- Inventory Management           -> uses /api/inventory, /api/inventory/licenses, /api/inventory/history, allocation endpoints

Requirements:
pip install streamlit requests pandas plotly streamlit-autorefresh st-aggrid
"""
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

API_BASE = st.secrets.get("api_base", "http://localhost:8000/api")
AUTO_REFRESH_SEC = 60

st.set_page_config(page_title="Devices & Inventory", layout="wide")
st_autorefresh(interval=AUTO_REFRESH_SEC * 1000, key="auto_refresh")

# -------------------------
# Helpers
# -------------------------
@st.cache_data(ttl=30)
def get_summary():
    r = requests.get(f"{API_BASE}/dashboard/summary", timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=30)
def get_latest_snapshot():
    try:
        r = requests.get(f"{API_BASE}/dashboard/snapshots?limit=1", timeout=20)
        r.raise_for_status()
        arr = r.json()
        if isinstance(arr, list) and arr:
            return arr[0]
    except:
        return None

@st.cache_data(ttl=30)
def get_inventory_items(limit=500):
    r = requests.get(f"{API_BASE}/inventory?limit={limit}", timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=30)
def get_license_pools():
    r = requests.get(f"{API_BASE}/inventory/licenses", timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=30)
def get_history(limit=200):
    r = requests.get(f"{API_BASE}/inventory/history?limit={limit}", timeout=20)
    r.raise_for_status()
    return r.json()

def post_json(path, payload):
    r = requests.post(f"{API_BASE}{path}", json=payload, timeout=20)
    return r

# -------------------------
# Layout: sidebar menu
# -------------------------
st.sidebar.title("Menu")
page = st.sidebar.radio("Go to", ["Dashboard", "Inventory Management", "About"])

# -------------------------
# Page: Dashboard (Device Management)
# -------------------------
def render_dashboard():
    st.title("Devices Management — Dashboard")
    # prefer snapshot for last update/time series
    latest_snapshot = get_latest_snapshot()
    if latest_snapshot:
        last_ts = pd.to_datetime(latest_snapshot.get("timestamp"))
    else:
        last_ts = datetime.utcnow()
    st.markdown(f"Last update (UTC): **{last_ts.strftime('%Y-%m-%d %H:%M:%S')}**")

    # summary KPIs
    if latest_snapshot:
        total = latest_snapshot.get("total", 0)
        corporate = latest_snapshot.get("corporate", 0)
        personal = latest_snapshot.get("personal", 0)
        compliant = latest_snapshot.get("compliant", 0)
        noncompliant = latest_snapshot.get("noncompliant", 0)
        owners = latest_snapshot.get("owners", {})
        by_os = latest_snapshot.get("by_os", {})
    else:
        summary = get_summary()
        total = summary.get("total", 0)
        corporate = summary.get("corporate", 0)
        personal = summary.get("personal", 0)
        compliant = summary.get("compliant", 0)
        noncompliant = summary.get("noncompliant", 0)
        owners = summary.get("owners", {})
        by_os = summary.get("by_os", {})

    c1, c2, c3, c4, c5 = st.columns([1.2,1.2,1.2,1.2,1.2])
    c1.metric("Total devices", f"{total:,}")
    c2.metric("Corporate", f"{corporate:,}")
    c3.metric("Personal", f"{personal:,}")
    c4.metric("Compliant", f"{compliant:,}")
    c5.metric("Non-compliant", f"{noncompliant:,}")

    st.markdown("---")
    st.subheader("Top OS distribution")
    if by_os:
        df_os = pd.DataFrame({"os": list(by_os.keys()), "count": list(by_os.values())})
        df_os = df_os.sort_values("count", ascending=False).head(20)
        fig = px.bar(df_os, x="os", y="count", color="os", height=360)
        fig.update_layout(showlegend=False, margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No OS distribution data available.")

    # Trend chart if snapshots exist
    st.subheader("Trend (if snapshots available)")
    try:
        r = requests.get(f"{API_BASE}/dashboard/snapshots?limit=200", timeout=30)
        r.raise_for_status()
        snaps = r.json()
        if snaps:
            df = pd.DataFrame(snaps)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp")
            cols = ["total", "noncompliant"]
            df_plot = df[["timestamp"] + [c for c in cols if c in df.columns]]
            fig2 = px.line(df_plot, x="timestamp", y=cols, markers=True, height=400)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Chưa có snapshot lịch sử. Bật scheduler backend để lưu snapshots.")
    except Exception as e:
        st.warning("Không thể lấy snapshots: " + str(e))

# -------------------------
# Page: Inventory Management
# -------------------------
def render_inventory():
    st.title("Inventory Management")
    tabs = st.tabs(["Items", "Licenses", "Assign / Return", "History", "Reports"])
    # Items tab
    with tabs[0]:
        st.subheader("Inventory items")
        items = get_inventory_items()
        if items:
            df = pd.DataFrame(items)
            if "quantity" in df.columns:
                df["available"] = df["quantity"]  # you can expand with reserved logic
            st.dataframe(df)
        else:
            st.info("No inventory items found.")

        with st.expander("Create new inventory item"):
            with st.form("new_item"):
                sku = st.text_input("SKU")
                name = st.text_input("Name")
                item_type = st.selectbox("Type", ["device", "accessory", "license"])
                quantity = st.number_input("Quantity", min_value=0, value=1)
                location = st.text_input("Location")
                notes = st.text_area("Notes")
                if st.form_submit_button("Create"):
                    payload = {
                        "sku": sku,
                        "name": name,
                        "item_type": item_type,
                        "quantity": int(quantity),
                        "location": location,
                        "metadata": {"notes": notes},
                    }
                    r = requests.post(f"{API_BASE}/inventory", json=payload, timeout=20)
                    if r.status_code in (200,201):
                        st.success("Item created")
                        st.experimental_rerun()
                    else:
                        st.error(f"Create failed: {r.status_code} {r.text}")

    # Licenses tab
    with tabs[1]:
        st.subheader("License pools")
        pools = get_license_pools()
        if pools:
            dfp = pd.DataFrame(pools)
            dfp["available"] = dfp["total"] - dfp["allocated"]
            st.dataframe(dfp)
        else:
            st.info("No license pools.")

        with st.expander("Create license pool"):
            with st.form("new_license"):
                sku = st.text_input("License SKU (unique)")
                display = st.text_input("Display name")
                total = st.number_input("Total count", min_value=0, value=0)
                if st.form_submit_button("Create license pool"):
                    payload = {"sku": sku, "display_name": display, "total": int(total)}
                    r = requests.post(f"{API_BASE}/inventory/licenses", json=payload, timeout=20)
                    if r.status_code in (200,201):
                        st.success("License pool created")
                        st.experimental_rerun()
                    else:
                        st.error(f"Error: {r.status_code} {r.text}")

    # Assign / Return tab
    with tabs[2]:
        st.subheader("Allocate license to user/device")
        pools = get_license_pools()
        if not pools:
            st.info("No licenses. Create a license pool first.")
        else:
            choices = {p["id"]: f'{p["sku"]} (avail {p["total"]-p["allocated"]})' for p in pools}
            license_id = st.selectbox("License pool", options=list(choices.keys()), format_func=lambda k: choices[k])
            user_upn = st.text_input("User UPN (e.g. user@company.com)")
            device_graph_id = st.text_input("Device Graph ID (optional)")
            actor = st.text_input("Your name / actor", value="admin")
            if st.button("Allocate"):
                payload = {"user_upn": user_upn, "device_graph_id": device_graph_id, "actor": actor}
                r = requests.post(f"{API_BASE}/inventory/licenses/{license_id}/allocate", json=payload, timeout=20)
                if r.status_code == 200:
                    st.success("Allocated")
                else:
                    st.error(f"Allocate failed: {r.status_code} {r.text}")

        st.markdown("---")
        st.subheader("Return / Revoke assignment")
        hist = get_history(limit=200)
        dfhist = pd.DataFrame(hist)
        if not dfhist.empty:
            # show recent allocations from history or assignments endpoint if available
            st.dataframe(dfhist.head(50))
            with st.form("return_form"):
                assignment_id = st.number_input("Assignment ID to return", min_value=0, value=0)
                actor_r = st.text_input("Your name", value="admin")
                if st.form_submit_button("Return"):
                    r = requests.post(f"{API_BASE}/inventory/assignments/{assignment_id}/return", json={"actor": actor_r}, timeout=20)
                    if r.status_code == 200:
                        st.success("Returned")
                    else:
                        st.error(f"Return failed: {r.status_code} {r.text}")
        else:
            st.info("No history available to return.")

    # History tab
    with tabs[3]:
        st.subheader("Inventory history / audit")
        history = get_history(limit=500)
        if history:
            dfh = pd.DataFrame(history)
            dfh["timestamp"] = pd.to_datetime(dfh["timestamp"])
            st.dataframe(dfh.sort_values("timestamp", ascending=False))
        else:
            st.info("No history records.")

    # Reports tab
    with tabs[4]:
        st.subheader("Reports & exports")
        items = get_inventory_items()
        if items:
            df = pd.DataFrame(items)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download inventory CSV", data=csv, file_name="inventory.csv", mime="text/csv")
        else:
            st.info("No data to export.")

# -------------------------
# Page: About
# -------------------------
def render_about():
    st.title("About")
    st.markdown("""
    This application combines:
    - Device Management Dashboard (Intune -> backend snapshots)
    - Inventory Management (items, license pools, assign/return)

    Tips:
    - Protect mutating endpoints with auth (API key or Azure AD).
    - For production, prefer Postgres (SQLite has concurrency limits).
    """)

# -------------------------
# Router
# -------------------------
if page == "Dashboard":
    render_dashboard()
elif page == "Inventory Management":
    render_inventory()
else:
    render_about()