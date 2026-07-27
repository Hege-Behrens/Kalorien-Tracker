#!/usr/bin/env python3
"""Read the inbox from an iCloud email account via IMAP."""

import imaplib
import email
import os
import sys
from email.header import decode_header
from datetime import datetime


IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993


def decode_str(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def decode_header_value(raw):
    parts = decode_header(raw or "")
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def read_inbox(username: str, password: str, limit: int = 10):
    print(f"Connecting to {IMAP_HOST}:{IMAP_PORT} …")
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(username, password)
        print("Login successful.")

        imap.select("INBOX")
        _, data = imap.search(None, "ALL")
        message_ids = data[0].split()
        total = len(message_ids)
        print(f"Total messages in inbox: {total}\n")

        # Fetch the most recent `limit` messages
        recent_ids = message_ids[-limit:][::-1]

        messages = []
        for uid in recent_ids:
            _, msg_data = imap.fetch(uid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_header_value(msg.get("Subject", "(no subject)"))
            sender = decode_header_value(msg.get("From", ""))
            date_raw = msg.get("Date", "")
            body = get_body(msg).strip()

            messages.append({
                "uid": uid.decode(),
                "subject": subject,
                "from": sender,
                "date": date_raw,
                "body_preview": body[:300],
            })

        return messages


def print_messages(messages):
    sep = "─" * 70
    for i, m in enumerate(messages, 1):
        print(f"\n{'='*70}")
        print(f"  #{i}  |  {m['date']}")
        print(f"  From: {m['from']}")
        print(f"  Subject: {m['subject']}")
        print(sep)
        print(m["body_preview"])
        if len(m["body_preview"]) == 300:
            print("  …")
    print(f"\n{'='*70}")


def main():
    username = os.environ.get("ICLOUD_EMAIL", "hegebehrens@icloud.com")
    password = os.environ.get("ICLOUD_APP_PASSWORD", "")

    if not password:
        print(
            "Error: ICLOUD_APP_PASSWORD environment variable is not set.\n"
            "\n"
            "iCloud requires an app-specific password for IMAP access:\n"
            "  1. Go to https://appleid.apple.com\n"
            "  2. Sign in and open 'Sign-In and Security' → 'App-Specific Passwords'\n"
            "  3. Generate a password for this app\n"
            "  4. Run:  export ICLOUD_APP_PASSWORD='xxxx-xxxx-xxxx-xxxx'\n"
            "  5. Then re-run this script.\n"
        )
        sys.exit(1)

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    messages = read_inbox(username, password, limit=limit)
    print_messages(messages)
    print(f"\nShowing {len(messages)} of the most recent messages.")


if __name__ == "__main__":
    main()
