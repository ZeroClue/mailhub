# 0003: local credentials use strict filesystem permissions

Configuration and credential state are stored under the user's XDG config and state directories with mode `0600`, atomic updates, and a cross-process refresh lock. OAuth uses PKCE and one-time state. Generic mail accounts use OAuth where offered and app passwords only as a fallback.

This is a pragmatic single-user local-tool model, not isolation from malicious processes running as the same Unix user.
