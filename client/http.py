import httpx

from config import settings


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.java_base_url,
        headers={
            "Authorization": f"Bearer {settings.java_internal_token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


async def post(path: str, json_body: dict | None = None) -> dict:
    async with _client() as c:
        resp = await c.post(path, json=json_body)
        resp.raise_for_status()
        return resp.json()


async def upload_file(path: str, file_path: str, fields: dict | None = None) -> dict:
    async with _client() as c:
        c.headers.pop("Content-Type", None)  # let httpx set multipart boundary
        with open(file_path, "rb") as f:
            data = fields or {}
            data["file"] = f
            resp = await c.post(path, files={"file": f}, data=fields)
        resp.raise_for_status()
        return resp.json()
