# Google Drive Setup

Date: 2026-08-22

Lingua Viva supports in-app Google Drive sign-in through an OAuth Desktop client.
Do not commit OAuth credentials to this repository.

## Required Google Cloud Setup

1. Open Google Cloud Console.
2. Enable the Google Drive API for the Lingua Viva project.
3. Create an OAuth 2.0 Client ID with application type `Desktop app`.
4. Copy the client ID and client secret.

## Local Source Checkout

Set either environment variable pair before starting Lingua Viva:

```bash
export LV_GOOGLE_OAUTH_CLIENT_ID="<client id>"
export LV_GOOGLE_OAUTH_CLIENT_SECRET="<client secret>"
```

The shorter spec alias is also accepted:

```bash
export LV_GOOGLE_OAUTH_CLIENT_ID="<client id>"
export LV_GOOGLE_OAUTH_SECRET="<client secret>"
```

Alternatively, write this uncommitted file:

```text
~/.lingua-viva/config/oauth_client.json
```

with:

```json
{
  "client_id": "<client id>",
  "client_secret": "<client secret>"
}
```

The file must stay outside the repo and should be mode `0600`.

## Packaged Desktop Builds

The desktop release workflow packages `oauth_client.json` from GitHub Actions
secrets when these are configured:

```text
LV_GOOGLE_OAUTH_CLIENT_ID
LV_GOOGLE_OAUTH_CLIENT_SECRET
```

After packaging, verify the app shows an active `Sign in with Google` button in
Sources -> Drive. The app requests `drive.file` access plus `openid email`.

## Verification

1. Start Lingua Viva.
2. Open Sources -> Drive.
3. Click `Sign in with Google`.
4. Complete consent in the browser.
5. Return to Lingua Viva and confirm Drive status shows a signed-in account.
6. Connect a Drive folder or paste a Drive roster link from Students.
7. Confirm files list and import through the normal preview-first pipeline.

If the button says Google Drive sign-in is unavailable, the OAuth client
configuration is missing from both environment variables and local config.
