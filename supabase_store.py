import os
from typing import MutableMapping

from supabase import Client, create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


class SupabaseNotConfigured(RuntimeError):
    pass


def _client() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise SupabaseNotConfigured(
            "SUPABASE_URL / SUPABASE_ANON_KEY 환경변수가 필요합니다."
        )
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def sign_up(email: str, password: str, display_name: str = ""):
    client = _client()
    return client.auth.sign_up(
        {
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "display_name": display_name,
                }
            },
        }
    )


def sign_in(email: str, password: str):
    client = _client()
    return client.auth.sign_in_with_password(
        {
            "email": email,
            "password": password,
        }
    )


def _authenticated_client(session_store: MutableMapping):
    access_token = session_store.get("access_token")
    refresh_token = session_store.get("refresh_token")

    if not access_token or not refresh_token:
        raise RuntimeError("로그인이 필요합니다.")

    client = _client()

    # Supabase set_session refreshes an expired access token when needed.
    response = client.auth.set_session(access_token, refresh_token)

    if response.session:
        session_store["access_token"] = response.session.access_token
        session_store["refresh_token"] = response.session.refresh_token

    return client


def get_user(session_store: MutableMapping):
    client = _authenticated_client(session_store)
    response = client.auth.get_user()

    if response.user:
        session_store["user_id"] = str(response.user.id)
        session_store["email"] = response.user.email or ""

    return response.user


def get_profile(session_store: MutableMapping):
    client = _authenticated_client(session_store)
    response = (
        client.table("profiles")
        .select("user_id, display_name, created_at")
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def load_watchlist(session_store: MutableMapping):
    client = _authenticated_client(session_store)

    response = (
        client.table("watchlist")
        .select("id, symbol, name, market, exchange, created_at")
        .order("created_at", desc=False)
        .execute()
    )
    return response.data or []


def add_watchlist(session_store: MutableMapping, item: dict):
    client = _authenticated_client(session_store)
    user = client.auth.get_user().user

    if not user:
        raise RuntimeError("사용자 정보를 확인할 수 없습니다.")

    existing = (
        client.table("watchlist")
        .select("id, symbol, name, market, exchange, created_at")
        .eq("market", item["market"])
        .eq("exchange", item["exchange"])
        .eq("symbol", item["symbol"])
        .limit(1)
        .execute()
    )

    if existing.data:
        return existing.data[0]

    response = (
        client.table("watchlist")
        .insert(
            {
                "user_id": str(user.id),
                "symbol": item["symbol"],
                "name": item["name"],
                "market": item["market"],
                "exchange": item["exchange"],
            }
        )
        .execute()
    )

    return response.data[0] if response.data else item


def delete_watchlist(
    session_store: MutableMapping,
    market: str,
    exchange: str,
    symbol: str,
):
    client = _authenticated_client(session_store)

    return (
        client.table("watchlist")
        .delete()
        .eq("market", market)
        .eq("exchange", exchange)
        .eq("symbol", symbol)
        .execute()
    )


def sign_out(session_store: MutableMapping):
    try:
        client = _authenticated_client(session_store)
        client.auth.sign_out()
    finally:
        for key in [
            "access_token",
            "refresh_token",
            "user_id",
            "email",
            "display_name",
        ]:
            session_store.pop(key, None)
