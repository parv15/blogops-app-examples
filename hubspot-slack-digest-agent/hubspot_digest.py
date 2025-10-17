"""
hubspot_digest.py - HubSpot → Slack Daily CRM Digest Agent (clean mapping)

This version:
- Uses env vars HUBSPOT_IDENTIFIER and SLACK_IDENTIFIER for service accounts.
- Mapping file only contains HubSpot owner ID → Slack user ID.
- No identifier data is read from mapping.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from settings import Settings
from sk_connectors import get_connector


# ----------------------------
# Snapshot helpers
# ----------------------------

def load_snapshot(path: str) -> Dict[str, str]:
    """Load previous snapshot of deals (deal_id -> last_modified timestamp)."""
    try:
        if not path:
            return {}
        p = Path(path)
        if not p.exists():
            return {}
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def save_snapshot(path: str, snapshot: Dict[str, str]) -> None:
    """Persist snapshot (deal_id -> last_modified timestamp) for next run."""
    try:
        if not path:
            return
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception:
        # Non-fatal
        pass


# ----------------------------
# Utilities
# ----------------------------

def ms_timestamp(dt: datetime) -> int:
    """Convert a datetime into a Unix timestamp in milliseconds."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def load_owner_mapping(path: str) -> Dict[str, str]:
    """
    Minimal mapping loader:
    {
      "84157204": { "slack_user_id": "U09JQLLKKMH" },
      "12345678": { "slack_user_id": "U01ABCDE2F3" }
    }
    Returns: { "84157204": "U09JQLLKKMH", "12345678": "U01ABCDE2F3" }
    """
    p = Path(path)
    if not p.exists():
        print(f"⚠️  Mapping file not found: {path}")
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            print("⚠️  Mapping file must contain a JSON object.")
            return {}
        out: Dict[str, str] = {}
        for owner_id, entry in data.items():
            if isinstance(entry, dict) and entry.get("slack_user_id"):
                out[str(owner_id)] = str(entry["slack_user_id"])
        return out
    except Exception as e:
        print(f"❌ Error loading mapping file: {e}")
        return {}


# ----------------------------
# HubSpot fetch & grouping
# ----------------------------

