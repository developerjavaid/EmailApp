import csv
import html
import logging
import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import azure.functions as func

from campaigns import DEFAULT_CAMPAIGN, get_campaign
from db_utils import (
    count_sent_today,
    ensure_delivery_columns,
    fetch_clinics,
    fetch_thresholds,
    fetch_unsent_customers,
    mark_delivered,
    mark_unsubscribed,
)
from email_utils import send_email
from rate_limiter import rate_limiter
from unsubscribe_utils import generate_token, verify_token

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

TEMPLATES_DIR = Path(__file__).parent / "templates"
LOGS_DIR = Path(__file__).parent / "logs"


def _write_send_log(results):
    """Write one CSV per send, named by run date/time, to LOGS_DIR."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOGS_DIR / f"send_{timestamp}.csv"
        with log_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["email", "clinic_id", "clinic_name", "status", "error"])
            for r in results:
                writer.writerow([r["email"], r["clinic_id"], r["clinic_name"], r["status"], r.get("error", "")])
        logging.info("Wrote send log to %s", log_path)
    except Exception:
        logging.exception("Failed to write send log")


def _unsubscribe_link(email):
    base_url = os.environ.get("APP_BASE_URL", "https://viasmiles-emailapp.azurewebsites.net")
    token = generate_token(email)
    return f"{base_url}/api/unsubscribe?email={urllib.parse.quote(email)}&token={token}"


def _render_merge_tags(template_name, **tags):
    """Render a campaign HTML template's {{merge_tag}} placeholders."""
    html = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    for key, value in tags.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def _send_clinic_emails(clinic_id, clinic, threshold, campaign):
    """Send this run's batch for one clinic, respecting its daily/hourly/
    per-minute throttle, and return one result dict per email actually
    attempted.

    Each clinic reads/writes its own source_table (from the clinic mapping
    row), so this is safe to run concurrently with the other clinics - see
    the ThreadPoolExecutor in _send_all_customer_emails. Because they run
    concurrently, pacing against the ACS account's shared 100/min and
    1000/hour quota is handled by the module-level rate_limiter, not here;
    per_minute_limit below only paces this one clinic's own share of it.
    """
    results = []
    daily_limit = threshold["daily_limit"]
    hourly_limit = threshold["hourly_limit"]
    per_minute_limit = threshold.get("per_minute_limit") or 0
    if daily_limit <= 0:
        logging.info("Clinic %s has daily_limit <= 0; skipping.", clinic_id)
        return results

    ensure_delivery_columns(clinic["source_table"])

    sent_today = count_sent_today(clinic["source_table"], clinic_id)
    remaining_today = daily_limit - sent_today
    if remaining_today <= 0:
        logging.info(
            "Clinic %s already sent its daily limit today (%d/%d); skipping.",
            clinic_id, sent_today, daily_limit,
        )
        return results

    batch_size = min(remaining_today, hourly_limit)
    customers = fetch_unsent_customers(clinic, clinic_id, batch_size)

    clinic_minute_key = None
    clinic_minute_count = 0

    for email, fname, lname in customers:
        if per_minute_limit > 0:
            while True:
                now = time.time()
                minute_key = int(now // 60)
                if minute_key != clinic_minute_key:
                    clinic_minute_key = minute_key
                    clinic_minute_count = 0
                if clinic_minute_count < per_minute_limit:
                    clinic_minute_count += 1
                    break
                time.sleep(60 - (now % 60) + 0.5)

        if not rate_limiter.wait_for_slot():
            logging.info(
                "ACS hourly send budget reached; stopping further sends this run "
                "for clinic %s (%s). Remainder will go out on the next scheduled run.",
                clinic_id, clinic["name"],
            )
            break

        result = {"email": email, "clinic_id": clinic_id, "clinic_name": clinic["name"]}
        try:
            html_body = _render_merge_tags(
                clinic["template_name"],
                first_name=fname or "there",
                last_name=lname or "",
                unsubscribe_link=_unsubscribe_link(email),
                **campaign["merge_tags"],
            )
            send_email(
                to_address=email,
                subject=campaign["subject"],
                html_body=html_body,
                from_address=clinic["from_email"],
            )
            mark_delivered(clinic, clinic_id, email)
            result["status"] = "sent"
            logging.info("Sent to %s (clinic_id=%s, clinic=%s)", email, clinic_id, clinic["name"])
        except Exception as e:
            logging.exception("Failed to send email to %s (clinic_id=%s)", email, clinic_id)
            result["status"] = "failed"
            result["error"] = str(e)

        results.append(result)

    return results


def _send_all_customer_emails(campaign_id=None):
    """Send this run's throttled batch for every clinic whose daily_limit is
    > 0, one clinic's batch sent in parallel with the others (each clinic
    reads/writes its own source_table, so there's no shared state between
    them), and returns one result dict per email actually attempted:
    {email, clinic_id, clinic_name, status ("sent"/"failed"), error}.

    A clinic's own daily/hourly limits (clinic_threshold table) decide how
    many of its still-unsent customers (delivery_status not yet 'sent') go
    out in this run; see _send_clinic_emails.
    """
    campaign_id, campaign = get_campaign(campaign_id or DEFAULT_CAMPAIGN)
    clinics = fetch_clinics()
    thresholds = fetch_thresholds()

    active = {
        clinic_id: clinic
        for clinic_id, clinic in clinics.items()
        if thresholds.get(clinic_id, {}).get("daily_limit", 0) > 0
    }

    results = []
    if active:
        with ThreadPoolExecutor(max_workers=len(active)) as executor:
            futures = {
                executor.submit(
                    _send_clinic_emails, clinic_id, clinic, thresholds[clinic_id], campaign
                ): clinic_id
                for clinic_id, clinic in active.items()
            }
            for future in as_completed(futures):
                results.extend(future.result())

    _write_send_log(results)
    return results


@app.route(route="send-customer-emails", methods=["GET", "POST"])
def send_customer_emails(req: func.HttpRequest) -> func.HttpResponse:
    campaign_id = req.params.get("campaign")
    results = _send_all_customer_emails(campaign_id)

    sent = [r for r in results if r["status"] == "sent"]
    failed = [r for r in results if r["status"] == "failed"]

    lines = [f"Sent: {len(sent)}, Failed: {len(failed)}.", "", "Breakdown:"]
    for r in results:
        line = f"  {r['email']} | clinic_id={r['clinic_id']} | clinic={r['clinic_name']} | {r['status']}"
        if r["status"] == "failed":
            line += f" | error={r.get('error')}"
        lines.append(line)

    return func.HttpResponse("\n".join(lines), status_code=200)


@app.timer_trigger(schedule="%TIMER_SCHEDULE%", arg_name="mytimer", run_on_startup=False)
def send_customer_emails_daily(mytimer: func.TimerRequest) -> None:
    results = _send_all_customer_emails()
    sent = [r for r in results if r["status"] == "sent"]
    failed = [r for r in results if r["status"] == "failed"]
    logging.info("Daily send complete. Sent: %d, Failed: %d", len(sent), len(failed))
    for r in results:
        logging.info(
            "  %s | clinic_id=%s | clinic=%s | %s%s",
            r["email"], r["clinic_id"], r["clinic_name"], r["status"],
            f" | error={r.get('error')}" if r["status"] == "failed" else "",
        )


def _render(template_name, **fields):
    page = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    for key, value in fields.items():
        page = page.replace("{" + key + "}", value)
    return page


@app.route(route="unsubscribe", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def unsubscribe(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "POST":
        try:
            form = urllib.parse.parse_qs(req.get_body().decode("utf-8"))
            email = form.get("email", [""])[0]
            token = form.get("token", [""])[0]
        except Exception:
            email, token = "", ""
    else:
        email = req.params.get("email", "")
        token = req.params.get("token", "")

    email = email.strip()
    valid = bool(email) and verify_token(email, token)

    if req.method == "POST":
        if not valid:
            return func.HttpResponse("Invalid or expired unsubscribe link.", status_code=400)
        try:
            mark_unsubscribed(email, campaign="viasmiles_acquisition_v1")
        except Exception:
            logging.exception("Failed to mark %s as unsubscribed", email)
            return func.HttpResponse("Something went wrong. Please try again later.", status_code=500)
        page = _render("unsubscribe_done.html", email=html.escape(email))
        return func.HttpResponse(page, status_code=200, mimetype="text/html")

    # GET: show the confirmation page.
    action_url = f"{req.url.split('?')[0]}"
    if not valid:
        error_banner = (
            '<div class="error-banner">This unsubscribe link is invalid or has expired. '
            "Please use the link from your most recent email, or call us directly.</div>"
        )
        form_block = '<a class="secondary" href="https://viasmiles.com/">Return to viasmiles.com</a>'
    else:
        error_banner = ""
        form_block = (
            f'<form method="post" action="{html.escape(action_url)}">'
            f'<input type="hidden" name="email" value="{html.escape(email)}">'
            f'<input type="hidden" name="token" value="{html.escape(token)}">'
            '<button type="submit">Confirm unsubscribe</button>'
            "</form>"
            '<a class="secondary" href="https://viasmiles.com/">No thanks, keep me subscribed</a>'
        )

    page = _render(
        "unsubscribe_confirm.html",
        email=html.escape(email),
        token=html.escape(token),
        error_banner=error_banner,
        form_block=form_block,
    )
    return func.HttpResponse(page, status_code=200, mimetype="text/html")
