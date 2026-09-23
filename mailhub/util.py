"""Shared utilities for Mailhub."""

from __future__ import annotations

import email
import re
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import unescape
from html.parser import HTMLParser
from typing import Sequence


class _HTMLToTextParser(HTMLParser):
    """HTML parser that extracts text content, preserving block structure."""
    
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip_tags = {"script", "style", "head", "title", "meta", "noscript"}
        self.block_tags = {"div", "p", "br", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "hr", "section", "article", "header", "footer", "nav", "main", "aside", "table", "ul", "ol"}
        self._skip_depth = 0
    
    def handle_starttag(self, tag: str, attrs):
        tag_lower = tag.lower()
        if tag_lower in self.skip_tags:
            self._skip_depth += 1
        elif tag_lower in self.block_tags:
            self.out.append("\n")
        elif tag_lower == "br":
            self.out.append("\n")
    
    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in self.skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag_lower in self.block_tags:
            self.out.append("\n")
    
    def handle_data(self, data: str):
        if self._skip_depth == 0 and data:
            self.out.append(data)


def html_to_text(html: str) -> str:
    """
    Convert HTML to plain text.
    
    Strips tags, decodes entities, and normalizes whitespace.
    """
    if not html:
        return ""
    parser = _HTMLToTextParser()
    parser.feed(html)
    text = "".join(parser.out)
    # Decode HTML entities
    text = unescape(text)
    # Normalize whitespace
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split_addrs(addrs: str) -> list[str]:
    """
    Parse comma-separated email addresses.
    
    Handles display names in angle brackets.
    """
    if not addrs.strip():
        return []
    # Use email.utils.getaddresses for robust parsing
    parsed = email.utils.getaddresses([addrs])
    return [addr for _, addr in parsed if addr]


def build_mime(
    *,
    from_addr: str,
    to: Sequence[str],
    cc: Sequence[str] | None = None,
    bcc: Sequence[str] | None = None,
    subject: str,
    text_body: str | None = None,
    html_body: str | None = None,
    message_id: str | None = None,
    in_reply_to: str | None = None,
    references: Sequence[str] | None = None,
) -> EmailMessage:
    """
    Build a MIME email message.
    
    Returns an EmailMessage ready to send via SMTP or provider API.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject

    if message_id:
        msg["Message-ID"] = message_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = " ".join(references)

    # Build content using MIMEMultipart for proper multipart handling
    if text_body and html_body:
        # Create multipart/alternative
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.set_content(alt)
    elif html_body:
        msg.set_content(html_body, subtype="html", charset="utf-8")
    elif text_body:
        msg.set_content(text_body, subtype="plain", charset="utf-8")
    else:
        msg.set_content("", subtype="plain", charset="utf-8")

    return msg


