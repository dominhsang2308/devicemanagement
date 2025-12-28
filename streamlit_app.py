# streamlit_app.py (snippet)
import streamlit as st
from device_management_dashboard import render_dashboard
from inventory_management import render_inventory_page
st.set_page_config(page_title="Devices & Inventory", layout="wide")
page = st.sidebar.radio("Menu", ["Device Dashboard", "Inventory Management", "Admin"])

if page == "Device Dashboard":
    # gọi hàm render_dashboard() bạn đã có
    render_dashboard()
elif page == "Inventory Management":
    # gọi hàm render_inventory() - chứa CRUD + assign + history
    render_inventory_page()
else:
    pass