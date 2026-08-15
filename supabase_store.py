import os
from supabase import create_client

URL=os.getenv("SUPABASE_URL","")
KEY=os.getenv("SUPABASE_PUBLISHABLE_KEY","") or os.getenv("SUPABASE_ANON_KEY","")

def _client():
    if not URL or not KEY:raise RuntimeError("Supabase 환경변수가 필요합니다.")
    return create_client(URL,KEY)

def sign_up(email,password,display_name=""):
    return _client().auth.sign_up({"email":email,"password":password,"options":{"data":{"display_name":display_name}}})
def sign_in(email,password):
    return _client().auth.sign_in_with_password({"email":email,"password":password})

def _auth(store):
    a=store.get("access_token");r=store.get("refresh_token")
    if not a or not r:raise RuntimeError("로그인이 필요합니다.")
    c=_client();resp=c.auth.set_session(a,r)
    if resp.session:
        store["access_token"]=resp.session.access_token
        store["refresh_token"]=resp.session.refresh_token
    return c

def get_user(store):
    c=_auth(store);resp=c.auth.get_user()
    if resp.user:
        store["user_id"]=str(resp.user.id);store["email"]=resp.user.email or ""
    return resp.user

def get_profile(store):
    c=_auth(store)
    r=c.table("profiles").select("user_id,display_name,avatar_url,created_at").limit(1).execute()
    return r.data[0] if r.data else None

def load_watchlist(store):
    c=_auth(store)
    r=c.table("watchlist").select("id,symbol,name,market,exchange,created_at").order("created_at",desc=False).execute()
    return r.data or []

def add_watchlist(store,item):
    c=_auth(store);u=c.auth.get_user().user
    if not u:raise RuntimeError("사용자 확인 실패")
    ex=(c.table("watchlist").select("id,symbol,name,market,exchange,created_at")
        .eq("market",item["market"]).eq("exchange",item["exchange"]).eq("symbol",item["symbol"]).limit(1).execute())
    if ex.data:return ex.data[0]
    r=c.table("watchlist").insert({
        "user_id":str(u.id),"symbol":item["symbol"],"name":item["name"],
        "market":item["market"],"exchange":item["exchange"],
    }).execute()
    return r.data[0] if r.data else item

def delete_watchlist(store,market,exchange,symbol):
    return (_auth(store).table("watchlist").delete()
            .eq("market",market).eq("exchange",exchange).eq("symbol",symbol).execute())

def sign_out(store):
    try:_auth(store).auth.sign_out()
    finally:
        for k in ["access_token","refresh_token","user_id","email","display_name"]:
            store.pop(k,None)
