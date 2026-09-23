# 0002: adapters advertise capabilities

Accounts advertise the domains and operations their adapter supports. Gmail, Graph, and IMAP/SMTP are mail adapters; calendar, contact, and task support is added independently through provider APIs or CalDAV/CardDAV.

Mailhub normalizes common operations but preserves provider-specific behavior and search syntax.
