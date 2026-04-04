import logging
import os
from typing import Any

import requests


logger = logging.getLogger(__name__)


class SupabaseStreamProfileSync:
    def __init__(
        self,
        *,
        url: str,
        service_key: str,
        table: str = "stream_profiles",
        scope: str = "videoBetTransit",
        timeout_seconds: int = 8,
    ):
        self.url = url.rstrip("/")
        self.service_key = service_key.strip()
        self.table = table.strip() or "stream_profiles"
        self.scope = scope.strip() or "videoBetTransit"
        self.timeout_seconds = max(2, int(timeout_seconds))
        self._session = requests.Session()

    @classmethod
    def from_config(cls, cfg: dict):
        url = str(os.environ.get("SUPABASE_URL") or cfg.get("supabase_url") or "").strip()
        service_key = str(
            os.environ.get("SUPABASE_SERVICE_KEY")
            or cfg.get("supabase_service_key")
            or ""
        ).strip()
        if not url or not service_key:
            return None

        return cls(
            url=url,
            service_key=service_key,
            table=str(
                os.environ.get("SUPABASE_STREAM_PROFILES_TABLE")
                or cfg.get("supabase_stream_profiles_table")
                or "stream_profiles"
            ).strip(),
            scope=str(
                os.environ.get("SUPABASE_STREAM_PROFILES_SCOPE")
                or cfg.get("supabase_stream_profiles_scope")
                or "videoBetTransit"
            ).strip(),
            timeout_seconds=int(
                os.environ.get("SUPABASE_TIMEOUT_SECONDS")
                or cfg.get("supabase_timeout_seconds")
                or 8
            ),
        )

    def fetch_profiles(self) -> tuple[list[dict], str | None]:
        response = self._session.get(
            self._table_url(),
            headers=self._headers(),
            params={
                "select": "id,name,stream_url,camera_id,roi,line,count_direction,is_selected,updated_at",
                "scope": f"eq.{self.scope}",
                "order": "updated_at.desc.nullslast,id.asc",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()

        profiles: list[dict] = []
        selected_profile_id = None
        for row in rows:
            profile = {
                "id": str(row.get("id") or "").strip(),
                "name": str(row.get("name") or "").strip(),
                "stream_url": str(row.get("stream_url") or "").strip(),
                "camera_id": str(row.get("camera_id") or "").strip(),
                "roi": row.get("roi") if isinstance(row.get("roi"), dict) else {},
                "line": row.get("line") if isinstance(row.get("line"), dict) else {},
                "count_direction": str(row.get("count_direction") or "any").strip(),
            }
            if not profile["id"] or not profile["stream_url"]:
                continue

            profiles.append(profile)
            if bool(row.get("is_selected")):
                selected_profile_id = profile["id"]

        return profiles, selected_profile_id

    def upsert_profiles(self, profiles: list[dict], selected_profile_id: str | None) -> None:
        payload: list[dict[str, Any]] = []
        selected_profile_id = str(selected_profile_id or "").strip()

        for profile in profiles:
            profile_id = str(profile.get("id") or "").strip()
            stream_url = str(profile.get("stream_url") or "").strip()
            if not profile_id or not stream_url:
                continue

            payload.append(
                {
                    "scope": self.scope,
                    "id": profile_id,
                    "name": str(profile.get("name") or "").strip(),
                    "stream_url": stream_url,
                    "camera_id": str(profile.get("camera_id") or "").strip(),
                    "roi": profile.get("roi") if isinstance(profile.get("roi"), dict) else {},
                    "line": profile.get("line") if isinstance(profile.get("line"), dict) else {},
                    "count_direction": str(profile.get("count_direction") or "any").strip(),
                    "is_selected": profile_id == selected_profile_id,
                }
            )

        if not payload:
            return

        response = self._session.post(
            self._table_url(),
            headers=self._headers(
                {
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                }
            ),
            params={"on_conflict": "scope,id"},
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def _table_url(self) -> str:
        return f"{self.url}/rest/v1/{self.table}"

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
        }
        if extra:
            headers.update(extra)
        return headers

