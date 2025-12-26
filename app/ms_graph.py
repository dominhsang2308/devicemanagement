# If you already have ms_graph.py, merge the fetch_users_cached and get_access_token functions.
import os
import msal
import requests
from dotenv import load_dotenv
from typing import List, Dict
from functools import lru_cache
import time

load_dotenv()

TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
SCOPE = [os.getenv("GRAPH_SCOPE", "https://graph.microsoft.com/.default")]
GRAPH_API = os.getenv("GRAPH_API", "https://graph.microsoft.com/v1.0")

def get_access_token() -> str:
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"Unable to acquire token: {result}")
    return result["access_token"]

def fetch_managed_devices() -> List[Dict]:
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_API}/deviceManagement/managedDevices"
    devices = []
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        devices.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")
    return devices

# Cached users fetch
def _fetch_users_from_graph() -> List[Dict]:
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_API}/users?$select=id,displayName,userPrincipalName&$top=999"
    users = []
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        users.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")
    simplified = [{"id": u.get("id"), "displayName": u.get("displayName"), "userPrincipalName": u.get("userPrincipalName")} for u in users]
    return simplified

# very small in-process TTL cache
@lru_cache(maxsize=1)
def fetch_users_cached(ttl_seconds: int = 60) -> List[Dict]:
    """
    Returns cached users. Call with fetch_users_cached() to get list.
    If TTL expired, refresh cache.
    NOTE: lru_cache doesn't support TTL directly, so we maintain timestamps on function attr.
    """
    now = int(time.time())
    if not hasattr(fetch_users_cached, "_cached_at"):
        fetch_users_cached._cached_at = 0
        fetch_users_cached._cached_result = []
    if now - fetch_users_cached._cached_at < ttl_seconds and fetch_users_cached._cached_result:
        return fetch_users_cached._cached_result
    result = _fetch_users_from_graph()
    fetch_users_cached._cached_result = result
    fetch_users_cached._cached_at = now
    return result