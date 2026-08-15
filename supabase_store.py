import os
from supabase import create_client

URL = os.getenv("SUPABASE_URL", "")
KEY = (
    os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    or os.getenv("SUPABASE_ANON_KEY", "")
)


def _client():
    if not URL or not KEY:
        raise RuntimeError("Supabase 환경변수가 필요합니다.")
    return create_client(URL, KEY)


def sign_up(email, password, display_name=""):
    return _client().auth.sign_up({
        "email": email,
        "password": password,
        "options": {
            "data": {
                "display_name": display_name,
            }
        },
    })


def sign_in(email, password):
    return _client().auth.sign_in_with_password({
        "email": email,
        "password": password,
    })


def _auth(store):
    access = store.get("access_token")
    refresh = store.get("refresh_token")
    if not access or not refresh:
        raise RuntimeError("로그인이 필요합니다.")

    client = _client()
    response = client.auth.set_session(access, refresh)

    if response.session:
        store["access_token"] = response.session.access_token
        store["refresh_token"] = response.session.refresh_token
    return client


def get_user(store):
    client = _auth(store)
    response = client.auth.get_user()
    if response.user:
        store["user_id"] = str(response.user.id)
        store["email"] = response.user.email or ""
    return response.user


def get_profile(store):
    response = (
        _auth(store)
        .table("profiles")
        .select("user_id,display_name,avatar_url,created_at")
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def load_watchlist(store):
    response = (
        _auth(store)
        .table("watchlist")
        .select("id,symbol,name,market,exchange,created_at")
        .order("created_at", desc=False)
        .execute()
    )
    return response.data or []


def add_watchlist(store, item):
    client = _auth(store)
    user = client.auth.get_user().user
    if not user:
        raise RuntimeError("사용자 확인 실패")

    existing = (
        client.table("watchlist")
        .select("id,symbol,name,market,exchange,created_at")
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
        .insert({
            "user_id": str(user.id),
            "symbol": item["symbol"],
            "name": item["name"],
            "market": item["market"],
            "exchange": item["exchange"],
        })
        .execute()
    )
    return response.data[0] if response.data else item


def delete_watchlist(store, market, exchange, symbol):
    return (
        _auth(store)
        .table("watchlist")
        .delete()
        .eq("market", market)
        .eq("exchange", exchange)
        .eq("symbol", symbol)
        .execute()
    )


def sign_out(store):
    try:
        _auth(store).auth.sign_out()
    finally:
        for key in [
            "access_token", "refresh_token",
            "user_id", "email", "display_name",
        ]:
            store.pop(key, None)
