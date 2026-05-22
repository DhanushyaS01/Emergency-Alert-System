"""
Emergency alert web app: browser capture, optional gender estimate, email and/or Twilio SMS.
Configure SMTP and/or Twilio in .env — never hardcode credentials.
"""
from __future__ import annotations

import base64
import os
import shutil
import smtplib
import ssl
import tempfile
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from gender_opencv import classify_gender_from_image_paths

load_dotenv()

app = Flask(__name__)
# Large JSON payloads (several base64 JPEGs)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024


def _smtp_configured() -> bool:
    return bool(
        os.environ.get("SMTP_SENDER", "").strip()
        and os.environ.get("SMTP_APP_PASSWORD", "").strip()
        and os.environ.get("SMTP_RECEIVER", "").strip()
    )


def _twilio_configured() -> bool:
    return bool(
        os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        and os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        and os.environ.get("TWILIO_FROM_NUMBER", "").strip()
        and os.environ.get("TWILIO_TO_NUMBER", "").strip()
    )


def _twilio_whatsapp_configured() -> bool:
    """Twilio WhatsApp (different from/to than SMS; both use whatsapp:+E164)."""
    return bool(
        os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        and os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        and os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
        and os.environ.get("TWILIO_WHATSAPP_TO", "").strip()
    )


def _decode_image_data(b64: str) -> bytes:
    s = b64.strip()
    if "," in s and s.startswith("data:"):
        s = s.split(",", 1)[1]
    return base64.b64decode(s)


def run_gender_classification(paths: list[str]) -> str:
    if os.environ.get("DISABLE_GENDER", "").strip() == "1":
        return "Disabled in configuration"
    return classify_gender_from_image_paths(paths)


def send_email_with_attachments(
    sender: str,
    receiver: str,
    password: str,
    latitude: str,
    longitude: str,
    image_paths: list[str],
    gender_label: str,
    emergency_message: str,
) -> None:
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = "Emergency alert — images & location"

    body = (
        "EMERGENCY MESSAGE\n"
        f"{emergency_message}\n\n"
        "This is an automated emergency alert.\n\n"
        f"Location:\n  Latitude: {latitude}\n  Longitude: {longitude}\n\n"
        f"Gender classification (ML estimate): {gender_label}\n\n"
    )
    if image_paths:
        body += "Attached: camera captures from the alert.\n"
    else:
        body += "No camera images were included with this alert.\n"
    msg.attach(MIMEText(body, "plain"))

    for image_path in image_paths:
        with open(image_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(image_path)}",
        )
        msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())


def _twilio_alert_body(
    latitude: str, longitude: str, gender_label: str, emergency_message: str
) -> str:
    body = (
        "EMERGENCY ALERT\n"
        f"{emergency_message}\n\n"
        f"Location: {latitude}, {longitude}\n"
        f"Gender (estimate): {gender_label}\n"
        "Photos may be attached to the email if SMTP is enabled."
    )
    if len(body) > 1500:
        body = body[:1497] + "..."
    return body


def send_twilio_sms(
    latitude: str, longitude: str, gender_label: str, emergency_message: str
) -> None:
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client

    sid = os.environ["TWILIO_ACCOUNT_SID"].strip()
    token = os.environ["TWILIO_AUTH_TOKEN"].strip()
    from_num = os.environ["TWILIO_FROM_NUMBER"].strip()
    to_num = os.environ["TWILIO_TO_NUMBER"].strip()

    body = _twilio_alert_body(latitude, longitude, gender_label, emergency_message)

    client = Client(sid, token)
    try:
        client.messages.create(body=body, from_=from_num, to=to_num)
    except TwilioRestException as e:
        raise RuntimeError(f"Twilio error {e.code}: {e.msg}") from e


def send_twilio_whatsapp(
    latitude: str, longitude: str, gender_label: str, emergency_message: str
) -> None:
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client

    sid = os.environ["TWILIO_ACCOUNT_SID"].strip()
    token = os.environ["TWILIO_AUTH_TOKEN"].strip()
    from_wa = os.environ["TWILIO_WHATSAPP_FROM"].strip()
    to_wa = os.environ["TWILIO_WHATSAPP_TO"].strip()

    body = _twilio_alert_body(latitude, longitude, gender_label, emergency_message)

    client = Client(sid, token)
    try:
        client.messages.create(body=body, from_=from_wa, to=to_wa)
    except TwilioRestException as e:
        raise RuntimeError(f"Twilio WhatsApp error {e.code}: {e.msg}") from e


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    smtp_ok = _smtp_configured()
    twilio_ok = _twilio_configured()
    wa_ok = _twilio_whatsapp_configured()
    return jsonify(
        {
            "smtp_configured": smtp_ok,
            "twilio_configured": twilio_ok,
            "whatsapp_configured": wa_ok,
            "any_channel_configured": smtp_ok or twilio_ok or wa_ok,
            "gender_disabled": os.environ.get("DISABLE_GENDER", "").strip() == "1",
        }
    )


