"""Zero-dependency alerting engine with alert fatigue cooldown suppression."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
from typing import Any, Dict, List, Optional
import urllib.request
import uuid


class AlertSeverity(str, Enum):
    """Severity tier for incident alerts."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class IncidentState(str, Enum):
    """Operational lifecycle state of a quality incident."""

    TRIGGERED = "TRIGGERED"
    SUPPRESSED_COOLDOWN = "SUPPRESSED_COOLDOWN"
    RESOLVED = "RESOLVED"


@dataclass
class IncidentRecord:
    """Tracking entity for active and historical lakehouse quality incidents."""

    incident_id: str
    target_table: str
    target_date: str
    incident_type: str  # 'SLA_BREACH', 'WINDOW_INCOMPLETE', 'VOLUME_ANOMALY'
    severity: AlertSeverity
    state: IncidentState
    message: str
    triggered_at: datetime
    cooldown_until: datetime
    resolved_at: Optional[datetime] = None
    notification_count: int = 1
    details: Dict[str, Any] = field(default_factory=dict)


class AlertDispatcher:
    """Dispatches actionable incident alerts with built-in fatigue suppression.

    Avoids spamming team channels when upstream pipelines stall.
    Supports Slack Block Kit and Microsoft Teams Adaptive Cards with zero external pip dependencies.
    """

    def __init__(self, cooldown_hours: int = 4):
        self.cooldown_hours = cooldown_hours
        self.active_incidents: Dict[str, IncidentRecord] = {}
        self.sent_payloads: List[Dict[str, Any]] = []

    def _incident_key(
        self, target_table: str, target_date: str, incident_type: str
    ) -> str:
        return f"{target_table}::{target_date}::{incident_type}"

    def build_slack_block_kit_card(
        self,
        table_name: str,
        target_date: str,
        severity: AlertSeverity,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Format an actionable Slack Block Kit card."""
        color_map = {
            AlertSeverity.INFO: "#38BDF8",
            AlertSeverity.WARNING: "#F59E0B",
            AlertSeverity.CRITICAL: "#EF4444",
        }
        color = color_map.get(severity, "#EF4444")

        fields = [
            {"type": "mrkdwn", "text": f"*Target Table:*\n`{table_name}`"},
            {"type": "mrkdwn", "text": f"*Partition Date:*\n`{target_date}`"},
            {"type": "mrkdwn", "text": f"*Severity:*\n*{severity.value}*"},
            {
                "type": "mrkdwn",
                "text": f"*Timestamp:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            },
        ]

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🛡️ Sentinel Alert: {title}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message},
            },
            {"type": "divider"},
            {"type": "section", "fields": fields},
        ]

        if details and "merge_sql" in details:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Automated Delta MERGE Healing Query:*\n```{details['merge_sql']}```",
                    },
                }
            )

        return {"attachments": [{"color": color, "blocks": blocks}]}

    def build_teams_card(
        self,
        table_name: str,
        target_date: str,
        severity: AlertSeverity,
        title: str,
        message: str,
    ) -> Dict[str, Any]:
        """Format an actionable Microsoft Teams Adaptive Card."""
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"Sentinel Alert: {title}",
                                "weight": "Bolder",
                                "size": "Medium",
                            },
                            {"type": "TextBlock", "text": message, "wrap": True},
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Table", "value": table_name},
                                    {"title": "Partition", "value": target_date},
                                    {"title": "Severity", "value": severity.value},
                                ],
                            },
                        ],
                    },
                }
            ],
        }

    def dispatch_alert(
        self,
        table_name: str,
        target_date: str,
        incident_type: str,
        severity: AlertSeverity,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        webhook_url: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> IncidentRecord:
        """Dispatch incident notification with alert fatigue cooldown check."""
        current_time = now or datetime.now()
        key = self._incident_key(table_name, target_date, incident_type)

        existing = self.active_incidents.get(key)
        if existing and existing.state != IncidentState.RESOLVED:
            if current_time < existing.cooldown_until:
                # Fatigue suppression active
                existing.notification_count += 1
                return IncidentRecord(
                    incident_id=existing.incident_id,
                    target_table=table_name,
                    target_date=target_date,
                    incident_type=incident_type,
                    severity=severity,
                    state=IncidentState.SUPPRESSED_COOLDOWN,
                    message=f"Alert suppressed: within {self.cooldown_hours}h cooldown window.",
                    triggered_at=existing.triggered_at,
                    cooldown_until=existing.cooldown_until,
                    notification_count=existing.notification_count,
                    details={"suppressed": True},
                )

        # Trigger new incident alert
        cooldown_expiry = current_time + timedelta(hours=self.cooldown_hours)
        record = IncidentRecord(
            incident_id=str(uuid.uuid4()),
            target_table=table_name,
            target_date=target_date,
            incident_type=incident_type,
            severity=severity,
            state=IncidentState.TRIGGERED,
            message=message,
            triggered_at=current_time,
            cooldown_until=cooldown_expiry,
            notification_count=1,
            details=details or {},
        )
        self.active_incidents[key] = record

        # Generate payload
        payload = self.build_slack_block_kit_card(
            table_name=table_name,
            target_date=target_date,
            severity=severity,
            title=title,
            message=message,
            details=details,
        )
        self.sent_payloads.append(payload)

        # Send to webhook if provided
        if webhook_url and (
            webhook_url.startswith("https://") or webhook_url.startswith("http://")
        ):
            try:
                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5):  # nosec B310
                    pass
            except Exception as e:
                record.details["webhook_error"] = str(e)

        return record

    def resolve_incident(
        self,
        table_name: str,
        target_date: str,
        incident_type: str,
        resolution_message: str = "Partition arrived cleanly; rolling windows healed.",
        webhook_url: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Optional[IncidentRecord]:
        """Mark incident as resolved and optionally send resolution notification."""
        key = self._incident_key(table_name, target_date, incident_type)
        existing = self.active_incidents.get(key)
        if not existing or existing.state == IncidentState.RESOLVED:
            return None

        current_time = now or datetime.now()
        existing.state = IncidentState.RESOLVED
        existing.resolved_at = current_time

        res_payload = self.build_slack_block_kit_card(
            table_name=table_name,
            target_date=target_date,
            severity=AlertSeverity.INFO,
            title=f"RESOLVED: {existing.incident_type}",
            message=resolution_message,
        )
        self.sent_payloads.append(res_payload)

        if webhook_url and (
            webhook_url.startswith("https://") or webhook_url.startswith("http://")
        ):
            try:
                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(res_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5):  # nosec B310
                    pass
            except Exception as e:
                existing.details["resolution_webhook_error"] = str(e)

        return existing
