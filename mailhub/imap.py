"""IMAP/SMTP adapter for Mailhub."""

from __future__ import annotations

import email
import os
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
    timeout: int = 30
    
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
            
            # IMAP LIST response format: (flags) "delimiter" "name" or (flags) "delimiter" name
            # name can be quoted or unquoted
            folder_pattern = re.compile(
                r'\([^)]*\)\s+"([^"]+)"\s+"([^"]+)"$|\([^)]*\)\s+"([^"]+)"\s+(\S+)$'
            )
            
            result = []
            for folder in folders:
                folder = folder.decode('utf-8')
                match = folder_pattern.search(folder)
                if match:
                    # Group 2 is quoted name, group 4 is unquoted name
                    name = match.group(2) if match.group(2) else match.group(4)
                    result.append({'name': name, 'id': name})
            return result
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def folder_status(self, alias: str, folder_name: str) -> dict[str, Any]:
        """Get folder status (message counts, unseen, etc.) via IMAP STATUS."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            status, data = conn.status(folder_name, '(MESSAGES UNSEEN UIDNEXT UIDVALIDITY)')
            if status != 'OK':
                raise CoreError(f"Failed to get folder status: {data}")
            
            # Parse STATUS response: b'INBOX (MESSAGES 10 UNSEEN 2 UIDNEXT 15 UIDVALIDITY 123)'
            result = {'folder': folder_name}
            if data and data[0]:
                line = data[0].decode('utf-8')
                import re
                for key in ['MESSAGES', 'UNSEEN', 'UIDNEXT', 'UIDVALIDITY']:
                    match = re.search(rf'{key}\s+(\d+)', line)
                    if match:
                        result[key.lower()] = int(match.group(1))
            return result
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def folder_statuses(self, alias: str) -> list[dict[str, Any]]:
        """Get status for all folders."""
        folders = self.folders(alias)
        results = []
        for folder in folders:
            try:
                status = self.folder_status(alias, folder['name'])
                results.append(status)
            except Exception as e:
                results.append({'folder': folder['name'], 'error': str(e)})
        return results

    def get_special_use_folders(self, alias: str) -> dict[str, str]:
        """Detect special-use folders (RFC 6154) like Inbox, Sent, Drafts, Trash, Junk, Archive."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            status, folders = conn.list()
            if status != 'OK':
                return {}
            
            # Try XLIST for Gmail-style special use
            special_folders = {}
            try:
                status, xlist = conn.xlist('', '*')
                if status == 'OK':
                    for item in xlist:
                        decoded = item.decode('utf-8')
                        # XLIST response: (\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"
                        match = re.search(r'\\([^)]+)\)\s+"([^"]+)"\s+"([^"]+)"', decoded)
                        if match:
                            flags = match.group(1).split()
                            name = match.group(3)
                            flag_map = {
                                'Inbox': 'inbox',
                                'Sent': 'sent',
                                'Drafts': 'drafts',
                                'Trash': 'trash',
                                'Junk': 'junk',
                                'Archive': 'archive',
                            }
                            for flag in flags:
                                if flag in flag_map:
                                    special_folders[flag_map[flag]] = name
            except Exception:
                pass
            
            # Fallback: try common names
            if not special_folders:
                common_names = {
                    'inbox': ['INBOX', 'Inbox', 'inbox'],
                    'sent': ['Sent', 'Sent Items', 'Sent Messages', '[Gmail]/Sent Mail'],
                    'drafts': ['Drafts', 'Draft', '[Gmail]/Drafts'],
                    'trash': ['Trash', 'Deleted Items', 'Deleted Messages', '[Gmail]/Trash'],
                    'junk': ['Junk', 'Spam', 'Junk E-mail', '[Gmail]/Spam'],
                    'archive': ['Archive', 'Archives', '[Gmail]/All Mail'],
                }
                folder_names = [f['name'] for f in self.folders(alias)]
                for key, candidates in common_names.items():
                    for candidate in candidates:
                        if candidate in folder_names:
                            special_folders[key] = candidate
                            break
            
            return special_folders
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def set_message_flags(self, alias: str, message_ids: list[str], add_flags: list[str] = None, remove_flags: list[str] = None) -> dict[str, Any]:
        """Add or remove flags (\Seen, \Flagged, etc.) from messages."""
        if not add_flags and not remove_flags:
            return {'error': 'No flags specified'}
        
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        results = []
        try:
            # Search across common folders
            folders_to_search = ['INBOX', 'Sent', 'Drafts', 'Archive', 'Junk', 'Trash']
            for msg_id in message_ids:
                msg_num = None
                source_folder = None
                for folder in folders_to_search:
                    try:
                        status, _ = conn.select(folder, readonly=False)
                        if status != 'OK':
                            continue
                        status, data = conn.search(None, f'HEADER Message-ID "{msg_id}"')
                        if status == 'OK' and data[0]:
                            msg_num = data[0].split()[0]
                            source_folder = folder
                            break
                    except Exception:
                        continue
                
                if not msg_num:
                    results.append({'message_id': msg_id, 'status': 'not_found'})
                    continue
                
                # Build STORE commands - IMAP store takes command and flags separately
                if add_flags:
                    status, data = conn.store(msg_num, '+FLAGS', f'({" ".join(add_flags)})')
                    if status != 'OK':
                        results.append({'message_id': msg_id, 'status': 'failed', 'error': str(data)})
                        continue
                if remove_flags:
                    status, data = conn.store(msg_num, '-FLAGS', f'({" ".join(remove_flags)})')
                    if status != 'OK':
                        results.append({'message_id': msg_id, 'status': 'failed', 'error': str(data)})
                        continue
                if status == 'OK':
                    results.append({'message_id': msg_id, 'folder': source_folder, 'status': 'updated'})
                else:
                    results.append({'message_id': msg_id, 'status': 'failed', 'error': str(data)})
            
            return {'results': results}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def batch_move(self, alias: str, message_ids: list[str], destination: str) -> dict[str, Any]:
        """Move multiple messages to a folder."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        results = []
        try:
            folders_to_search = ['INBOX', 'Sent', 'Drafts', 'Archive', 'Junk', 'Trash']
            for msg_id in message_ids:
                msg_num = None
                for folder in folders_to_search:
                    try:
                        status, _ = conn.select(folder, readonly=False)
                        if status != 'OK':
                            continue
                        status, data = conn.search(None, f'HEADER Message-ID "{msg_id}"')
                        if status == 'OK' and data[0]:
                            msg_num = data[0].split()[0]
                            break
                    except Exception:
                        continue
                
                if not msg_num:
                    results.append({'message_id': msg_id, 'status': 'not_found'})
                    continue
                
                status, _ = conn.copy(msg_num, destination)
                if status == 'OK':
                    conn.store(msg_num, '+FLAGS', '\Deleted')
                    conn.expunge()
                    results.append({'message_id': msg_id, 'status': 'moved'})
                else:
                    results.append({'message_id': msg_id, 'status': 'failed'})
            
            return {'results': results}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def batch_delete(self, alias: str, message_ids: list[str]) -> dict[str, Any]:
        """Move multiple messages to Trash."""
        return self.batch_move(alias, message_ids, 'Trash')

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
            # Search across common folders since we don't know which folder the message is in
            folders_to_search = ['INBOX', 'Sent', 'Drafts', 'Archive', 'Junk', 'Trash']
            msg_num = None
            for folder in folders_to_search:
                try:
                    status, _ = conn.select(folder, readonly=True)
                    if status != 'OK':
                        continue
                    status, data = conn.search(None, f'HEADER Message-ID "{message_id}"')
                    if status == 'OK' and data[0]:
                        msg_num = data[0].split()[0]
                        break
                except Exception:
                    continue
            
            if not msg_num:
                raise CoreError(f"Message not found: {message_id}")
            
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
             in_reply_to: str | None, references: list[str], confirm: bool,
             attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Send message via SMTP with optional attachments."""
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
        
        # Handle attachments - use multipart/mixed
        if attachments:
            if text_body:
                msg.set_content(text_body)
            if html_body:
                if text_body:
                    msg.make_mixed()
                msg.add_alternative(html_body, subtype='html')
            
            for att in attachments:
                # Handle both dict and Attachment model
                if hasattr(att, 'model_dump'):
                    att = att.model_dump()
                file_path = att.get('path')
                filename = att.get('filename', os.path.basename(file_path))
                content_type = att.get('content_type', 'application/octet-stream')
                main_type, sub_type = content_type.split('/', 1) if '/' in content_type else ('application', 'octet-stream')
                
                with open(file_path, 'rb') as f:
                    msg.add_attachment(f.read(), maintype=main_type, subtype=sub_type, filename=filename)
        else:
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
              in_reply_to: str | None, references: list[str],
              attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Create draft - save to Drafts folder via IMAP with optional attachments."""
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
        
        # Handle attachments - use multipart/mixed
        if attachments:
            if text_body:
                msg.set_content(text_body)
            if html_body:
                if text_body:
                    msg.make_mixed()
                msg.add_alternative(html_body, subtype='html')
            
            for att in attachments:
                # Handle both dict and Attachment model
                if hasattr(att, 'model_dump'):
                    att = att.model_dump()
                file_path = att.get('path')
                filename = att.get('filename', os.path.basename(file_path))
                content_type = att.get('content_type', 'application/octet-stream')
                main_type, sub_type = content_type.split('/', 1) if '/' in content_type else ('application', 'octet-stream')
                
                with open(file_path, 'rb') as f:
                    msg.add_attachment(f.read(), maintype=main_type, subtype=sub_type, filename=filename)
        else:
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
            # Search across common folders since we don't know which folder the message is in
            folders_to_search = ['INBOX', 'Sent', 'Drafts', 'Archive', 'Junk', 'Trash']
            msg_num = None
            for folder in folders_to_search:
                try:
                    status, _ = conn.select(folder, readonly=False)
                    if status != 'OK':
                        continue
                    status, data = conn.search(None, f'HEADER Message-ID "{message_id}"')
                    if status == 'OK' and data[0]:
                        msg_num = data[0].split()[0]
                        break
                except Exception:
                    continue
            
            if not msg_num:
                raise CoreError(f"Message not found: {message_id}")
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

    def create_folder(self, alias: str, folder_name: str) -> dict[str, Any]:
        """Create a new IMAP folder."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            status, data = conn.create(folder_name)
            if status != 'OK':
                raise CoreError(f"Failed to create folder: {data}")
            return {'name': folder_name, 'status': 'created'}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def delete_folder(self, alias: str, folder_name: str) -> dict[str, Any]:
        """Delete an IMAP folder."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            status, data = conn.delete(folder_name)
            if status != 'OK':
                raise CoreError(f"Failed to delete folder: {data}")
            return {'name': folder_name, 'status': 'deleted'}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def rename_folder(self, alias: str, old_name: str, new_name: str) -> dict[str, Any]:
        """Rename an IMAP folder."""
        config = self._get_config(alias)
        config.timeout = 30
        conn = self._connect_imap(config)
        try:
            status, data = conn.rename(old_name, new_name)
            if status != 'OK':
                raise CoreError(f"Failed to rename folder: {data}")
            return {'old_name': old_name, 'new_name': new_name, 'status': 'renamed'}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def close(self) -> None:
        """Close any open connections."""
        self._configs.clear()


def create_imap_adapter(core: Any) -> IMAPAdapter:
    """Factory function for Core."""
    return IMAPAdapter(core)
