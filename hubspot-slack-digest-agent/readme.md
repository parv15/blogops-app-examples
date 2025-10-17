HubSpot → Slack Daily CRM Digest (via Scalekit)

A tiny script that—when you run it—looks back N hours (default: 24h) for HubSpot deal changes and posts:

📢 A summary to a Slack channel

✉️ DMs to mapped HubSpot owners

No web server. No cron. You just trigger the script whenever you want a digest.

1) What you set up (end-to-end flow)
Slack destination

Create or pick a Slack channel (e.g. #sales-updates).

Copy its Channel ID (e.g. C01234567).

If it’s private, later invite the app to the channel.

HubSpot app (OAuth via Scalekit)

In the HubSpot Developer Portal, create an app.

Set the redirect URL to your Scalekit app’s callback (shown in Scalekit).

Install the app into the HubSpot account you want to pull deals from.

Give it minimal scopes (see below).

Connect in Scalekit

In Scalekit, configure OAuth clients for HubSpot + Slack.

Authorize each service under identifiers you’ll use in .env.

These identifiers can be different (e.g. one Slack user, another HubSpot user).

Ensure each identifier has exactly one active connection per service to avoid ambiguity.

2) Minimal scopes you need
HubSpot

For this digest (read-only):

✅ crm.objects.deals.read

That’s it.
You don’t need contacts, companies, schemas, forms, timeline, or write scopes.
(oauth is always implied by HubSpot for authentication.)

Slack

Scalekit abstracts tokens, but your Slack app typically needs:

chat:write → post messages

im:write → send DMs

users:read → resolve IDs

channels:read / groups:read → check membership (public/private channels)

3) Repo layout

hubspot_digest.py → fetch → diff → DM owners → post channel summary

settings.py → loads config from .env

mapping.json → HubSpot owner ID → Slack user ID map (for DMs)

deal_snapshot.json → auto-created snapshot of last-seen deals

requirements.txt → minimal dependencies

4) Setup & Run
A) Install dependencies
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

B) Configure .env

Create a file named .env:

SCALEKIT_ENV_URL=https://hey.scalekit.dev
SCALEKIT_CLIENT_ID=your_client_id
SCALEKIT_CLIENT_SECRET=your_client_secret

# Different identifiers if needed
HUBSPOT_IDENTIFIER=your_hubspot_identifier
SLACK_IDENTIFIER=your_slack_identifier

DIGEST_CHANNEL_ID=C01234567
DIGEST_LOOKBACK_HOURS=24

MAPPING_FILE=mapping.json
SNAPSHOT_FILE=deal_snapshot.json

C) Create mapping.json
{
  "84157204": { "slack_user_id": "U09JQLLKKMH" }
}


Keys = HubSpot owner IDs (string)

Values = Slack user IDs for DMs

D) Run it
python hubspot_digest.py


If a connection isn’t authorized, the script prints OAuth links — open them in your browser, authorize, then re-run.

First run creates deal_snapshot.json. Later runs only report deals updated since last snapshot.

5) How it works (at a glance)

Loads .env and owner mapping.

Fetches HubSpot deals updated in last N hours.

Compares with last snapshot (deal_snapshot.json).

Sends DMs to mapped Slack users for each changed deal.

Posts a channel summary (if DIGEST_CHANNEL_ID is set).

Saves new snapshot for next run.

6) Troubleshooting

channel_not_found → Wrong Slack channel ID or app not invited to private channel.

multiple connected accounts found → Your identifier has multiple Slack connections in Scalekit. Remove duplicates.

“No Slack mapping for owner …” → Add the HubSpot owner’s ID to mapping.json.

No changes reported → Delete deal_snapshot.json to reset baseline.

7) Scheduling (optional)

Currently manual trigger only.
If you want daily automation later → set up cron (Linux/macOS) or Task Scheduler (Windows).

👉 This is now minimal, clear, and easy to follow.