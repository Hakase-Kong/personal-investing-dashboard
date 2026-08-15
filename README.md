# My Market NiceGUI v0.3 — Social Auth + Charts

## Included

- Email/password Auth
- Google Auth
- Kakao Auth
- Apple Auth button (disabled by default)
- Naver Auth through Supabase Custom OIDC (`custom:naver`)
- Supabase user-specific Watchlist + RLS
- Stock detail page
- 1-day intraday chart
- Daily / weekly / monthly candlestick chart
- Volume
- MA5 / MA20 / MA60 / MA120 selectors
- Korean current prices via KIS
- Korean historical chart via KIS with Yahoo fallback
- US market charts/current prices via Yahoo Finance
- Render deployment

## GitHub files

Upload:

```text
main.py
kis.py
chart_data.py
market_data.py
supabase_store.py
requirements.txt
render.yaml
.gitignore
supabase/schema.sql
README.md (optional)
```

Never upload `.env`.

## Render Environment

```text
APP_URL=https://YOUR-SERVICE.onrender.com

KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ENV=real

SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...

STORAGE_SECRET=long-random-value

ENABLE_GOOGLE=true
ENABLE_KAKAO=true
ENABLE_NAVER=true
ENABLE_APPLE=false

REFRESH_SECONDS=5
```

## Supabase

Run `supabase/schema.sql`.

In Authentication -> URL Configuration:

```text
Site URL:
https://YOUR-SERVICE.onrender.com

Redirect URLs:
https://YOUR-SERVICE.onrender.com/oauth/callback
```

This app uses Supabase browser implicit OAuth flow:
provider -> Supabase callback -> your `/oauth/callback` -> NiceGUI user session.

## Provider callback URL

Google/Kakao/Apple/Naver developer consoles should NOT point directly
to the Render `/oauth/callback`.

The OAuth provider callback URL is Supabase's callback:

```text
https://YOUR_PROJECT_REF.supabase.co/auth/v1/callback
```

Supabase then redirects to:

```text
https://YOUR-SERVICE.onrender.com/oauth/callback
```

after authentication.

## Google

1. Google Cloud Console -> project.
2. Google Auth Platform/OAuth consent screen: configure app name/audience.
3. Create OAuth Client ID -> Web application.
4. Add Supabase callback to Authorized redirect URIs:
   `https://YOUR_PROJECT_REF.supabase.co/auth/v1/callback`
5. Copy Google Client ID and Client Secret.
6. Supabase -> Authentication -> Providers -> Google -> enable.
7. Paste Client ID / Client Secret.

## Kakao

1. Kakao Developers -> create app.
2. App -> Platform Key -> copy REST API Key.
3. Enable Kakao Login.
4. REST API Key settings -> Redirect URI:
   `https://YOUR_PROJECT_REF.supabase.co/auth/v1/callback`
5. Create/enable Client Secret.
6. Configure consent scopes, e.g. profile nickname/image.
7. If email is required, configure `account_email`; availability can depend on Kakao app setup.
8. Supabase -> Authentication -> Providers -> Kakao.
9. Client ID = Kakao REST API Key.
10. Client Secret = Kakao Client Secret.

## Naver

Naver is not a built-in Supabase provider. Naver officially provides OIDC.

1. Naver Developers -> Application -> register application.
2. Select Naver Login.
3. Set service URL and callback.
4. Callback should be the callback URL shown by the Supabase Custom Provider form.
5. Copy Naver Client ID / Client Secret.
6. Supabase -> Authentication -> Providers -> Add Custom Provider.
7. Type: OIDC / Auto-discovery.
8. Identifier: `custom:naver`
9. Client ID / Client Secret: Naver values.
10. Issuer URL:
    `https://nid.naver.com`
11. Enable provider.
12. Keep `ENABLE_NAVER=true` in Render.

Naver's discovery document is:
`https://nid.naver.com/.well-known/openid-configuration`

For unrestricted production use, review Naver's service/review requirements.

## Apple

Apple web auth setup is more involved.

1. Apple Developer -> Certificates, Identifiers & Profiles.
2. Create/choose a primary App ID with Sign in with Apple enabled.
3. Create a Services ID for the website.
4. Configure Sign in with Apple on that Services ID.
5. Domains/Subdomains: Supabase project domain:
   `YOUR_PROJECT_REF.supabase.co`
6. Return URL:
   `https://YOUR_PROJECT_REF.supabase.co/auth/v1/callback`
7. Create a Sign in with Apple key and download the private key once.
8. Note Team ID, Key ID, Services ID and private key.
9. Supabase -> Authentication -> Providers -> Apple.
10. Enter the Apple configuration requested by Supabase.
11. Turn `ENABLE_APPLE=true` in Render.

Apple's web setup depends on Apple Developer program capabilities and is
the one provider here that may conflict with a strict zero-cost goal.

## Charts

Click any Watchlist card.

Routes:

```text
/stock/KR/KOSPI/005930
/stock/US/NMS/NVDA
```

Periods:

- `1D`: intraday
- `D`: daily
- `W`: weekly
- `M`: monthly

Moving averages:

- MA5
- MA20
- MA60
- MA120

KIS domestic period chart endpoint is used for KR D/W/M.
KIS intraday endpoint is used for KR 1D with Yahoo fallback.
US charts use Yahoo Finance in this version.

## Note on KIS traffic

The intraday KIS endpoint returns at most 30 bars per call, so the code
walks backward through the session and caches the result for 60 seconds.
Historical charts are cached longer. This is important when several users
view the same stock.
