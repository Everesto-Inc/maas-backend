"""Grafana HTTP API wrapper."""
import aiohttp
from config import settings

BASE = settings.GRAFANA_URL
AUTH = aiohttp.BasicAuth(settings.GRAFANA_ADMIN_USER, settings.GRAFANA_ADMIN_PASSWORD)


async def create_org(name: str) -> int:
    async with aiohttp.ClientSession(auth=AUTH) as s:
        async with s.post(f"{BASE}/api/orgs", json={"name": name}) as r:
            if r.status == 409:
                # Org already exists — look it up by name
                async with s.get(f"{BASE}/api/orgs/name/{name}") as r2:
                    r2.raise_for_status()
                    data = await r2.json()
                    return data["id"]
            r.raise_for_status()
            data = await r.json()
            return data["orgId"]


async def create_org_user(org_id: int, username: str, password: str, email: str):
    async with aiohttp.ClientSession(auth=AUTH) as s:
        # Create global user — handle 412 if user already exists
        async with s.post(f"{BASE}/api/admin/users", json={
            "name": username, "login": username, "password": password, "email": email,
        }) as r:
            if r.status == 412:
                # 412 = login or email already taken — look up by email first, then username
                async with s.get(f"{BASE}/api/users/lookup?loginOrEmail={email}") as r2:
                    if r2.status == 200:
                        user_id = (await r2.json())["id"]
                    else:
                        async with s.get(f"{BASE}/api/users/lookup?loginOrEmail={username}") as r3:
                            r3.raise_for_status()
                            user_id = (await r3.json())["id"]
            else:
                r.raise_for_status()
                user_id = (await r.json())["id"]

        # Add to org — 409 means already a member, that's fine
        async with s.post(f"{BASE}/api/orgs/{org_id}/users", json={
            "loginOrEmail": username, "role": "Viewer",
        }) as r:
            if r.status not in (200, 409):
                r.raise_for_status()

    return user_id


async def ensure_prometheus_datasource(org_id: int):
    """Create the Prometheus datasource in the org if it doesn't exist."""
    headers = {"X-Grafana-Org-Id": str(org_id)}
    async with aiohttp.ClientSession(auth=AUTH, headers=headers) as s:
        async with s.get(f"{BASE}/api/datasources/name/Prometheus") as r:
            if r.status == 200:
                return  # already exists

        async with s.post(f"{BASE}/api/datasources", json={
            "name": "Prometheus",
            "type": "prometheus",
            "url": settings.PROMETHEUS_URL,
            "access": "proxy",
            "isDefault": True,
        }) as r:
            r.raise_for_status()


async def provision_laptop_dashboard(org_id: int) -> dict:
    """Import Node Exporter Full as 'My Laptop' dashboard into the org."""
    async with aiohttp.ClientSession() as s:
        async with s.get(
            "https://grafana.com/api/dashboards/1860/revisions/latest/download"
        ) as r:
            r.raise_for_status()
            dashboard_json = await r.json(content_type=None)

    dashboard_json["title"] = "My Laptop"

    headers = {"X-Grafana-Org-Id": str(org_id)}
    async with aiohttp.ClientSession(auth=AUTH, headers=headers) as s:
        async with s.post(f"{BASE}/api/dashboards/import", json={
            "dashboard": dashboard_json,
            "overwrite": True,
            "inputs": [{"name": "DS_PROMETHEUS", "type": "datasource",
                        "pluginId": "prometheus", "value": "Prometheus"}],
            "folderId": 0,
            "orgId": org_id,
        }) as r:
            r.raise_for_status()
            data = await r.json()
            return {"uid": data["uid"], "url": data["importedUrl"]}


async def provision_dashboard(org_id: int, dashboard_id: int) -> dict:
    """Import a pre-built dashboard into the org. Returns uid and url."""
    # Grafana 11 import API requires full JSON — fetch it from grafana.com first
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"https://grafana.com/api/dashboards/{dashboard_id}/revisions/latest/download"
        ) as r:
            r.raise_for_status()
            dashboard_json = await r.json(content_type=None)

    headers = {"X-Grafana-Org-Id": str(org_id)}
    async with aiohttp.ClientSession(auth=AUTH, headers=headers) as s:
        async with s.post(f"{BASE}/api/dashboards/import", json={
            "dashboard": dashboard_json,
            "overwrite": True,
            "inputs": [{"name": "DS_PROMETHEUS", "type": "datasource",
                        "pluginId": "prometheus", "value": "Prometheus"}],
            "folderId": 0,
            "orgId": org_id,
        }) as r:
            r.raise_for_status()
            data = await r.json()
            return {"uid": data["uid"], "url": data["importedUrl"]}


def generate_dashboard_url(org_id: int, dashboard_uid: str) -> str:
    """Return the Grafana dashboard URL for the client's org."""
    return f"{settings.GRAFANA_PUBLIC_URL}/d/{dashboard_uid}?orgId={org_id}"


async def update_user_password(username: str, new_password: str):
    """Update a Grafana user's password via the admin API."""
    async with aiohttp.ClientSession(auth=AUTH) as s:
        async with s.get(f"{BASE}/api/users/lookup?loginOrEmail={username}") as r:
            r.raise_for_status()
            user_id = (await r.json())["id"]
        async with s.put(f"{BASE}/api/admin/users/{user_id}/password",
                         json={"password": new_password}) as r:
            r.raise_for_status()


async def delete_org(org_id: int):
    async with aiohttp.ClientSession(auth=AUTH) as s:
        async with s.delete(f"{BASE}/api/orgs/{org_id}") as r:
            r.raise_for_status()
