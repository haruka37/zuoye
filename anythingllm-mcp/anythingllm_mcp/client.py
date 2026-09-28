import httpx


class AnythingLLM:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._slug: str | None = None

    def workspace_slug(self) -> str:
        if self._slug is None:
            r = httpx.get(
                f"{self.base_url}/api/v1/workspaces", headers=self._headers, timeout=30
            )
            r.raise_for_status()
            workspaces = r.json()
            if isinstance(workspaces, dict):
                workspaces = workspaces.get("workspaces", [])
            if len(workspaces) != 1:
                raise RuntimeError(f"期望恰好 1 个工作区,实际有 {len(workspaces)} 个")
            self._slug = workspaces[0]["slug"]
        return self._slug

    def chat(self, message: str, mode: str = "query") -> dict:
        r = httpx.post(
            f"{self.base_url}/api/v1/workspace/{self.workspace_slug()}/chat",
            headers=self._headers,
            json={"message": message, "mode": mode},
            timeout=180,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        return data