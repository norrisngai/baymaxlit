# Google Calendar (real) integration setup

This app supports syncing the student schedule into the student’s real Google Calendar.

## 1) Create OAuth credentials

1. Go to Google Cloud Console.
2. Create/select a project.
3. Enable **Google Calendar API**.
4. Configure the **OAuth consent screen** (External is fine for testing).
5. Create **OAuth Client ID** → **Web application**.
6. Add an **Authorized redirect URI**:

- `http://127.0.0.1:5000/google/callback`

7. Download the client JSON.

## 2) Provide the client JSON to the app

Option A (recommended): put the downloaded JSON in the project root as:

- `google_oauth_client.json`

Option B: set an env var:

- `GOOGLE_OAUTH_CLIENT_SECRETS_FILE` = full path to your JSON

You can also set it in `local_secrets.py` as:

- `GOOGLE_OAUTH_CLIENT_SECRETS_FILE = "..."`

## 3) (Optional) Set timezone for events

By default the app uses `UTC` for event times.

To use your local timezone, set:

- `SCHEDULE_TIMEZONE` (example: `Asia/Hong_Kong`)

## 4) Use it

1. Start the app: `python web_app.py`
2. Log in as a student.
3. Open **My schedule**.
4. Click **Connect Google Calendar** and complete the Google consent.
5. Click **Sync to Google**.

## Localhost HTTP note (insecure_transport)

Google OAuth libraries require HTTPS by default.

For local development on `http://127.0.0.1:5000`, the app enables oauthlib’s localhost exception automatically, so you can test without HTTPS.

For production deployments, you must serve the app over HTTPS.

## Notes

- First connect uses `prompt=consent` so Google returns a `refresh_token` (needed for long-term sync).
- Events are created in the student’s `primary` calendar.
- The app avoids creating duplicates by remembering which schedule item created which Google event.
