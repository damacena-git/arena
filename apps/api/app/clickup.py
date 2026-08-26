from __future__ import annotations

import httpx
from fastapi import HTTPException

from .config import get_settings

settings = get_settings()


class ClickUpError(RuntimeError):
    """Erro quando o ClickUp não responde conforme esperado."""


class ClickUpClient:
    BASE_URL = "https://api.clickup.com/api/v2"

    def __init__(self, api_key: str, default_team_id: str | None = None) -> None:
        self.api_key = api_key
        self.default_team_id = default_team_id
        self._workspace_id = default_team_id
        self._default_list_id: str | None = None

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", self.api_key)
        headers.setdefault("Content-Type", "application/json")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(
                method, f"{self.BASE_URL}{path}", headers=headers, **kwargs
            )
        if response.status_code >= 400:
            raise ClickUpError(
                f"ClickUp retornou HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ClickUpError("Resposta inválida do ClickUp") from exc

    async def get_workspaces(self) -> list[dict]:
        data = await self._request("GET", "/team")
        return data.get("teams", [])

    async def get_folders(self, workspace_id: str) -> list[dict]:
        data = await self._request("GET", f"/team/{workspace_id}/folder")
        return data.get("folders", [])

    async def get_lists(self, workspace_id: str) -> list[dict]:
        """Retorna listas de espaços com e sem pastas do workspace.

        A API do ClickUp não possui um endpoint /team/{id}/list. As listas
        ficam abaixo de cada space ou folder.
        """
        spaces_data = await self._request("GET", f"/team/{workspace_id}/space", params={"archived": "false"})
        lists: list[dict] = []
        for space in spaces_data.get("spaces", []):
            space_id = space["id"]
            direct = await self._request("GET", f"/space/{space_id}/list", params={"archived": "false"})
            lists.extend(direct.get("lists", []))
            folders_data = await self._request("GET", f"/space/{space_id}/folder", params={"archived": "false"})
            for folder in folders_data.get("folders", []):
                folder_lists = await self._request("GET", f"/folder/{folder['id']}/list", params={"archived": "false"})
                lists.extend(folder_lists.get("lists", []))
        return lists

    async def get_members(self, workspace_id: str) -> list[dict]:
        data = await self._request("GET", f"/team/{workspace_id}/member")
        return data.get("members", [])

    async def get_lists_for_workspace(self) -> list[dict]:
        return await self.get_lists(await self.get_workspace_id())

    async def get_tasks(self, list_id: str) -> list[dict]:
        data = await self._request("GET", f"/list/{list_id}/task")
        return data.get("tasks", [])

    async def get_filtered_tasks(self, workspace_id: str, **filters: str | int | bool) -> list[dict]:
        data = await self._request("GET", f"/team/{workspace_id}/task", params=filters)
        return data.get("tasks", [])

    async def create_task(
        self,
        list_id: str,
        name: str,
        description: str | None = None,
        priority: int | None = None,
        due_dates: str | None = None,
        assignees: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        payload: dict = {"name": name}
        if description:
            payload["description"] = description
        if priority:
            payload["priority"] = priority
        if due_dates:
            payload["due_dates"] = due_dates
        if assignees:
            payload["assignees"] = [int(assignee) for assignee in assignees]
        if tags:
            payload["tags"] = tags

        return await self._request("POST", f"/list/{list_id}/task", json=payload)

    async def update_task(
        self,
        task_id: str,
        name: str | None = None,
        description: str | None = None,
        priority: int | None = None,
        due_dates: str | None = None,
        assignees: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        payload: dict = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if priority is not None:
            payload["priority"] = priority
        if due_dates is not None:
            payload["due_dates"] = due_dates
        if assignees is not None:
            payload["assignees"] = assignees
        if tags is not None:
            payload["tags"] = tags

        return await self._request("PUT", f"/task/{task_id}", json=payload)

    async def get_task(self, task_id: str) -> dict:
        return await self._request("GET", f"/task/{task_id}")

    async def delete_task(self, task_id: str) -> dict:
        return await self._request("DELETE", f"/task/{task_id}")

    async def add_comment(self, task_id: str, comment_text: str) -> dict:
        payload = {"comment_text": comment_text}
        return await self._request("POST", f"/task/{task_id}/comment", json=payload)

    async def get_workspace_id(self) -> str:
        if self._workspace_id:
            return self._workspace_id
        workspaces = await self.get_workspaces()
        if not workspaces:
            raise ClickUpError("Nenhum workspace/workspace encontrado no ClickUp.")
        self._workspace_id = workspaces[0]["id"]
        return self._workspace_id

    async def get_default_list_id(self) -> str:
        if self._default_list_id:
            return self._default_list_id
        workspace_id = await self.get_workspace_id()
        lists = await self.get_lists(workspace_id)
        if not lists:
            raise ClickUpError("Nenhuma lista encontrada no workspace padrão do ClickUp.")
        self._default_list_id = lists[0]["id"]
        return self._default_list_id


def get_clickup_client() -> ClickUpClient | None:
    if not settings.clickup_api_key:
        return None
    return ClickUpClient(
        api_key=settings.clickup_api_key,
        default_team_id=settings.clickup_default_team_id or None,
    )


def require_clickup() -> ClickUpClient:
    client = get_clickup_client()
    if not client:
        raise HTTPException(status_code=503, detail="ClickUp não está configurado.")
    return client