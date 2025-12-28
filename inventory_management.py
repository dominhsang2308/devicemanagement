import streamlit as st
import requests
import pandas as pd
from typing import Optional
import plotly.express as px
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode, JsCode

# Config
API_BASE = st.secrets.get("api_base", "http://localhost:8000/api")
API_KEY = st.secrets.get("api_key")  # optional
AUTO_REFRESH_SEC = 60
LOW_STOCK_THRESHOLD = 3  # UI highlight for low stock

# Display API connection info in sidebar for debugging
with st.sidebar:
    st.caption(f"🔗 API: {API_BASE}")
    # Test connection
    try:
        test_response = requests.get(f"{API_BASE.replace('/api', '')}/docs", timeout=2)
        if test_response.ok:
            st.caption("✅ Connected")
        else:
            st.caption("⚠️ API responding with errors")
    except:
        st.caption("❌ Cannot connect to API")

st.set_page_config(page_title="Devices & Inventory", layout="wide")
st.markdown(
    """
    <style>
    .kpi { padding: 12px; border-radius: 8px; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.06) }
    .small { font-size:12px; color:#666 }
    /* Dark theme for AgGrid */
    .ag-theme-streamlit-dark {
        --ag-background-color: #1e1e1e;
        --ag-header-background-color: #2d2d2d;
        --ag-odd-row-background-color: #252525;
        --ag-header-foreground-color: #e0e0e0;
        --ag-foreground-color: #e0e0e0;
        --ag-border-color: #404040;
        --ag-row-hover-color: #333333;
        --ag-selected-row-background-color: #3d5a80;
    }
    
    /* Toolbar styling */
    .toolbar-container {
        background: #2d2d2d;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 16px;
        display: flex;
        gap: 12px;
        align-items: center;
    }
    
    /* Status badge styling */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 12px;
        text-align: center;
    }
    
    .status-in-stock {
        background-color: #3b82f6;
        color: white;
    }
    
    .status-in-use {
        background-color: #10b981;
        color: white;
    }
    
    .status-retired {
        background-color: #6b7280;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st_autorefresh(interval=AUTO_REFRESH_SEC * 1000, key="auto_refresh_inventory")

# ---------- Helpers (API wrappers) ----------
def _headers():
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h

# Compatibility helpers for different Streamlit versions
def safe_clear_cache():
    try:
        if hasattr(st, "cache_data") and hasattr(st.cache_data, "clear"):
            st.cache_data.clear()
        elif hasattr(st, "experimental_memo") and hasattr(st.experimental_memo, "clear"):
            st.experimental_memo.clear()
    except Exception:
        pass


def safe_rerun():
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
        elif hasattr(st, "rerun"):
            st.rerun()
    except Exception:
        pass

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
    except requests.exceptions.Timeout:
        st.error(f"⏱️ Request timeout: {path} took longer than {timeout}s")
        return None
    except requests.exceptions.ConnectionError:
        st.error(f"🔌 Connection error: Cannot reach API at {API_BASE}")
        return None
    except Exception as e:
        st.error(f"❌ Request failed: {str(e)}")
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


@st.cache_data(ttl=15)
def get_devices_in_use():
    """Fetch devices directly from Intune via Graph API"""
    result = api_get("/intune/devices")
    if result and isinstance(result, dict) and "error" in result:
        st.warning(f"Intune API Error: {result.get('error')}")
        return []
    return result or []


@st.cache_data(ttl=15)
def get_devices_in_stock():
    return api_get("/inventory/devices/in_stock") or []


def api_assign_device(item_id: int, user_upn: str, device_graph_id: Optional[str], actor: str = "ui_user"):
    payload = {"item_id": item_id, "user_upn": user_upn, "device_graph_id": device_graph_id, "actor": actor}
    return api_post_raw("/inventory/assign", payload)


def api_unassign_by_item(item_id: int, actor: str = "ui_user"):
    payload = {"item_id": item_id, "actor": actor}
    return api_post_raw("/inventory/assignments/unassign_by_item", payload)


@st.cache_data(ttl=60)
def get_users(limit: int = 200):
    return api_get("/users", params={"limit": limit}) or []

# ---------- Inventory UI ----------
def render_inventory_page():
    st.title("Inventory Management")
    left, right = st.columns([3, 1])

    # session state for stable single-click selection
    if "selected_item" not in st.session_state:
        st.session_state["selected_item"] = None
    if "selected_device_in_stock" not in st.session_state:
        st.session_state["selected_device_in_stock"] = None
    if "selected_device_in_use" not in st.session_state:
        st.session_state["selected_device_in_use"] = None

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
            get_inventory_items.clear()
            get_license_pools.clear()
            get_devices_in_stock.clear()
            get_devices_in_use.clear()
            st.rerun()
        # quick links
        st.markdown("#### Import / Export")
        st.write("- Use Import/Export tab to bulk operations")

    st.markdown("---")

    tabs = st.tabs(["Devices In Use", "Devices In Stock", "Items", "Licenses", "Assign / Return", "History", "Import/Export"])

    # ---- Devices In Use tab ----
    with tabs[0]:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader("📱 Devices In Use (Intune Managed)")
        with col2:
            if st.button("🔄 Refresh", key="refresh_in_use"):
                get_devices_in_use.clear()
                st.rerun()
        
        st.markdown("*Live data from Microsoft Intune - read-only view*")
        
        with st.spinner("Loading devices from Intune..."):
            devices = get_devices_in_use()
        
        if devices:
            dfd = pd.DataFrame(devices)
            
            # Format columns for display
            display_columns = []
            if "deviceName" in dfd.columns:
                display_columns.append("deviceName")
            elif "device_name" in dfd.columns:
                dfd.rename(columns={"device_name": "deviceName"}, inplace=True)
                display_columns.append("deviceName")
            elif "name" in dfd.columns:
                dfd.rename(columns={"name": "deviceName"}, inplace=True)
                display_columns.append("deviceName")
            
            if "serialNumber" in dfd.columns:
                display_columns.append("serialNumber")
            elif "serial_number" in dfd.columns:
                dfd.rename(columns={"serial_number": "serialNumber"}, inplace=True)
                display_columns.append("serialNumber")
            elif "serial" in dfd.columns:
                dfd.rename(columns={"serial": "serialNumber"}, inplace=True)
                display_columns.append("serialNumber")
            
            if "userPrincipalName" in dfd.columns:
                display_columns.append("userPrincipalName")
            elif "user_upn" in dfd.columns:
                dfd.rename(columns={"user_upn": "userPrincipalName"}, inplace=True)
                display_columns.append("userPrincipalName")
            elif "assigned_to" in dfd.columns:
                dfd.rename(columns={"assigned_to": "userPrincipalName"}, inplace=True)
                display_columns.append("userPrincipalName")
            
            if "createdDateTime" in dfd.columns:
                dfd["createdDateTime"] = pd.to_datetime(dfd["createdDateTime"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
                display_columns.append("createdDateTime")
            elif "created_at" in dfd.columns:
                dfd["createdDateTime"] = pd.to_datetime(dfd["created_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
                display_columns.append("createdDateTime")
            
            if "model" in dfd.columns:
                display_columns.append("model")
            if "os" in dfd.columns or "operatingSystem" in dfd.columns:
                if "operatingSystem" not in dfd.columns and "os" in dfd.columns:
                    dfd.rename(columns={"os": "operatingSystem"}, inplace=True)
                display_columns.append("operatingSystem")
            
            # Add status badge
            dfd["status"] = "In Use"
            display_columns.insert(0, "status")
            
            # Show metrics
            st.markdown(f"**Total Devices:** {len(dfd)} | 🟢 **Status:** Active")
            st.markdown("---")
            
            # Configure AgGrid
            gb = GridOptionsBuilder.from_dataframe(dfd[display_columns] if display_columns else dfd)
            gb.configure_default_column(filter=True, sortable=True, resizable=True, wrapText=True, autoHeight=False)
            gb.configure_selection(selection_mode="single", use_checkbox=True)
            gb.configure_column("status", header_name="Status", width=120, cellStyle={"color": "white", "backgroundColor": "#10b981", "fontWeight": "600", "textAlign": "center"})
            if "deviceName" in display_columns:
                gb.configure_column("deviceName", header_name="Device Name", width=200, pinned="left")
            if "serialNumber" in display_columns:
                gb.configure_column("serialNumber", header_name="Serial Number", width=180)
            if "userPrincipalName" in display_columns:
                gb.configure_column("userPrincipalName", header_name="Assigned User", width=220)
            if "createdDateTime" in display_columns:
                gb.configure_column("createdDateTime", header_name="Enrolled Date", width=150)
            
            if "metadata_" in dfd.columns:
                gb.configure_column("metadata_", hide=True)
            if "id" in dfd.columns:
                gb.configure_column("id", hide=True)
            
            gb.configure_pagination(enabled=True, paginationPageSize=20)
            grid_opts = gb.build()
            
            grid = AgGrid(
                dfd[display_columns] if display_columns else dfd,
                gridOptions=grid_opts,
                enable_enterprise_modules=False,
                fit_columns_on_grid_load=True,
                theme="streamlit",
                key="devices_in_use_grid",
                height=500,
                allow_unsafe_jscode=True
            )
            
            sel_list = grid.get("selected_rows")
            if sel_list is not None and not (isinstance(sel_list, pd.DataFrame) and sel_list.empty) and len(sel_list) > 0:
                if isinstance(sel_list, pd.DataFrame):
                    st.session_state["selected_device_in_use"] = sel_list.iloc[0].to_dict()
                else:
                    st.session_state["selected_device_in_use"] = sel_list[0]
            
            row = st.session_state.get("selected_device_in_use")
            if row:
                st.markdown("---")
                st.markdown("### 📋 Device Details")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Device Name:** {row.get('deviceName', 'N/A')}")
                    st.markdown(f"**Serial Number:** {row.get('serialNumber', 'N/A')}")
                    st.markdown(f"**Model:** {row.get('model', 'N/A')}")
                with col_b:
                    st.markdown(f"**Assigned User:** {row.get('userPrincipalName', 'N/A')}")
                    st.markdown(f"**Enrolled:** {row.get('createdDateTime', 'N/A')}")
                    st.markdown(f"**OS:** {row.get('operatingSystem', 'N/A')}")
                st.info("ℹ️ This device is managed by Intune. Changes must be made through the Intune portal.")
        else:
            st.info("📭 No devices currently enrolled in Intune.")

    # ---- Devices In Stock tab ----
    with tabs[1]:
        # Header with icon
        col_header, col_refresh = st.columns([6, 1])
        with col_header:
            st.markdown("## 📦 Devices In Stock (Local Inventory)")
            st.markdown("*Local inventory - devices not yet enrolled in Intune*")
        with col_refresh:
            if st.button("🔄 Refresh", key="refresh_in_stock", use_container_width=True):
                safe_clear_cache()
                safe_rerun()
        
        # Add Device Button - Collapsible
        with st.expander("➕ Add New Device to Stock", expanded=False):
            with st.form("add_device_form"):
                st.markdown("### Add Device to Inventory")
                col_a, col_b = st.columns(2)
                with col_a:
                    device_name = st.text_input("Device Name *", placeholder="e.g., Surface Laptop 5")
                    serial_number = st.text_input("Serial Number *", placeholder="e.g., SN123456789")
                    asset_code = st.text_input("Asset Code", placeholder="e.g., AT001")
                    model = st.text_input("Model", placeholder="e.g., Surface Laptop 5")
                with col_b:
                    manufacturer = st.text_input("Manufacturer", placeholder="e.g., Microsoft")
                    device_type = st.selectbox("Device Type", ["Laptop", "Monitor", "Phone", "Tablet", "Accessory", "Other"])
                    os_type = st.selectbox("Operating System", ["Windows 11", "Windows 10", "macOS", "Linux", "Other"])
                    location = st.text_input("Storage Location", placeholder="e.g., Warehouse A, Shelf 3")
                
                notes = st.text_area("Notes", placeholder="Additional information...")
                actor = st.text_input("Added by", value="ui_user")
                
                col_submit, col_cancel = st.columns([1, 3])
                with col_submit:
                    submit_add = st.form_submit_button("✅ Add Device", use_container_width=True)
                
                if submit_add:
                    if not device_name or not serial_number:
                        st.error("❌ Device Name and Serial Number are required!")
                    else:
                        with st.spinner("Adding device to inventory..."):
                            # Create inventory item
                            item_payload = {
                                "sku": serial_number,
                                "name": device_name,
                                "item_type": "device",
                                "quantity": 1,
                                "location": location or "Stock",
                                "metadata_": {"notes": notes, "manufacturer": manufacturer},
                                "actor": actor,
                            }
                            # Create laptop/device record
                            laptop_payload = {
                                "serial": serial_number,
                                "asset_tag": asset_code or "",
                                "model": model or device_name,
                                "device_type": device_type,
                                "os": os_type,
                                "status": "in_stock",
                            }
                            try:
                                res = api_post_raw("/inventory/devices", {"item": item_payload, "laptop": laptop_payload, "actor": actor}, timeout=30)
                                if res and getattr(res, "status_code", None) in (200, 201):
                                    st.success(f"✅ Device '{device_name}' added successfully!")
                                    # Clear specific caches
                                    get_devices_in_stock.clear()
                                    get_inventory_items.clear()
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed to add device: {res.status_code if res else 'No response'} - {res.text if res else ''}")
                            except Exception as e:
                                st.error(f"❌ Error adding device: {str(e)}")
        
        st.markdown("---")
        
        with st.spinner("Loading stock devices..."):
            devices = get_devices_in_stock()
        
        if devices:
            dfd = pd.DataFrame(devices)
            
            # Standardize column names
            column_mapping = {
                "asset_tag": "assetCode",
            }
            for old_col, new_col in column_mapping.items():
                if old_col in dfd.columns and new_col not in dfd.columns:
                    dfd.rename(columns={old_col: new_col}, inplace=True)
            
            # Ensure assetCode exists
            if "assetCode" not in dfd.columns:
                dfd["assetCode"] = ""
            
            # Format dates
            if "updated_at" in dfd.columns:
                dfd["updated_at"] = pd.to_datetime(dfd["updated_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
            elif "created_at" in dfd.columns:
                dfd["updated_at"] = pd.to_datetime(dfd["created_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
            
            # Format device_type
            if "device_type" not in dfd.columns:
                dfd["device_type"] = "Laptop"
            
            # Add status column
            if "status" not in dfd.columns:
                dfd["status"] = "in_stock"
            
            # Show metrics
            st.markdown(f"**Total In Stock:** {len(dfd)} | 🔵 **Status:** Available")
            st.markdown("---")
            
            # Configure AgGrid with modern dark theme
            gb = GridOptionsBuilder.from_dataframe(dfd)
            
            # Default column configuration
            gb.configure_default_column(
                filter=True, 
                sortable=True, 
                resizable=True, 
                wrapText=False,
                autoHeight=False
            )
            
            # Selection with checkbox
            gb.configure_selection(
                selection_mode="single", 
                use_checkbox=True,
                header_checkbox=False,
                pre_selected_rows=[]
            )
            
            # Status column with custom renderer (blue badge for "in_stock")
            status_cell_renderer = JsCode("""
                function(params) {
                    const status = params.value;
                    if (status === 'in_stock') {
                        return '<span style="display: inline-block; padding: 4px 12px; border-radius: 12px; background-color: #3b82f6; color: white; font-weight: 600; font-size: 12px;">In Stock</span>';
                    } else if (status === 'in_use') {
                        return '<span style="display: inline-block; padding: 4px 12px; border-radius: 12px; background-color: #10b981; color: white; font-weight: 600; font-size: 12px;">In Use</span>';
                    } else if (status === 'retired') {
                        return '<span style="display: inline-block; padding: 4px 12px; border-radius: 12px; background-color: #6b7280; color: white; font-weight: 600; font-size: 12px;">Retired</span>';
                    }
                    return status;
                }
            """)
            
            gb.configure_column(
                "status", 
                header_name="Status", 
                width=130,
                cellRenderer=status_cell_renderer
            )
            
            # Asset Code column (pinned left)
            if "assetCode" in dfd.columns:
                gb.configure_column("assetCode", header_name="Asset Code", width=130, pinned="left")
            
            # Device Type
            if "device_type" in dfd.columns:
                gb.configure_column("device_type", header_name="Device Type", width=130)
            
            # Model
            if "model" in dfd.columns:
                gb.configure_column("model", header_name="Model", width=180)
            
            # Serial Number
            if "serialNumber" in dfd.columns:
                gb.configure_column("serialNumber", header_name="Serial Number", width=180)
            
            # Company
            if "company" in dfd.columns:
                gb.configure_column("company", header_name="Company", width=150)
            
            # OS
            if "os" in dfd.columns:
                gb.configure_column("os", header_name="OS", width=130)
            
            # Assigned To ID
            if "assigned_to_id" in dfd.columns:
                gb.configure_column("assigned_to_id", header_name="Assigned To ID", width=180)
            
            # Device Graph ID
            if "device_graph_id" in dfd.columns:
                gb.configure_column("device_graph_id", header_name="Device Graph ID", width=180)
            
            # Notes with tooltip
            if "notes" in dfd.columns:
                gb.configure_column(
                    "notes", 
                    header_name="Notes", 
                    width=200,
                    tooltipField="notes",
                    cellStyle={"whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"}
                )
            
            # Updated At
            if "updated_at" in dfd.columns:
                gb.configure_column("updated_at", header_name="Updated At", width=160)
            
            # Location
            if "location" in dfd.columns:
                gb.configure_column("location", header_name="Location", width=150)
            
            # Hide internal IDs
            if "metadata_" in dfd.columns:
                gb.configure_column("metadata_", hide=True)
            if "id" in dfd.columns:
                gb.configure_column("id", hide=True)
            if "item_id" in dfd.columns:
                gb.configure_column("item_id", hide=True)
            
            # Pagination
            gb.configure_pagination(
                enabled=True, 
                paginationPageSize=25,
                paginationAutoPageSize=False
            )
            
            # Grid options for better UX
            gb.configure_grid_options(
                domLayout="normal",
                rowHeight=45,
                headerHeight=48,
                animateRows=True,
                suppressMovableColumns=False
            )
            
            grid_opts = gb.build()
            
            # Render with custom CSS for dark theme
            grid = AgGrid(
                dfd,
                gridOptions=grid_opts,
                enable_enterprise_modules=False,
                fit_columns_on_grid_load=False,
                theme="streamlit",
                key="devices_in_stock_grid",
                height=600,
                allow_unsafe_jscode=True,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                custom_css={
                    ".ag-root-wrapper": {
                        "border-radius": "8px",
                        "border": "1px solid #404040"
                    },
                    ".ag-header": {
                        "background-color": "#2d2d2d",
                        "font-weight": "600"
                    },
                    ".ag-header-cell": {
                        "padding": "12px 8px"
                    },
                    ".ag-row": {
                        "border-bottom": "1px solid #333"
                    },
                    ".ag-row-hover": {
                        "background-color": "#333333 !important"
                    },
                    ".ag-cell": {
                        "display": "flex",
                        "align-items": "center",
                        "padding": "8px"
                    }
                }
            )
            
            sel_list = grid.get("selected_rows")
            if sel_list is not None and not (isinstance(sel_list, pd.DataFrame) and sel_list.empty) and len(sel_list) > 0:
                if isinstance(sel_list, pd.DataFrame):
                    st.session_state["selected_device_in_stock"] = sel_list.iloc[0].to_dict()
                else:
                    st.session_state["selected_device_in_stock"] = sel_list[0]
            
            row = st.session_state.get("selected_device_in_stock")
            if row:
                st.markdown("---")
                st.markdown("### 📋 Selected Device Actions")
                
                col_info, col_actions = st.columns([2, 1])
                
                with col_info:
                    st.markdown("#### Device Information")
                    st.markdown(f"**Device Name:** {row.get('deviceName') or row.get('name', 'N/A')}")
                    st.markdown(f"**Serial Number:** {row.get('serialNumber') or row.get('serial', 'N/A')}")
                    st.markdown(f"**Model:** {row.get('model', 'N/A')}")
                    st.markdown(f"**Location:** {row.get('location', 'N/A')}")
                    st.markdown(f"**Added:** {row.get('created_at', 'N/A')}")
                
                with col_actions:
                    st.markdown("#### Actions")
                    
                    # Edit button
                    if st.button("✏️ Edit Device", use_container_width=True):
                        st.session_state["show_edit_form"] = True
                    
                    # Delete button with confirmation
                    if st.button("🗑️ Delete Device", type="secondary", use_container_width=True):
                        st.session_state["show_delete_confirm"] = True
                
                # Edit form
                if st.session_state.get("show_edit_form"):
                    with st.form("edit_device_form"):
                        st.markdown("#### Edit Device")
                        edit_name = st.text_input("Device Name", value=row.get('deviceName') or row.get('name', ''))
                        edit_location = st.text_input("Location", value=row.get('location', ''))
                        edit_notes = st.text_area("Notes", value=row.get('metadata_', {}).get('notes', '') if isinstance(row.get('metadata_'), dict) else '')
                        
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.form_submit_button("💾 Save Changes", use_container_width=True):
                                item_id = row.get("item_id") or row.get("id")
                                if item_id:
                                    payload = {
                                        "name": edit_name,
                                        "location": edit_location,
                                        "metadata_": {"notes": edit_notes},
                                        "actor": "ui_user"
                                    }
                                    res = api_patch(f"/inventory/{int(item_id)}", payload)
                                    if res:
                                        st.success("✅ Device updated successfully!")
                                        st.session_state["show_edit_form"] = False
                                        get_devices_in_stock.clear()
                                        get_inventory_items.clear()
                                        st.rerun()
                        with col_cancel:
                            if st.form_submit_button("❌ Cancel", use_container_width=True):
                                st.session_state["show_edit_form"] = False
                                safe_rerun()
                
                # Delete confirmation
                if st.session_state.get("show_delete_confirm"):
                    st.warning("⚠️ Are you sure you want to delete this device from inventory?")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("✅ Yes, Delete", type="primary", use_container_width=True):
                            # For devices in stock, we need the laptop.id (not item_id)
                            # The Laptop table has both 'id' (laptop primary key) and 'item_id' (foreign key to InventoryItem)
                            laptop_id = row.get("id")
                            
                            if laptop_id:
                                try:
                                    st.info(f"Deleting device (laptop_id: {laptop_id})...")
                                    # Use the new device-specific delete endpoint
                                    r = requests.delete(f"{API_BASE}/inventory/devices/{int(laptop_id)}", headers=_headers())
                                    if r.ok:
                                        st.success("✅ Device deleted successfully!")
                                        st.session_state["show_delete_confirm"] = False
                                        st.session_state["selected_device_in_stock"] = None
                                        # Clear specific caches
                                        get_devices_in_stock.clear()
                                        get_inventory_items.clear()
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Delete failed: {r.status_code} - {r.text}")
                                        st.info("Debug info - Row data:")
                                        st.json(row)
                                except Exception as e:
                                    st.error(f"❌ Error deleting device: {str(e)}")
                            else:
                                st.error("❌ Cannot find device ID in selected row. Available fields: " + ", ".join(row.keys()))
                                st.json(row)
                    with col_no:
                        if st.button("❌ Cancel", use_container_width=True):
                            st.session_state["show_delete_confirm"] = False
                            safe_rerun()
                
                # Assign to user section
                st.markdown("---")
                with st.expander("👤 Assign Device to User"):
                    users = get_users()
                    with st.form("assign_form"):
                        if users:
                            users_map = {u.get("userPrincipalName"): (u.get("displayName") or u.get("userPrincipalName")) for u in users}
                            user_upn = st.selectbox("Select User", options=list(users_map.keys()), format_func=lambda k: f"{users_map[k]} ({k})")
                        else:
                            user_upn = st.text_input("User Principal Name (UPN)")
                        actor = st.text_input("Actor", value="ui_user")
                        if st.form_submit_button("✅ Assign to User", use_container_width=True):
                            item_id = row.get("item_id") or row.get("id")
                            if item_id:
                                with st.spinner("Assigning device..."):
                                    r = api_assign_device(int(item_id), user_upn, None, actor)
                                    if r and getattr(r, "status_code", None) in (200, 201):
                                        st.success("✅ Device assigned successfully!")
                                        # Clear specific caches
                                        get_devices_in_stock.clear()
                                        get_devices_in_use.clear()
                                        get_inventory_items.clear()
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Assignment failed: {getattr(r, 'status_code', '')} {getattr(r, 'text', '')}")
                            else:
                                st.error("❌ Cannot determine item ID for this device")
        else:
            st.info("📭 No devices in stock. Add your first device using the form above!")

    # ---- Items tab ----
    with tabs[2]:
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

            # show AgGrid table with nicer appearance
            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_default_column(filter=True, sortable=True, resizable=True)
            gb.configure_selection(selection_mode="single", use_checkbox=False)
            gb.configure_column("status", header_name="Status", cellRenderer="""function(params){
                if(params.value=='low'){return '<span style="color:#d97706;font-weight:600'>LOW</span>'}
                if(params.value=='out'){return '<span style="color:#d62728;font-weight:600'>OUT</span>'}
                return '<span style="color:#2ca02c;font-weight:600'>OK</span>'}""", editable=False)
            if "metadata_" in df.columns:
                gb.configure_column("metadata_", hide=True)
            gb.configure_column("created_at", header_name="Created", type=["dateColumnFilter","customDateTimeFormat"], custom_format_string="yyyy-MM-dd HH:mm")
            grid_options = gb.build()
            grid_response = AgGrid(
                df,
                gridOptions=grid_options,
                enable_enterprise_modules=False,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                fit_columns_on_grid_load=True,
                key="items_grid",
                height=420,
            )
            selected = grid_response.get("selected_rows")
            if selected is not None and not (isinstance(selected, pd.DataFrame) and selected.empty) and len(selected) > 0:
                if isinstance(selected, pd.DataFrame):
                    st.session_state["selected_item"] = selected.iloc[0].to_dict()
                else:
                    st.session_state["selected_item"] = selected[0]
            sel = st.session_state.get("selected_item")
            st.markdown("### Selected item")
            if sel:
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
                                    safe_rerun()
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
                                if r and getattr(r, "status_code", None) in (200,201):
                                    st.success("Allocated item")
                                    safe_rerun()
                                else:
                                    st.error(f"Allocate failed: {r.status_code if r else ''} {r.text if r else ''}")
                with col_delete:
                    # Use a form with explicit confirm checkbox and submit button
                    with st.form("delete_item_form"):
                        confirm = st.checkbox("Confirm delete this item?")
                        if st.form_submit_button("Delete item"):
                            if not confirm:
                                st.warning("Please confirm deletion by checking the box")
                            else:
                                try:
                                    item_id = int(sel.get("id")) if sel and sel.get("id") else None
                                    if not item_id:
                                        st.error("Cannot determine item id to delete")
                                    else:
                                        r = requests.delete(f"{API_BASE}/inventory/{item_id}", headers=_headers())
                                        if r.ok:
                                            st.success("Deleted")
                                            safe_rerun()
                                        else:
                                            st.error(f"Delete failed: {r.status_code} {r.text}")
                                except Exception as e:
                                    st.error(f"Delete request failed: {e}")
        else:
            st.info("No inventory items found. Create a new item below.")

        with st.expander("Create a new inventory item"):
            with st.form("new_item"):
                sku = st.text_input("SKU")
                name = st.text_input("Name")
                item_type = st.selectbox("Type", ["device", "accessory", "license"])
                quantity = st.number_input("Quantity", min_value=0, value=1)
                location = st.text_input("Location")
                notes = st.text_area("Notes")
                # Additional device fields when creating a device
                serial = None
                model = None
                os_field = None
                if item_type == "device":
                    serial = st.text_input("Serial number")
                    model = st.text_input("Model")
                    os_field = st.text_input("OS")

                if st.form_submit_button("Create"):
                    item_payload = {
                        "sku": sku,
                        "name": name,
                        "item_type": item_type,
                        "quantity": int(quantity),
                        "location": location,
                        "metadata_": {"notes": notes},
                        "actor": "ui_user",
                    }
                    try:
                        if item_type == "device":
                            laptop_payload = {
                                "serial": serial,
                                "model": model,
                                "os": os_field,
                                "status": "in_stock",
                            }
                            res = api_post_raw("/inventory/devices", {"item": item_payload, "laptop": laptop_payload, "actor": "ui_user"}, timeout=30)
                        else:
                            res = api_post_raw("/inventory", item_payload, timeout=30)
                    except Exception as e:
                        st.error(f"Create request failed: {e}")
                        res = None

                    if res and getattr(res, "status_code", None) in (200,201):
                        st.success("Created")
                        try:
                            safe_rerun()
                        except Exception as e:
                            st.info("Created (reload failed): %s" % e)
                    else:
                        try:
                            st.error(f"Create failed: {res.status_code} - {res.text}")
                        except Exception:
                            st.error("Create failed")

    # ---- Licenses tab ----
    with tabs[3]:
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
                sku = st.text_input("License SKU (unique)", placeholder="e.g., MS365-E3")
                display = st.text_input("Display name", placeholder="e.g., Microsoft 365 E3")
                total = st.number_input("Total count", min_value=0, value=0)
                if st.form_submit_button("Create license pool"):
                    if not sku or not display:
                        st.error("❌ SKU and Display name are required!")
                    else:
                        with st.spinner("Creating license pool..."):
                            payload = {"sku": sku, "display_name": display, "total": int(total), "actor": "ui_user"}
                            try:
                                res = api_post_raw("/inventory/licenses", payload, timeout=10)
                                if res is None:
                                    # Error already shown by api_post_raw
                                    pass
                                elif res.status_code in (200, 201):
                                    st.success("✅ License pool created successfully!")
                                    # Clear specific cache for license pools
                                    get_license_pools.clear()
                                    # Small delay to ensure DB commit completes
                                    import time
                                    time.sleep(0.1)
                                    st.rerun()
                                else:
                                    error_msg = ""
                                    try:
                                        error_detail = res.json()
                                        error_msg = error_detail.get("detail", res.text)
                                    except:
                                        error_msg = res.text
                                    st.error(f"❌ Error {res.status_code}: {error_msg}")
                            except Exception as e:
                                st.error(f"❌ Unexpected error: {str(e)}")

    # ---- Assign / Return tab ----
    with tabs[4]:
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
    with tabs[5]:
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
    with tabs[6]:
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
                    if r and getattr(r, "status_code", None) in (200,201):
                        st.success(f"Imported {r.json().get('imported', 'N/A')} records")
                        safe_rerun()
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