def fetch_recent_deals(connector, identifier: str, lookback_hours: int) -> List[Dict]:
    """Fetch deals from HubSpot modified within the lookback window."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=lookback_hours)
    ms_start = ms_timestamp(start_time)
    ms_end = ms_timestamp(end_time)

    print(f"📦 Fetching deals modified between {start_time.isoformat()} and {end_time.isoformat()}")

    all_results: List[Dict] = []
    after: Optional[str] = None
    page = 0
    while True:
        page += 1
        params: Dict[str, any] = {
            "query": "",
            "filterGroups": [{
                "filters": [{
                    "propertyName": "hs_lastmodifieddate",
                    "operator": "BETWEEN",
                    "value": str(ms_start),
                    "highValue": str(ms_end),
                }]
            }],
            "properties": [
                "dealname", "amount", "pipeline", "dealstage",
                "hubspot_owner_id", "hs_lastmodifieddate"
            ],
            "limit": 100,
        }
        if after:
            params["after"] = after

        result = connector.execute_action_with_retry(
            identifier=identifier, tool="hubspot_deals_search", parameters=params
        )
        if not result:
            print("❌ hubspot_deals_search returned no data or encountered an error")
            break

        data = result if isinstance(result, dict) else getattr(result, "data", None)
        if not isinstance(data, dict):
            print("⚠️  Unexpected response structure from hubspot_deals_search")
            break

        page_results: List[Dict] = data.get("results") or data.get("deals") or []
        print(f"   📄 Page {page}: fetched {len(page_results)} deals")
        all_results.extend(page_results)

        paging = data.get("paging") or {}
        next_obj = paging.get("next") if isinstance(paging, dict) else None
        after = next_obj.get("after") if next_obj else None
        if not after:
            break

    print(f"✅ Total deals fetched: {len(all_results)}")
    return all_results


def group_deals_by_owner(deals: List[Dict]) -> Dict[str, List[Dict]]:
    """Group deals by HubSpot owner ID."""
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for deal in deals:
        props = deal.get("properties", {})
        owner_id = props.get("hubspot_owner_id") or deal.get("hubspot_owner_id") or deal.get("owner_id")
        grouped[str(owner_id or "unknown")].append(deal)
    return grouped


# ----------------------------
# Slack helpers
# ----------------------------

def get_slack_display_name(connector, identifier: str, slack_user_id: str) -> Optional[str]:
    """Retrieve the display name for a Slack user via Scalekit."""
    if not slack_user_id:
        return None
    try:
        result = connector.execute_action_with_retry(
            identifier=identifier,
            tool="slack_get_user_info",
            parameters={"user": slack_user_id},
        )
        data = result if isinstance(result, dict) else getattr(result, "data", None)
        if not isinstance(data, dict):
            return None
        user_info = data.get("user")
        if not user_info:
            return None
        profile = user_info.get("profile", {})
        return profile.get("display_name") or profile.get("real_name") or user_info.get("name")
    except Exception:
        return None


def build_dm_message(deals: List[Dict]) -> str:
    """Construct a Slack DM message summarising deals for an owner."""
    lines = [f"📊 *Your pipeline updates for the last {Settings.DIGEST_LOOKBACK_HOURS}h*", ""]
    for i, deal in enumerate(deals, start=1):
        props = deal.get("properties", {})
        name = props.get("dealname", deal.get("dealname", "Unnamed Deal"))
        stage = props.get("dealstage", deal.get("dealstage", ""))
        pipeline = props.get("pipeline", deal.get("pipeline", ""))
        amount = props.get("amount", deal.get("amount", ""))
        last_modified = props.get("hs_lastmodifieddate", deal.get("hs_lastmodifieddate", ""))
        pretty_date = ""
        if last_modified:
            try:
                dt = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                pretty_date = dt.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                pretty_date = last_modified
        lines.append(
            f"{i}. *{name}*\n   • Stage: `{stage}`\n   • Pipeline: `{pipeline}`\n   • Amount: `{amount}`\n   • Modified: {pretty_date}"
        )
    return "\n".join(lines)


def build_channel_summary(grouped_deals: Dict[str, List[Dict]],
                          owner_to_slack: Dict[str, str],
                          connector, slack_identifier: str) -> str:
    """Construct a channel summary message summarising all pipeline updates."""
    total_deals = sum(len(deals) for deals in grouped_deals.values())
    lines = [
        f"📣 *Daily CRM Digest – Pipeline Updates ({Settings.DIGEST_LOOKBACK_HOURS}h)*",
        f"Total deals updated: {total_deals}",
        "",
    ]
    for owner_id, deals in sorted(grouped_deals.items(), key=lambda x: len(x[1]), reverse=True):
        slack_user_id = owner_to_slack.get(str(owner_id))
        owner_name = get_slack_display_name(connector, slack_identifier, slack_user_id) if slack_user_id else None
        owner_label = owner_name or owner_id
        lines.append(f"*{owner_label}* – {len(deals)} deal(s)")
        for deal in deals[:3]:
            props = deal.get("properties", {})
            name = props.get("dealname", deal.get("dealname", "Unnamed Deal"))
            stage = props.get("dealstage", deal.get("dealstage", ""))
            pipeline = props.get("pipeline", deal.get("pipeline", ""))
            amount = props.get("amount", deal.get("amount", ""))
            lines.append(f"   • *{name}* — Stage: `{stage}`, Pipeline: `{pipeline}`, Amount: `{amount}`")
        if len(deals) > 3:
            lines.append(f"   • …and {len(deals) - 3} more")
        lines.append("")
    return "\n".join(lines).strip()


def send_slack_message(connector, identifier: str, channel: str, text: str, thread_ts: Optional[str] = None):
    """Send a message to Slack using the Slack connector."""
    params = {"channel": channel, "text": text}
    if thread_ts:
        params["thread_ts"] = thread_ts
    result = connector.execute_action_with_retry(
        identifier=identifier, tool="slack_send_message", parameters=params
    )
    if result:
        ts = None
        if isinstance(result, dict):
            ts = result.get("ts") or result.get("timestamp")
        elif hasattr(result, "data") and isinstance(result.data, dict):
            ts = result.data.get("ts") or result.data.get("timestamp")
        print(f"✅ Sent Slack message to {channel} (ts: {ts})")
    else:
        print(f"❌ Failed to send Slack message to {channel}")


# ----------------------------
# Main
# ----------------------------

def run_digest():
    """Main entry point for running the daily digest."""
    connector = get_connector()

    # --- Required service identifiers from env ---
    hubspot_identifier: Optional[str] = Settings.HUBSPOT_IDENTIFIER
    slack_identifier: Optional[str] = Settings.SLACK_IDENTIFIER

    if not hubspot_identifier:
        print("❌ HUBSPOT_IDENTIFIER not set. Please set it in your .env.")
        return
    if not slack_identifier:
        print("❌ SLACK_IDENTIFIER not set. Please set it in your .env.")
        return

    # Validate connections; print OAuth links only if missing
    hubspot_connected = (
        connector.is_service_connected("hubspotcrm", hubspot_identifier)
        or connector.is_service_connected("hubspot", hubspot_identifier)
    )
    if not hubspot_connected:
        print("❌ HubSpot not connected for this user. Please authorize HubSpot via Scalekit OAuth.")
        url = connector.get_authorization_url(service="hubspot", user_identifier=hubspot_identifier)
        print("🔗 HubSpot OAuth:", url)
        return

    if not connector.is_service_connected("slack", slack_identifier):
        print("❌ Slack not connected for this user. Please authorize Slack via Scalekit OAuth.")
        url = connector.get_authorization_url(service="slack", user_identifier=slack_identifier)
        print("🔗 Slack OAuth:", url)
        return

    # Load minimal owner mapping (HubSpot owner → Slack user)
    owner_to_slack: Dict[str, str] = load_owner_mapping(Settings.MAPPING_FILE)

    # Fetch deals within the lookback window
    deals = fetch_recent_deals(
        connector, identifier=hubspot_identifier, lookback_hours=Settings.DIGEST_LOOKBACK_HOURS
    )

    # Snapshot delta
    snapshot_path = getattr(Settings, "SNAPSHOT_FILE", "deal_snapshot.json")
    previous_snapshot = load_snapshot(snapshot_path)
    current_snapshot: Dict[str, str] = {}
    changed_deals: List[Dict] = []
    for deal in deals:
        deal_id = str(deal.get("id") or deal.get("dealId"))
        props = deal.get("properties", {})
        last_modified = props.get("hs_lastmodifieddate") or deal.get("hs_lastmodifieddate") or ""
        current_snapshot[deal_id] = last_modified
        prev_last = previous_snapshot.get(deal_id)
        if prev_last is None or prev_last != last_modified:
            changed_deals.append(deal)
    save_snapshot(snapshot_path, current_snapshot)

    # If no changed deals, optional channel notice
    if not changed_deals:
        print(f"📭 No new or updated deals in the last {Settings.DIGEST_LOOKBACK_HOURS}h.")
        if Settings.DIGEST_CHANNEL_ID:
            msg = (
                f"📣 *Daily CRM Digest – Pipeline Updates ({Settings.DIGEST_LOOKBACK_HOURS}h)*\n"
                f"No new or updated pipeline changes in the last {Settings.DIGEST_LOOKBACK_HOURS}h."
            )
            send_slack_message(connector, identifier=slack_identifier,
                               channel=Settings.DIGEST_CHANNEL_ID, text=msg)
        return

    # Group changed deals by owner
    grouped = group_deals_by_owner(changed_deals)

    # Send DMs to mapped owners
    for owner_id, owner_deals in grouped.items():
        slack_user_id = owner_to_slack.get(str(owner_id))
        if not slack_user_id:
            print(f"ℹ️  No Slack mapping for owner {owner_id} – skipping DM.")
            continue
        dm_text = build_dm_message(owner_deals)
        send_slack_message(connector, identifier=slack_identifier,
                           channel=slack_user_id, text=dm_text)

    # Send channel summary
    if Settings.DIGEST_CHANNEL_ID:
        summary_text = build_channel_summary(grouped_deals=grouped,
                                             owner_to_slack=owner_to_slack,
                                             connector=connector,
                                             slack_identifier=slack_identifier)
        send_slack_message(connector, identifier=slack_identifier,
                           channel=Settings.DIGEST_CHANNEL_ID, text=summary_text)
    else:
        print("ℹ️  DIGEST_CHANNEL_ID not set. Channel summary will not be sent.")


if __name__ == "__main__":
    run_digest()
