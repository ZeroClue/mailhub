"""IMAP/SMTP adapter for Mailhub."""

from __future__ import annotations

import email
import imaplib
import re
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Optional

from .core import CoreError, SendDenied


@dataclass
class IMAPConfig:
    """IMAP/SMTP connection configuration."""
    # IMAP settings
    host: str
    port: int = 993
    username: str = ""
    password: str = ""  # can be app password or regular password
    use_ssl: bool = True
    use_starttls: bool = False
    
    # SMTP settings (optional, defaults to IMAP settings)
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_use_starttls: Optional[bool] = None
    
    # Auth method
    auth_method: str = "plain"  # "plain", "oauth2", "app_password"
    
    def get_smtp_host(self) -> str:
        return self.smtp_host or self.host.replace('imap', 'smtp')
    
    def get_smtp_port(self) -> int:
        return self.smtp_port or (465 if (self.smtp_use_ssl or self.use_ssl) else 587)
    
    def get_smtp_username(self) -> str:
        return self.smtp_username or self.username
    
    def get_smtp_password(self) -> str:
        return self.smtp_password or self.password
    
    def get_smtp_use_ssl(self) -> bool:
        if self.smtp_use_ssl is not None:
            return self.smtp_use_ssl
        return self.use_ssl
    
    def get_smtp_use_starttls(self) -> bool:
        if self.smtp_use_starttls is not None:
            return self.smtp_use_starttls
        return self.use_starttls


