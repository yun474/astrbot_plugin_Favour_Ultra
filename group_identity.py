from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GroupMemorySpace:
    id: str
    name: str = ""
    session_id: str = ""
    kind: str = "group"
    owner_user_id: str = ""
    owner_display_name: str = ""
    owner_evidence: str = ""
    owner_updated_at: int = 0
    member_directory_updated_at: int = 0
    member_directory_source: str = ""
    member_count: int = 0
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    message_count: int = 0


@dataclass
class GroupMember:
    id: str
    group_id: str
    user_id: str
    display_name: str = ""
    card: str = ""
    nickname: str = ""
    recall_name_preference: str = ""
    role: str = "member"
    source: str = "event"
    active: bool = True
    first_seen_at: int = field(default_factory=lambda: int(time.time()))
    last_seen_at: int = field(default_factory=lambda: int(time.time()))
    verified_at: int = field(default_factory=lambda: int(time.time()))


def normalize_text(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_role(value: str) -> str:
    role = normalize_text(value)
    if role in {"owner", "群主", "super_admin", "superadmin"}:
        return "owner"
    if role in {"admin", "administrator", "管理员", "manage", "manager"}:
        return "admin"
    if role in {"member", "manber", "群友", "成员", "user", "normal"}:
        return "member"
    return role or "member"


def role_rank(role: str) -> int:
    return {"unknown": 0, "member": 1, "admin": 2, "owner": 3}.get(normalize_role(role), 0)


def member_id(group_id: str, user_id: str) -> str:
    return f"{normalize_text(group_id)}:{normalize_text(user_id)}"


class GroupIdentityStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_file = self.data_dir / "group_identity.json"
        self.groups: dict[str, GroupMemorySpace] = {}
        self.members: dict[str, GroupMember] = {}

    def load(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            self.save()
            return
        try:
            payload = json.loads(self.data_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.groups = {}
            self.members = {}
            return

        self.groups = {}
        for item in payload.get("groups", []):
            group = self._coerce_group(item)
            if group:
                self.groups[group.id] = group

        self.members = {}
        for item in payload.get("members", []):
            member = self._coerce_member(item)
            if member:
                self.members[member.id] = member

        self._ensure_groups()
        self._refresh_group_counts()

    def save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "groups": [asdict(group) for group in self.groups.values()],
            "members": [asdict(member) for member in self.members.values()],
        }
        tmp_file = self.data_file.with_suffix(".json.tmp")
        tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_file, self.data_file)

    def _coerce_group(self, item: Any) -> GroupMemorySpace | None:
        if not isinstance(item, dict):
            return None
        group_id = str(item.get("id") or item.get("group_id") or "").strip()
        if not group_id:
            return None
        payload = {field_name: item.get(field_name) for field_name in GroupMemorySpace.__dataclass_fields__}
        payload["id"] = group_id
        payload["name"] = str(payload.get("name") or group_id)
        payload["session_id"] = str(payload.get("session_id") or group_id)
        payload["kind"] = str(payload.get("kind") or "group")
        for key in ("owner_updated_at", "member_directory_updated_at", "member_count", "created_at", "updated_at", "message_count"):
            payload[key] = int(payload.get(key) or 0)
        return GroupMemorySpace(**payload)

    def _coerce_member(self, item: Any) -> GroupMember | None:
        if not isinstance(item, dict):
            return None
        group_id = str(item.get("group_id") or "").strip()
        user_id = str(item.get("user_id") or "").strip()
        if not group_id or not user_id:
            return None
        payload = {field_name: item.get(field_name) for field_name in GroupMember.__dataclass_fields__}
        payload["id"] = str(payload.get("id") or member_id(group_id, user_id))
        payload["group_id"] = group_id
        payload["user_id"] = user_id
        payload["role"] = normalize_role(payload.get("role") or "member")
        payload["active"] = bool(payload.get("active", True))
        for key in ("first_seen_at", "last_seen_at", "verified_at"):
            payload[key] = int(payload.get(key) or int(time.time()))
        return GroupMember(**payload)

    def _ensure_groups(self) -> None:
        for member in self.members.values():
            if member.group_id and member.group_id not in self.groups:
                self.groups[member.group_id] = GroupMemorySpace(
                    id=member.group_id,
                    name=member.group_id,
                    session_id=member.group_id,
                    kind="group",
                )

    def _refresh_group_counts(self) -> None:
        for group in self.groups.values():
            group.member_count = len(
                [member for member in self.members.values() if member.group_id == group.id and member.active]
            )

    def touch_group(self, group_id: str, name: str = "", session_id: str = "", kind: str = "group") -> GroupMemorySpace:
        now = int(time.time())
        group_id = str(group_id or "").strip()
        group = self.groups.get(group_id)
        if not group:
            group = GroupMemorySpace(
                id=group_id,
                name=name.strip() or group_id,
                session_id=session_id.strip() or group_id,
                kind=kind.strip() or "group",
                created_at=now,
                updated_at=now,
            )
            self.groups[group_id] = group
        else:
            if name:
                group.name = name.strip()
            if session_id:
                group.session_id = session_id.strip()
            if kind:
                group.kind = kind.strip()
            group.updated_at = now
        group.message_count += 1
        self.save()
        return group

    def set_group_owner(self, group_id: str, user_id: str, display_name: str = "", evidence: str = "") -> GroupMemorySpace | None:
        group = self.groups.get(str(group_id or "").strip())
        if not group:
            return None
        group.owner_user_id = str(user_id or "").strip()
        group.owner_display_name = str(display_name or "").strip()
        group.owner_evidence = str(evidence or "").strip()
        group.owner_updated_at = int(time.time()) if group.owner_user_id else 0
        group.updated_at = int(time.time())
        self.save()
        return group

    def get_member(self, group_id: str, user_id: str) -> GroupMember | None:
        return self.members.get(member_id(group_id, user_id))

    def upsert_group_member(
        self,
        group_id: str,
        user_id: str,
        display_name: str = "",
        card: str = "",
        nickname: str = "",
        role: str = "member",
        source: str = "event",
        active: bool = True,
        save: bool = True,
    ) -> GroupMember:
        group_id = str(group_id or "").strip()
        user_id = str(user_id or "").strip()
        now = int(time.time())
        mid = member_id(group_id, user_id)
        role = normalize_role(role)
        member = self.members.get(mid)
        if not member:
            member = GroupMember(
                id=mid,
                group_id=group_id,
                user_id=user_id,
                display_name=str(display_name or user_id).strip(),
                card=str(card or "").strip(),
                nickname=str(nickname or "").strip(),
                role=role,
                source=str(source or "event").strip(),
                active=active,
                first_seen_at=now,
                last_seen_at=now,
                verified_at=now,
            )
            self.members[mid] = member
        else:
            member.display_name = str(display_name or member.display_name or user_id).strip()
            member.card = str(card or member.card or "").strip()
            member.nickname = str(nickname or member.nickname or "").strip()
            manual_sources = {"webui", "manual", "debug_command"}
            authoritative_sources = {"platform"}
            manual_role_locked = (
                member.source in manual_sources
                and source not in manual_sources
                and source not in authoritative_sources
            )
            if source in authoritative_sources or (role_rank(role) >= role_rank(member.role) and not manual_role_locked):
                member.role = role
            if not manual_role_locked or source in manual_sources:
                member.source = str(source or member.source or "event").strip()
            member.active = active
            member.last_seen_at = now
            member.verified_at = now
        if group_id not in self.groups:
            self.groups[group_id] = GroupMemorySpace(id=group_id, name=group_id, session_id=group_id, kind="group")
        self._refresh_group_counts()
        if save:
            self.save()
        return member

    def replace_group_members(self, group_id: str, members: list[dict[str, Any]], source: str = "platform") -> None:
        group_id = str(group_id or "").strip()
        seen: set[str] = set()
        for item in members:
            user_id = str(item.get("user_id") or "").strip()
            if not user_id:
                continue
            seen.add(user_id)
            self.upsert_group_member(
                group_id=group_id,
                user_id=user_id,
                display_name=str(item.get("display_name") or item.get("nickname") or item.get("card") or user_id),
                card=str(item.get("card") or item.get("group_card") or ""),
                nickname=str(item.get("nickname") or item.get("name") or ""),
                role=str(item.get("role") or "member"),
                source=source,
                active=True,
                save=False,
            )
        now = int(time.time())
        for member in self.members.values():
            if member.group_id == group_id and member.user_id not in seen:
                member.active = False
        group = self.groups.get(group_id)
        if group:
            group.member_directory_updated_at = now
            group.member_directory_source = source
            group.member_count = len(seen)
            group.updated_at = now
        self.save()

    def update_group_member_role(self, group_id: str, user_id: str, role: str, source: str = "manual") -> GroupMember | None:
        member = self.get_member(group_id, user_id)
        if not member:
            return None
        member.role = normalize_role(role)
        member.source = source
        member.verified_at = int(time.time())
        self.save()
        return member

    def refresh_member_directory_metadata(self, group_id: str, source: str = "event_fallback") -> None:
        group = self.groups.get(group_id)
        if not group:
            return
        group.member_directory_updated_at = int(time.time())
        group.member_directory_source = source
        group.member_count = len([member for member in self.members.values() if member.group_id == group_id and member.active])
        group.updated_at = int(time.time())
        self.save()
