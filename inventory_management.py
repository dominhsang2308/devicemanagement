import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode

# Config
API_BASE = st.secrets.get("api_base", "http://localhost:8000/api")
API_KEY = st.secrets.get("api_key")  # optional
AUTO_REFRESH_SEC = 60
LOW_STOCK_THRESHOLD = 3  # UI highlight for low stock

st.set_page_config(page_title="Devices & Inventory", layout="wide")
st.markdown(
    """
    <style>
    .kpi { padding: 12px; border-radius: 8px; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.06) }
    .small { font-size:12px; color:#666 }
    </style>
    """,
    unsafe_allow_html=True,
)

st_autorefresh(interval=AUTO_REFRESH_SEC * 1000, key="auto_refresh")

# ---------- Helpers (API wrappers) ----------
def _headers():
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h

def api_get(path, params=None, timeout=20):
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, headers=_headers(), timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"GET {path} failed: {e}")
        return None

def api_post(path, payload, timeout=30):
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, headers=_headers(), timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as he:
        try:
            st.error(f"Error: {r.status_code} - {r.text}")
        except:
            st.error(f"HTTP error: {he}")
        return None
    except Exception as e:
        st.error(f"POST {path} failed: {e}")
        return None

def api_patch(path, payload, timeout=20):
    try:
        r = requests.patch(f"{API_BASE}{path}", json=payload, headers=_headers(), timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"PATCH {path} failed: {e}")
        return None

def api_post_raw(path, payload, timeout=30):
    # return Response for status checks
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, headers=_headers(), timeout=timeout)
        return r
    except Exception as e:
        st.error(f"POST {path} failed: {e}")
        return None

# ---------- Cached GETs ----------
@st.cache_data(ttl=30)
def get_inventory_items(limit=500, offset=0):
    params = {"limit": limit, "offset": offset}
    return api_get("/inventory", params=params) or []

@st.cache_data(ttl=30)
def get_license_pools():
    return api_get("/inventory/licenses") or []

@st.cache_data(ttl=30)
def get_history(limit=500):
    return api_get("/inventory/history", params={"limit": limit}) or []