class IMAPAdapter:
    """IMAP adapter for mail operations."""

    def __init__(self, core: Any):
        self._core = core
        self._configs: dict[str, IMAPConfig] = {}

    def _get_config(self, alias: str) -> IMAPConfig:
        """Get IMAP config for account - per-account config with global fallback."""
        if alias not in self._configs:
            account = self._core._config.account(alias)
            creds = self._core._load_credentials(alias)
            
            # Get global [imap] section as fallback
            global_raw = self._core._config._raw.get("imap", {})
            
            # Get per-account settings from account's raw config
            account_raw = self._core._config._raw.get("accounts", {}).get(alias, {})
            
            # Merge: per-account settings override global
            raw = {**global_raw, **account_raw}
            
            self._configs[alias] = IMAPConfig(
                host=raw.get("host", raw.get("imap_host", "imap.gmail.com")),
                port=raw.get("port", raw.get("imap_port", 993)),
                username=creds.client_id or account.email or raw.get("imap_username", ""),
                password=creds.client_secret or creds.refresh_token or raw.get("imap_password", ""),
                use_ssl=raw.get("use_ssl", raw.get("imap_use_ssl", True)),
                use_starttls=raw.get("use_starttls", raw.get("imap_use_starttls", False)),
                smtp_host=raw.get("smtp_host", raw.get("imap_smtp_host")),
                smtp_port=raw.get("smtp_port", raw.get("imap_smtp_port")),
                smtp_username=raw.get("smtp_username", raw.get("imap_smtp_username")),
                smtp_password=raw.get("smtp_password", raw.get("imap_smtp_password")),
                smtp_use_ssl=raw.get("smtp_use_ssl", raw.get("imap_smtp_use_ssl")),
                smtp_use_starttls=raw.get("smtp_use_starttls", raw.get("imap_smtp_use_starttls")),
                auth_method=raw.get("auth_method", raw.get("imap_auth_method", "plain")),
            )
        return self._configs[alias]

    def _connect_imap(self, config: IMAPConfig) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        """Create IMAP connection."""
        if config.use_ssl:
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(config.host, config.port, ssl_context=ctx, timeout=config.timeout)
        else:
            conn = imaplib.IMAP4(config.host, config.port, timeout=config.timeout)
            if config.use_starttls:
                conn.starttls()
        
        # Support different auth methods
        if config.auth_method == "oauth2":
            # OAuth2 auth would go here (XOAUTH2)
            raise NotImplementedError("OAuth2 auth not yet implemented for IMAP")
        else:
            # Plain auth (username/password or app password)
            conn.login(config.username, config.password)
        return conn

    def _connect_smtp(self, config: IMAPConfig) -> smtplib.SMTP:
        """Create SMTP connection."""
        smtp_host = config.get_smtp_host()
        smtp_port = config.get_smtp_port()
        smtp_user = config.get_smtp_username()
        smtp_pass = config.get_smtp_password()
        
        if config.get_smtp_use_ssl() and smtp_port == 465:
            conn = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=config.timeout)
        else:
            conn = smtplib.SMTP(smtp_host, smtp_port, timeout=config.timeout)
            if config.get_smtp_use_starttls() or smtp_port == 587:
                conn.starttls()
        
        if config.auth_method == "oauth2":
            raise NotImplementedError("OAuth2 auth not yet implemented for SMTP")
        else:
            conn.login(smtp_user, smtp_pass)
        return conn

    def _parse_message(self, msg_data: bytes) -> dict[str, Any]:
        """Parse raw email message."""
        msg = email.message_from_bytes(msg_data)
        
        # Extract headers
        headers = {}
        for key in ['Message-ID', 'Subject', 'From', 'To', 'Cc', 'Bcc', 'Date', 'In-Reply-To', 'References']:
            val = msg.get(key)
            if val:
                headers[key.lower().replace('-', '_')] = val
        
        # Extract body
        text_body = ""
        html_body = ""
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = part.get('Content-Disposition', '')
                
                if content_type == 'text/plain' and 'attachment' not in disposition:
                    text_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                elif content_type == 'text/html' and 'attachment' not in disposition:
                    html_body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                elif 'attachment' in disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append({
                            'filename': filename,
                            'content_type': content_type,
                            'size': len(part.get_payload(decode=True) or b'')
                        })
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
                if content_type == 'text/html':
                    html_body = text
                else:
                    text_body = text
        
        return {
            'id': headers.get('message_id', '').strip('<>'),
            'thread_id': None,
            'headers': headers,
            'text_body': text_body,
            'html_body': html_body,
            'attachments': attachments,
            'labels': [],
            'flags': [],
        }

    def folders(self, alias: str) -> list[dict[str, Any]]:
        """List IMAP folders."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            status, folders = conn.list()
            if status != 'OK':
                raise CoreError(f"Failed to list folders: {folders}")
            
            result = []
            for folder in folders:
                folder = folder.decode('utf-8')
                match = re.search(r'"([^"]*)"$', folder)
                if match:
                    name = match.group(1)
                    result.append({'name': name, 'id': name})
            return result
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def search(self, alias: str, query: str, max_results: int = 50, page_token: str | None = None) -> dict[str, Any]:
        """Search messages using IMAP SEARCH."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            folder = page_token or 'INBOX'
            status, _ = conn.select(folder, readonly=True)
            if status != 'OK':
                raise CoreError(f"Failed to select folder {folder}")
            
            imap_query = self._parse_search_query(query)
            
            status, data = conn.search(None, imap_query)
            if status != 'OK':
                raise CoreError(f"Search failed: {data}")
            
            msg_ids = data[0].split() if data[0] else []
            msg_ids = msg_ids[-max_results:]
            
            messages = []
            for msg_id in reversed(msg_ids):
                status, data = conn.fetch(msg_id, '(RFC822)')
                if status == 'OK' and data:
                    msg_data = data[0][1]
                    parsed = self._parse_message(msg_data)
                    messages.append(parsed)
            
            return {
                'messages': messages,
                'next_page_token': None,
            }
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _parse_search_query(self, query: str) -> str:
        """Convert simple query to IMAP SEARCH criteria."""
        if not query.strip():
            return 'ALL'
        
        parts = []
        tokens = query.split()
        
        for token in tokens:
            if ':' in token:
                field, value = token.split(':', 1)
                field = field.lower()
                if field == 'from':
                    parts.append(f'FROM "{value}"')
                elif field == 'to':
                    parts.append(f'TO "{value}"')
                elif field == 'subject':
                    parts.append(f'SUBJECT "{value}"')
                elif field == 'before':
                    parts.append(f'BEFORE "{value}"')
                elif field == 'after':
                    parts.append(f'SINCE "{value}"')
                elif field == 'hasattachment':
                    parts.append('HAS attachment')
                else:
                    parts.append(f'BODY "{value}"')
            else:
                parts.append(f'BODY "{token}"')
        
        return ' '.join(parts) if parts else 'ALL'

    def get(self, alias: str, message_id: str) -> dict[str, Any]:
        """Get a message by ID."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            status, data = conn.search(None, f'HEADER Message-ID "{message_id}"')
            if status != 'OK' or not data[0]:
                raise CoreError(f"Message not found: {message_id}")
            
            msg_num = data[0].split()[0]
            status, data = conn.fetch(msg_num, '(RFC822)')
            if status != 'OK' or not data:
                raise CoreError(f"Failed to fetch message: {message_id}")
            
            msg_data = data[0][1]
            return self._parse_message(msg_data)
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def send(self, alias: str, to: list[str], cc: list[str], bcc: list[str],
             subject: str, text_body: str | None, html_body: str | None,
             in_reply_to: str | None, references: list[str], confirm: bool) -> dict[str, Any]:
        """Send message via SMTP."""
        if not confirm:
            raise SendDenied("send requires confirm=true")
        
        config = self._get_config(alias)
        
        msg = EmailMessage()
        msg['From'] = config.get_smtp_username()
        msg['To'] = ', '.join(to)
        if cc:
            msg['Cc'] = ', '.join(cc)
        msg['Subject'] = subject
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
        if references:
            msg['References'] = ' '.join(references)
        
        if text_body:
            msg.set_content(text_body)
        if html_body:
            if text_body:
                msg.make_mixed()
            msg.add_alternative(html_body, subtype='html')
        
        all_recipients = to + cc + bcc
        
        conn = self._connect_smtp(config)
        try:
            conn.send_message(msg, from_addr=config.get_smtp_username(), to_addrs=all_recipients)
            return {'id': 'sent', 'status': 'sent'}
        finally:
            try:
                conn.quit()
            except Exception:
                pass

    def draft(self, alias: str, to: list[str], cc: list[str], bcc: list[str],
              subject: str, text_body: str | None, html_body: str | None,
              in_reply_to: str | None, references: list[str]) -> dict[str, Any]:
        """Create draft - save to Drafts folder via IMAP."""
        config = self._get_config(alias)
        
        msg = EmailMessage()
        msg['From'] = config.get_smtp_username()
        msg['To'] = ', '.join(to)
        if cc:
            msg['Cc'] = ', '.join(cc)
        msg['Subject'] = subject
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
        if references:
            msg['References'] = ' '.join(references)
        
        if text_body:
            msg.set_content(text_body)
        if html_body:
            if text_body:
                msg.make_mixed()
            msg.add_alternative(html_body, subtype='html')
        
        conn = self._connect_imap(config)
        try:
            conn.select('Drafts', readonly=False)
            msg_bytes = msg.as_bytes()
            conn.append('Drafts', '', imaplib.Time2Internaldate(time.time()), msg_bytes)
            return {'id': 'draft', 'status': 'draft'}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def move(self, alias: str, message_id: str, destination: str) -> dict[str, Any]:
        """Move message to folder."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            status, data = conn.search(None, f'HEADER Message-ID "{message_id}"')
            if status != 'OK' or not data[0]:
                raise CoreError(f"Message not found: {message_id}")
            
            msg_num = data[0].split()[0]
            conn.copy(msg_num, destination)
            conn.store(msg_num, '+FLAGS', '\\Deleted')
            conn.expunge()
            return {'id': message_id, 'status': 'moved'}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def trash(self, alias: str, message_id: str) -> dict[str, Any]:
        """Move message to Trash."""
        return self.move(alias, message_id, 'Trash')

    def close(self) -> None:
        """Close any open connections."""
        self._configs.clear()


def create_imap_adapter(core: Any) -> IMAPAdapter:
    """Factory function for Core."""
    return IMAPAdapter(core)
