from fastapi import APIRouter, HTTPException
from typing import List, Dict
from .ms_graph import fetch_users_cached

router = APIRouter(prefix="/api", tags=["users"])

@router.get("/users", response_model=List[Dict])
def list_users(limit: int = 200):
    """
    Return a list of users from Microsoft Graph (cached).
    Fields: id, displayName, userPrincipalName
    """
    try:
        users = fetch_users_cached(ttl_seconds=60)
        if limit:
            return users[:limit]
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))