# ---------- Inventory UI ----------
def render_inventory_page():
    st.title("Inventory Management")
    left, right = st.columns([3, 1])

    # Top quick stats
    with left:
        items = get_inventory_items(limit=1000)
        total_items = len(items)
        total_quantity = sum([i.get("quantity", 0) for i in items]) if items else 0

        st.markdown("### Overview")
        c1, c2, c3 = st.columns(3)
        c1.metric("SKUs", f"{total_items:,}")
        c2.metric("Total qty", f"{total_quantity:,}")
        low_stock = sum(1 for i in items if i.get("quantity", 0) <= LOW_STOCK_THRESHOLD)
        c3.metric("Low stock SKUs", f"{low_stock:,}")

    with right:
        st.markdown("### Actions")
        if st.button("Refresh data"):
            st.experimental_memo.clear()
            st.experimental_rerun()
        # quick links
        st.markdown("#### Import / Export")
        st.write("- Use Import/Export tab to bulk operations")

    st.markdown("---")

    tabs = st.tabs(["Items", "Licenses", "Assign / Return", "History", "Import/Export"])

    # ---- Items tab ----
    with tabs[0]:
        st.subheader("Inventory items")
        items = get_inventory_items(limit=1000)
        if items:
            df = pd.DataFrame(items)
            if "quantity" in df.columns:
                df["available"] = df["quantity"]
                # Add status column
                def status_badge(q):
                    if q <= 0:
                        return "out"
                    if q <= LOW_STOCK_THRESHOLD:
                        return "low"
                    return "ok"
                df["status"] = df["available"].apply(status_badge)
            else:
                df["available"] = 0
                df["status"] = "unknown"

            # show AgGrid table
            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_default_column(filter=True, sortable=True, resizable=True)
            gb.configure_selection(selection_mode="single", use_checkbox=False)
            gb.configure_column("status", header_name="Status", cellRenderer="""function(params){
                if(params.value=='low'){return '<span style="color:#d97706;font-weight:600'>LOW</span>'}
                if(params.value=='out'){return '<span style="color:#d62728;font-weight:600'>OUT</span>'}
                return '<span style="color:#2ca02c;font-weight:600'>OK</span>'}""", editable=False)
            grid_options = gb.build()
            grid_response = AgGrid(
                df,
                gridOptions=grid_options,
                enable_enterprise_modules=False,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                height=420,
            )
            selected = grid_response.get("selected_rows")
            if selected:
                sel = selected[0]
                st.markdown("### Selected item")
                st.write(sel)
                # action buttons for selected item
                col_edit, col_alloc, col_delete = st.columns(3)
                with col_edit:
                    if st.button("Edit selected"):
                        with st.form("edit_item_form"):
                            new_name = st.text_input("Name", value=sel.get("name", ""))
                            new_location = st.text_input("Location", value=sel.get("location", "") or "")
                            new_qty = st.number_input("Quantity", min_value=0, value=int(sel.get("quantity", 0)))
                            if st.form_submit_button("Save changes"):
                                payload = {"name": new_name, "location": new_location, "quantity": int(new_qty), "actor": "ui_user"}
                                res = api_patch(f"/inventory/{int(sel['id'])}", payload)
                                if res:
                                    st.success("Updated")
                                    st.experimental_rerun()
                with col_alloc:
                    if st.button("Allocate item to device"):
                        with st.form("allocate_item_form"):
                            device_id = st.text_input("Device Graph ID")
                            user_upn = st.text_input("User UPN (optional)")
                            actor = st.text_input("Your name", value="admin")
                            if st.form_submit_button("Allocate item"):
                                # For items, you might implement an endpoint like /inventory/{id}/assign
                                payload = {"item_id": int(sel["id"]), "device_graph_id": device_id, "user_upn": user_upn, "actor": actor}
                                r = api_post_raw(f"/inventory/assign", payload)
                                if r and r.status_code in (200,201):
                                    st.success("Allocated item")
                                    st.experimental_rerun()
                                else:
                                    st.error(f"Allocate failed: {r.status_code if r else ''} {r.text if r else ''}")
                with col_delete:
                    if st.button("Delete selected"):
                        if st.confirmation_dialog:
                            pass
                        # Use a simple confirm
                        if st.checkbox("Confirm delete this item?"):
                            r = requests.delete(f"{API_BASE}/inventory/{int(sel['id'])}", headers=_headers())
                            if r.ok:
                                st.success("Deleted")
                                st.experimental_rerun()
                            else:
                                st.error(f"Delete failed: {r.status_code} {r.text}")
        else:
            st.info("No inventory items found. Create a new item below.")

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
                        "actor": "ui_user",
                    }
                    res = api_post_raw("/inventory", payload)
                    if res and res.status_code in (200,201):
                        st.success("Item created")
                        st.experimental_rerun()
                    else:
                        st.error(f"Create failed: {res.status_code if res else ''} {res.text if res else ''}")

    # ---- Licenses tab ----
    with tabs[1]:
        st.subheader("License pools")
        pools = get_license_pools()
        if pools:
            dfp = pd.DataFrame(pools)
            dfp["available"] = dfp["total"] - dfp["allocated"]
            def avail_color(x):
                if x <= 0: return "❌ Out"
                if x <= LOW_STOCK_THRESHOLD: return "⚠️ Low"
                return "✅ Avail"
            dfp["status"] = dfp["available"].apply(avail_color)
            st.dataframe(dfp)
        else:
            st.info("No license pools.")

        with st.expander("Create license pool"):
            with st.form("new_license"):
                sku = st.text_input("License SKU (unique)")
                display = st.text_input("Display name")
                total = st.number_input("Total count", min_value=0, value=0)
                if st.form_submit_button("Create license pool"):
                    payload = {"sku": sku, "display_name": display, "total": int(total), "actor": "ui_user"}
                    res = api_post_raw("/inventory/licenses", payload)
                    if res and res.status_code in (200,201):
                        st.success("License pool created")
                        st.experimental_rerun()
                    else:
                        st.error(f"Error: {res.status_code if res else ''} {res.text if res else ''}")

    # ---- Assign / Return tab ----
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
                r = api_post_raw(f"/inventory/licenses/{license_id}/allocate", payload)
                if r and r.status_code == 200:
                    st.success("Allocated")
                else:
                    st.error(f"Allocate failed: {r.status_code if r else ''} {r.text if r else ''}")

        st.markdown("---")
        st.subheader("Return / Revoke assignment")
        hist = get_history(limit=200)
        dfhist = pd.DataFrame(hist)
        if not dfhist.empty:
            st.dataframe(dfhist.head(50))
            with st.form("return_form"):
                assignment_id = st.number_input("Assignment ID to return", min_value=0, value=0)
                actor_r = st.text_input("Your name", value="admin")
                if st.form_submit_button("Return"):
                    r = api_post_raw(f"/inventory/assignments/{int(assignment_id)}/return", {"actor": actor_r})
                    if r and r.status_code == 200:
                        st.success("Returned")
                    else:
                        st.error(f"Return failed: {r.status_code if r else ''} {r.text if r else ''}")
        else:
            st.info("No history available to return.")

    # ---- History tab ----
    with tabs[3]:
        st.subheader("Inventory history / audit")
        history = get_history(limit=500)
        if history:
            dfh = pd.DataFrame(history)
            if "timestamp" in dfh.columns:
                dfh["timestamp"] = pd.to_datetime(dfh["timestamp"])
            st.dataframe(dfh.sort_values("timestamp", ascending=False))
        else:
            st.info("No history records.")

    # ---- Import / Export tab ----
    with tabs[4]:
        st.subheader("Import / Export")
        st.markdown("Bulk import CSV to create inventory items. CSV columns: sku,name,item_type,quantity,location")
        uploaded = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded:
            try:
                df = pd.read_csv(uploaded)
                st.write(df.head())
                if st.button("Import to inventory"):
                    payload = {"items": df.to_dict(orient="records")}
                    r = api_post_raw("/inventory/bulk_import", payload, timeout=120)
                    if r and r.status_code in (200,201):
                        st.success(f"Imported {r.json().get('imported', 'N/A')} records")
                        st.experimental_rerun()
                    else:
                        st.error(f"Import failed: {r.status_code if r else ''} {r.text if r else ''}")
            except Exception as e:
                st.error(f"Failed to parse CSV: {e}")

        # Export
        items = get_inventory_items(limit=10000)
        if items:
            df = pd.DataFrame(items)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download inventory CSV", data=csv, file_name="inventory_export.csv", mime="text/csv")
        else:
            st.info("No inventory to export.")

# ---------- Minimal Dashboard & About for menu ----------
def render_dashboard():
    st.header("Devices Management — Dashboard")
    st.markdown("Your existing dashboard code should be here (snapshots, KPIs, charts).")
    st.info("This area is unchanged from your previous dashboard. Use sidebar to switch to Inventory.")

def render_about():
    st.header("About")
    st.markdown("""
    Admin app - Devices & Inventory.
    - Inventory page includes CRUD, assignment, import/export, audit.
    - Protect mutating endpoints with API key or Azure AD in production.
    """)

# ---------- Sidebar menu ----------
st.sidebar.title("Menu")
page = st.sidebar.radio("Go to", ["Dashboard", "Inventory", "About"])

if page == "Dashboard":
    render_dashboard()
elif page == "Inventory":
    try:
        render_inventory_page()
    except Exception as e:
        st.error("Lỗi khi hiển thị Inventory:")
        st.exception(e)
else:
    render_about()