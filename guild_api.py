import json
import os
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Preferred current Nexon Open API host first, legacy host second.
DEFAULT_BASE_URLS = [
    "https://open.api.nexon.com/maplestory/v1",
    "https://openapi.nexon.com/maplestory/v1",
]


class GuildAPIError(RuntimeError):
    pass


def _get_base_urls() -> list[str]:
    custom = os.environ.get("NEXON_OPENAPI_BASE_URL", "").strip()
    if custom:
        return [custom.rstrip("/")]
    return DEFAULT_BASE_URLS


def _get_json(path: str, api_key: str, params: Optional[dict] = None) -> dict:
    query = f"?{urlencode(params)}" if params else ""
    last_error: Exception | None = None
    tried: list[str] = []

    for base_url in _get_base_urls():
        url = f"{base_url}{path}{query}"
        tried.append(url)
        req = Request(url, headers={"x-nxopen-api-key": api_key}, method="GET")
        try:
            with urlopen(req, timeout=15) as resp:
                payload = resp.read().decode("utf-8")
                return json.loads(payload)
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="ignore")[:300]
            except Exception:
                pass
            last_error = GuildAPIError(
                f"Nexon API 호출 실패: HTTP {exc.code} ({path}) "
                f"params={params or {}} body={body or '<empty>'}"
            )
            # 404/308 등은 호스트 호환성 문제일 수 있어 다음 base_url도 시도.
            continue
        except URLError as exc:
            last_error = GuildAPIError(f"Nexon API 네트워크 오류: {exc.reason} ({path})")
            continue
        except Exception as exc:
            last_error = GuildAPIError(f"Nexon API 호출 실패: {exc} ({path})")
            continue

    raise GuildAPIError(f"{last_error} | tried={tried}")


def fetch_guild_id(api_key: str, world_name: str, guild_name: str) -> str:
    data = _get_json(
        "/guild/id/",
        api_key,
        {"world_name": world_name, "guild_name": guild_name},
    )
    guild_id = data.get("oguild_id")
    if not guild_id:
        raise GuildAPIError(
            "oguild_id를 찾지 못했습니다. 서버명/길드명을 확인하세요. "
            f"(world_name={world_name}, guild_name={guild_name})"
        )
    return guild_id


def fetch_guild_members(
    api_key: str,
    world_name: str,
    guild_name: str,
    date: Optional[str] = None,
) -> List[str]:
    guild_id = fetch_guild_id(api_key, world_name, guild_name)
    params = {"oguild_id": guild_id}
    if date:
        params["date"] = date

    data = _get_json("/guild/basic/", api_key, params)
    members = data.get("guild_member") or data.get("guild_member_name") or []
    if not isinstance(members, list):
        raise GuildAPIError(
            "길드원 목록 형식이 예상과 다릅니다. "
            "응답의 guild_member/guild_member_name 필드를 확인하세요."
        )
    return [m.strip() for m in members if isinstance(m, str) and m.strip()]