@app.route("/api/emergency", methods=["POST"])
def api_emergency():
    if not _smtp_configured() and not _twilio_configured() and not _twilio_whatsapp_configured():
        return (
            jsonify(
                {
                    "ok": False,
                    "error": (
                        "No alert channel configured. Set SMTP_* and/or TWILIO_* / "
                        "TWILIO_WHATSAPP_* in .env (see .env.example)."
                    ),
                }
            ),
            400,
        )

    sender = os.environ.get("SMTP_SENDER", "").strip()
    password = os.environ.get("SMTP_APP_PASSWORD", "").strip()
    receiver = os.environ.get("SMTP_RECEIVER", "").strip()

    data = request.get_json(silent=True) or {}
    images = data.get("images") or []
    lat = str(data.get("lat", "unknown"))
    lng = str(data.get("lng", "unknown"))
    emergency_message = (data.get("message") or "").strip()
    if not emergency_message:
        emergency_message = "I need help — this is an automated emergency alert."

    if not isinstance(images, list):
        images = []

    tmpdir: str | None = None
    paths: list[str] = []
    try:
        if images:
            tmpdir = tempfile.mkdtemp(prefix="emergency_")
            for i, b64 in enumerate(images[:5]):
                if not isinstance(b64, str):
                    continue
                try:
                    raw = _decode_image_data(b64)
                except Exception:
                    continue
                p = os.path.join(tmpdir, f"frame_{i}.jpg")
                with open(p, "wb") as f:
                    f.write(raw)
                paths.append(p)

        if paths:
            gender = run_gender_classification(paths)
        else:
            gender = "No image"

        email_sent = False
        sms_sent = False
        whatsapp_sent = False
        email_error: str | None = None
        sms_error: str | None = None
        whatsapp_error: str | None = None

        if _smtp_configured():
            try:
                send_email_with_attachments(
                    sender,
                    receiver,
                    password,
                    lat,
                    lng,
                    paths,
                    gender,
                    emergency_message,
                )
                email_sent = True
            except smtplib.SMTPAuthenticationError:
                email_error = (
                    "Email login failed. Use a Gmail App Password, not your normal password."
                )
            except Exception as e:
                email_error = str(e)

        if _twilio_configured():
            try:
                send_twilio_sms(lat, lng, gender, emergency_message)
                sms_sent = True
            except ImportError:
                sms_error = "Twilio package not installed (pip install twilio)."
            except Exception as e:
                sms_error = str(e)

        if _twilio_whatsapp_configured():
            try:
                send_twilio_whatsapp(lat, lng, gender, emergency_message)
                whatsapp_sent = True
            except ImportError:
                whatsapp_error = "Twilio package not installed (pip install twilio)."
            except Exception as e:
                whatsapp_error = str(e)

        if not email_sent and not sms_sent and not whatsapp_sent:
            parts = [p for p in (email_error, sms_error, whatsapp_error) if p]
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": " | ".join(parts) if parts else "All channels failed.",
                        "email_sent": False,
                        "sms_sent": False,
                        "whatsapp_sent": False,
                    }
                ),
                502,
            )

        warnings = [f"Email: {email_error}"] if email_error else []
        if sms_error:
            warnings.append(f"SMS: {sms_error}")
        if whatsapp_error:
            warnings.append(f"WhatsApp: {whatsapp_error}")

        parts = []
        if email_sent:
            parts.append("email")
        if sms_sent:
            parts.append("SMS")
        if whatsapp_sent:
            parts.append("WhatsApp")
        message = "Alert sent via " + " & ".join(parts) + "."

        return jsonify(
            {
                "ok": True,
                "gender": gender,
                "email_sent": email_sent,
                "sms_sent": sms_sent,
                "whatsapp_sent": whatsapp_sent,
                "message": message,
                "warnings": warnings or None,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    # Use 127.0.0.1 for local testing; allow camera APIs on localhost in modern browsers.
    app.run(host="127.0.0.1", port=5000, debug=True)
