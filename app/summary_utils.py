from collections import Counter, defaultdict
from typing import List, Dict


def infer_owner_from_device(d: Dict) -> str:
    # Try canonical owner field first
    cand_fields = ["ownerType", "ownership", "managedDeviceOwnerType"]
    for f in cand_fields:
        v = d.get(f)
        if v:
            vv = str(v).strip().lower()
            # normalize common values
            if vv in ("company", "corporate", "companyowned", "company_owned"):
                return "company"
            if vv in ("personal", "personalowned", "personal_owned", "user"):
                return "personal"
            # catch values like "company, personal" etc
            if "company" in vv:
                return "company"
            if "personal" in vv or "user" in vv:
                return "personal"
    # fallback heuristics:
    # - if userPrincipalName exists -> likely user-associated (treat as personal)
    # - if managedDeviceOwnerType exists and indicates user -> personal
    if d.get("userPrincipalName"):
        return "personal"
    # - if device is azureAdRegistered but no user -> company
    # try common fields that might indicate corporate management
    if d.get("managementAgent") and "microsoft" in str(d.get("managementAgent")).lower():
        return "company"
    # default unknown
    return "unknown"

def summarize_devices(devices: List[Dict]) -> Dict:
    owners = Counter()
    compliance = Counter()
    os_counter = Counter()
    os_version_counter = Counter()
    for d in devices:
        owner = infer_owner_from_device(d)
        owners[owner] += 1

        state = (d.get("complianceState") or "unknown")
        compliance[state.lower()] += 1

        os_name = (d.get("operatingSystem") or "unknown").lower()
        os_counter[os_name] += 1

        os_version = (d.get("osVersion") or "unknown").lower()
        os_version_counter[f"{os_name} {os_version}"] += 1

    result = {
        "total": len(devices),
        "owners": dict(owners),
        "compliance": dict(compliance),
        "by_os": dict(os_counter),
        "by_os_version": dict(os_version_counter),
        "corporate": owners.get("company", 0),
        "personal": owners.get("personal", 0),
        "compliant": compliance.get("compliant", 0),
        "noncompliant": compliance.get("noncompliant", 0),
    }
    return result