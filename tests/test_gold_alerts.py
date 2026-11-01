"""Unit tests for AlertDispatcher and fatigue cooldown suppression."""

from datetime import datetime, timedelta

from sentinel.gold.alerts import (
    AlertDispatcher,
    AlertSeverity,
    IncidentState,
)


def test_alert_card_generation():
    """Verify Slack Block Kit and MS Teams cards are correctly structured."""
    dispatcher = AlertDispatcher(cooldown_hours=4)

    slack_card = dispatcher.build_slack_block_kit_card(
        table_name="gold_revenue",
        target_date="2026-10-31",
        severity=AlertSeverity.CRITICAL,
        title="Partition SLA Breached",
        message="Partition 2026-10-31 did not arrive within 4h grace period.",
        details={"merge_sql": "MERGE INTO target ..."},
    )

    assert "attachments" in slack_card
    blocks = slack_card["attachments"][0]["blocks"]
    assert any("Sentinel Alert: Partition SLA Breached" in str(b) for b in blocks)
    assert any("MERGE INTO target" in str(b) for b in blocks)

    teams_card = dispatcher.build_teams_card(
        table_name="gold_revenue",
        target_date="2026-10-31",
        severity=AlertSeverity.CRITICAL,
        title="Partition SLA Breached",
        message="Partition 2026-10-31 missing.",
    )
    assert teams_card["type"] == "message"
    assert teams_card["attachments"][0]["content"]["type"] == "AdaptiveCard"


def test_alert_fatigue_cooldown_suppression():
    """Repeated alerts for the same table, partition, and incident should be suppressed within cooldown."""
    dispatcher = AlertDispatcher(cooldown_hours=4)
    t0 = datetime(2026, 10, 31, 6, 0, 0)

    # First alert at 06:00
    first_record = dispatcher.dispatch_alert(
        table_name="gold_revenue",
        target_date="2026-10-31",
        incident_type="SLA_BREACH",
        severity=AlertSeverity.CRITICAL,
        title="SLA Breach",
        message="Missing partition.",
        now=t0,
    )

    assert first_record.state == IncidentState.TRIGGERED
    assert first_record.notification_count == 1
    assert len(dispatcher.sent_payloads) == 1

    # Second alert at 07:00 (within 4h cooldown)
    t1 = t0 + timedelta(hours=1)
    second_record = dispatcher.dispatch_alert(
        table_name="gold_revenue",
        target_date="2026-10-31",
        incident_type="SLA_BREACH",
        severity=AlertSeverity.CRITICAL,
        title="SLA Breach",
        message="Still missing.",
        now=t1,
    )

    assert second_record.state == IncidentState.SUPPRESSED_COOLDOWN
    assert second_record.notification_count == 2
    # Verify no new payload was emitted during cooldown
    assert len(dispatcher.sent_payloads) == 1

    # Third alert at 11:00 (after 4h cooldown has expired)
    t2 = t0 + timedelta(hours=5)
    third_record = dispatcher.dispatch_alert(
        table_name="gold_revenue",
        target_date="2026-10-31",
        incident_type="SLA_BREACH",
        severity=AlertSeverity.CRITICAL,
        title="SLA Breach",
        message="Still missing after 5 hours.",
        now=t2,
    )

    assert third_record.state == IncidentState.TRIGGERED
    assert len(dispatcher.sent_payloads) == 2


def test_incident_resolution_flow():
    """Resolving an active incident should update status and dispatch resolution notice."""
    dispatcher = AlertDispatcher(cooldown_hours=4)
    t0 = datetime(2026, 10, 31, 6, 0, 0)

    dispatcher.dispatch_alert(
        table_name="gold_revenue",
        target_date="2026-10-31",
        incident_type="SLA_BREACH",
        severity=AlertSeverity.CRITICAL,
        title="SLA Breach",
        message="Missing partition.",
        now=t0,
    )

    t1 = t0 + timedelta(minutes=45)
    resolved_record = dispatcher.resolve_incident(
        table_name="gold_revenue",
        target_date="2026-10-31",
        incident_type="SLA_BREACH",
        resolution_message="Partition 2026-10-31 arrived and was reconciled.",
        now=t1,
    )

    assert resolved_record is not None
    assert resolved_record.state == IncidentState.RESOLVED
    assert resolved_record.resolved_at == t1
    assert len(dispatcher.sent_payloads) == 2
    assert "RESOLVED: SLA_BREACH" in str(dispatcher.sent_payloads[1])
