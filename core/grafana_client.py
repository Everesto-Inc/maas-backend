"""Grafana HTTP API wrapper."""
import re
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
        login_to_use = username  # track actual login for org membership
        async with s.post(f"{BASE}/api/admin/users", json={
            "name": username, "login": username, "password": password, "email": email,
        }) as r:
            if r.status == 412:
                # 412 = login or email already taken — look up by email first, then username
                async with s.get(f"{BASE}/api/users/lookup?loginOrEmail={email}") as r2:
                    if r2.status == 200:
                        user_data = await r2.json()
                        user_id = user_data["id"]
                        login_to_use = user_data["login"]
                    else:
                        async with s.get(f"{BASE}/api/users/lookup?loginOrEmail={username}") as r3:
                            r3.raise_for_status()
                            user_data = await r3.json()
                            user_id = user_data["id"]
                            login_to_use = user_data["login"]
            else:
                r.raise_for_status()
                user_id = (await r.json())["id"]

        # Add to org — 409 means already a member, that's fine
        async with s.post(f"{BASE}/api/orgs/{org_id}/users", json={
            "loginOrEmail": login_to_use, "role": "Viewer",
        }) as r:
            if r.status not in (200, 409):
                r.raise_for_status()

        # Remove from Org 1 — Grafana auto-adds all new users to the default org,
        # which would let clients see the platform org via the org switcher.
        async with s.delete(f"{BASE}/api/orgs/1/users/{user_id}") as r:
            pass  # ignore errors — user may not be in Org 1

    return user_id, login_to_use


async def ensure_prometheus_datasource(org_id: int, client_slug: str):
    """Create the Prometheus datasource in the org if it doesn't exist.
    customQueryParameters filters label/series endpoints to client's data only,
    preventing clients from seeing other clients' or platform metrics in dropdowns."""
    headers = {"X-Grafana-Org-Id": str(org_id)}
    async with aiohttp.ClientSession(auth=AUTH, headers=headers) as s:
        async with s.get(f"{BASE}/api/datasources/name/Prometheus") as r:
            if r.status == 200:
                return  # already exists

        async with s.post(f"{BASE}/api/datasources", json={
            "name": "Prometheus",
            "type": "prometheus",
            "url": settings.GRAFANA_PROMETHEUS_URL,
            "access": "proxy",
            "isDefault": True,
            "jsonData": {
                "customQueryParameters": f'match[]={{client="{client_slug}"}}',
            },
        }) as r:
            r.raise_for_status()


def _inject_client_label(expr: str, client_slug: str) -> str:
    """Add client="{slug}" to every PromQL metric selector in expr."""
    if not expr or f'client="{client_slug}"' in expr:
        return expr
    # Add label to existing selectors that don't already have client=
    result = re.sub(r'\{(?!client=)', '{' + f'client="{client_slug}",', expr)
    return result


def _patch_panels(panels: list, client_slug: str) -> None:
    """Recursively inject client label into all panel target expressions."""
    for panel in panels:
        if panel.get("type") == "row":
            _patch_panels(panel.get("panels", []), client_slug)
        for target in panel.get("targets", []):
            if target.get("expr"):
                target["expr"] = _inject_client_label(target["expr"], client_slug)


def _patch_dashboard_variables(dashboard_json: dict, client_slug: str) -> dict:
    """Inject client label filter into variable queries and all panel expressions."""
    # Patch template variable queries (dropdowns)
    for t in dashboard_json.get("templating", {}).get("list", []):
        q = t.get("query", "")
        expr = q.get("query", "") if isinstance(q, dict) else q
        expr = expr.replace(
            "node_uname_info{",
            f'node_uname_info{{client="{client_slug}",',
        ).replace(
            "node_uname_info,",
            f'node_uname_info{{client="{client_slug}"}},',
        )
        if isinstance(q, dict):
            q["query"] = expr
            t["query"] = q
        else:
            t["query"] = expr

    # Patch all panel expressions so actual data is scoped to this client
    _patch_panels(dashboard_json.get("panels", []), client_slug)

    return dashboard_json


async def provision_laptop_dashboard(org_id: int, client_slug: str) -> dict:
    """Import Node Exporter Full as 'My Laptop' dashboard into the org."""
    async with aiohttp.ClientSession() as s:
        async with s.get(
            "https://grafana.com/api/dashboards/1860/revisions/latest/download"
        ) as r:
            r.raise_for_status()
            dashboard_json = await r.json(content_type=None)

    dashboard_json["title"] = "My Laptop"
    _patch_dashboard_variables(dashboard_json, client_slug)

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


async def provision_dashboard(org_id: int, dashboard_id: int, client_slug: str) -> dict:
    """Import a pre-built dashboard into the org, scoped to client_slug. Returns uid and url."""
    # Grafana 11 import API requires full JSON — fetch it from grafana.com first
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"https://grafana.com/api/dashboards/{dashboard_id}/revisions/latest/download"
        ) as r:
            r.raise_for_status()
            dashboard_json = await r.json(content_type=None)

    _patch_dashboard_variables(dashboard_json, client_slug)

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
