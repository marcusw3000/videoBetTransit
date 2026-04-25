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
        schedule_table: str = "stream_schedule_rules",
        scope: str = "videoBetTransit",
        timeout_seconds: int = 8,
    ):
        self.url = url.rstrip("/")
        self.service_key = service_key.strip()
        self.table = table.strip() or "stream_profiles"
        self.schedule_table = schedule_table.strip() or "stream_schedule_rules"
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
            schedule_table=str(
                os.environ.get("SUPABASE_STREAM_SCHEDULE_TABLE")
                or cfg.get("supabase_stream_schedule_table")
                or "stream_schedule_rules"
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
            self._table_url(self.table),
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

        if payload:
            response = self._session.post(
                self._table_url(self.table),
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

        self._delete_missing_rows(self.table, [item["id"] for item in payload])

    def fetch_schedule_rules(self) -> tuple[list[dict], str | None]:
        response = self._session.get(
            self._table_url(self.schedule_table),
            headers=self._headers(),
            params={
                "select": "id,name,enabled,start_time,end_time,allowed_profile_ids,timezone,updated_at",
                "scope": f"eq.{self.scope}",
                "order": "updated_at.desc.nullslast,id.asc",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()

        rules: list[dict] = []
        timezone_name = None
        for row in rows:
            rule_id = str(row.get("id") or "").strip()
            start_time = str(row.get("start_time") or "").strip()
            end_time = str(row.get("end_time") or "").strip()
            allowed_ids = row.get("allowed_profile_ids")
            if not isinstance(allowed_ids, list):
                allowed_ids = []
            if not rule_id or not start_time or not end_time:
                continue
            rules.append(
                {
                    "id": rule_id,
                    "name": str(row.get("name") or "").strip(),
                    "enabled": bool(row.get("enabled", True)),
                    "start_time": start_time,
                    "end_time": end_time,
                    "allowed_profile_ids": [str(value).strip() for value in allowed_ids if str(value).strip()],
                }
            )
            if timezone_name is None:
                timezone_name = str(row.get("timezone") or "").strip() or None

        return rules, timezone_name

    def upsert_schedule_rules(self, rules: list[dict], timezone_name: str | None) -> None:
        payload: list[dict[str, Any]] = []
        normalized_timezone = str(timezone_name or "").strip() or "America/Sao_Paulo"

        for rule in rules:
            rule_id = str(rule.get("id") or "").strip()
            start_time = str(rule.get("start_time") or "").strip()
            end_time = str(rule.get("end_time") or "").strip()
            if not rule_id or not start_time or not end_time:
                continue

            allowed_ids = [
                str(value).strip()
                for value in (rule.get("allowed_profile_ids") or [])
                if str(value).strip()
            ]
            payload.append(
                {
                    "scope": self.scope,
                    "id": rule_id,
                    "name": str(rule.get("name") or "").strip(),
                    "enabled": bool(rule.get("enabled", True)),
                    "start_time": start_time,
                    "end_time": end_time,
                    "allowed_profile_ids": allowed_ids,
                    "timezone": normalized_timezone,
                }
            )

        if payload:
            response = self._session.post(
                self._table_url(self.schedule_table),
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

        self._delete_missing_rows(self.schedule_table, [item["id"] for item in payload])

    def _table_url(self, table_name: str) -> str:
        return f"{self.url}/rest/v1/{table_name}"

    def _delete_missing_rows(self, table_name: str, retained_ids: list[str]) -> None:
        params = {"scope": f"eq.{self.scope}"}
        if retained_ids:
            escaped_ids = ",".join(str(value).replace('"', '\\"') for value in retained_ids)
            params["id"] = f"not.in.({escaped_ids})"
        response = self._session.delete(
            self._table_url(table_name),
            headers=self._headers({"Prefer": "return=minimal"}),
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
        }
        if extra:
            headers.update(extra)
        return headers
