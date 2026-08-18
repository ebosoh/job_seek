"""IMAP Inbox Scanner for hudson.eboso@techbrain.africa."""

import email
from email.header import decode_header
from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from src.config import EmailConfig
from src.core.llm_client import LLMClient
from src.data.tracker import ApplicationTracker

logger = logging.getLogger(__name__)

try:
    from imapclient import IMAPClient
except ImportError:
    IMAPClient = None


class ParsedEmail(BaseModel):
    """Structured representation of an incoming recruiter email."""
    uid: int
    sender: str
    subject: str
    date_str: str
    body_text: str
    classification: str = "UNRELATED"
    confidence: float = 0.0
    action_item: str = ""
    matched_company: Optional[str] = None


class InboxScanner:
    """Connects to IMAP server, scans recent emails, and updates application statuses."""

    def __init__(self, config: EmailConfig, llm_client: LLMClient, tracker: ApplicationTracker):
        self.config = config
        self.llm = llm_client
        self.tracker = tracker

    def _decode_str(self, header_value: str) -> str:
        """Decodes MIME encoded email header string."""
        if not header_value:
            return ""
        decoded_list = decode_header(header_value)
        result = []
        for text, encoding in decoded_list:
            if isinstance(text, bytes):
                try:
                    result.append(text.decode(encoding or "utf-8", errors="ignore"))
                except Exception:
                    result.append(text.decode("latin1", errors="ignore"))
            else:
                result.append(str(text))
        return "".join(result)

    def _extract_body(self, msg) -> str:
        """Extracts plain text content from an email message."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get("Content-Disposition"))
                if ctype == "text/plain" and "attachment" not in cdispo:
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        body += payload.decode(charset, errors="ignore") + "\n"
                    except Exception:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="ignore")
            except Exception:
                body = str(msg.get_payload())

        return body.strip()

    def scan_inbox(self, hours_back: int = 24) -> List[ParsedEmail]:
        """
        Scans IMAP inbox for incoming messages in the past N hours,
        classifies them, and updates application_tracker.csv.
        """
        if not IMAPClient:
            logger.warning("IMAPClient is not installed. Skipping inbox scan.")
            return []

        if not self.config.imap_username or not self.config.imap_password:
            logger.info("IMAP credentials not configured. Skipping active inbox scan.")
            return []

        parsed_emails: List[ParsedEmail] = []
        since_date = datetime.now() - timedelta(hours=hours_back)

        try:
            with IMAPClient(self.config.imap_server, port=self.config.imap_port, ssl=self.config.imap_use_ssl) as client:
                client.login(self.config.imap_username, self.config.imap_password)
                client.select_folder("INBOX", readonly=True)

                # Search messages since date
                messages = client.search(["SINCE", since_date.strftime("%d-%b-%Y")])
                logger.info(f"Found {len(messages)} recent emails in inbox since {since_date.strftime('%Y-%m-%d')}")

                if not messages:
                    return []

                response = client.fetch(messages, ["BODY.PEEK[]", "ENVELOPE"])
                for uid, data in response.items():
                    raw_msg = data.get(b"BODY[]") or data.get(b"BODY.PEEK[]")
                    if not raw_msg:
                        continue

                    msg = email.message_from_bytes(raw_msg)
                    subject = self._decode_str(msg.get("Subject", ""))
                    sender = self._decode_str(msg.get("From", ""))
                    date_str = msg.get("Date", "")
                    body = self._extract_body(msg)

                    # Classify email
                    category, conf, action = self.llm.classify_email(
                        subject=subject,
                        sender=sender,
                        body=body
                    )

                    parsed_item = ParsedEmail(
                        uid=uid,
                        sender=sender,
                        subject=subject,
                        date_str=date_str,
                        body_text=body[:500],
                        classification=category,
                        confidence=conf,
                        action_item=action
                    )

                    # Correlate with tracked applications
                    self._correlate_and_update(parsed_item)
                    parsed_emails.append(parsed_item)

        except Exception as e:
            logger.error(f"Error scanning IMAP inbox: {e}")

        return parsed_emails

    def _correlate_and_update(self, item: ParsedEmail):
        """Matches email to company and updates tracker status."""
        apps = self.tracker.get_all_applications()
        for app in apps:
            company = str(app.get("company", "")).strip()
            if not company or len(company) < 3:
                continue

            combined = f"{item.sender} {item.subject} {item.body_text}".lower()
            if company.lower() in combined:
                item.matched_company = company
                new_status = item.classification
                self.tracker.update_status_by_company(
                    company_name=company,
                    new_status=new_status,
                    email_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    notes=f"Email: '{item.subject}' | Action: {item.action_item}"
                )
                logger.info(f"Updated status for application '{company}' to '{new_status}'")
                break
