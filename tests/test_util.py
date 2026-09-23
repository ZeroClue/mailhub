"""Unit tests for mailhub.util module."""

from __future__ import annotations

import pytest

from mailhub.util import build_mime, html_to_text, split_addrs


class TestHtmlToText:
    def test_empty_string_returns_empty(self):
        assert html_to_text("") == ""
        assert html_to_text(None) == ""

    def test_strips_html_tags(self):
        html = "<p>Hello <b>world</b></p>"
        assert html_to_text(html) == "Hello world"

    def test_preserves_block_structure(self):
        html = "<div>Line 1</div><p>Line 2</p>"
        result = html_to_text(html)
        assert "Line 1" in result
        assert "Line 2" in result

    def test_removes_scripts_and_styles(self):
        html = "<script>alert('xss')</script><p>Safe</p><style>body{color:red}</style>"
        result = html_to_text(html)
        assert "alert" not in result
        assert "Safe" in result
        assert "color:red" not in result

    def test_decodes_html_entities(self):
        html = "<p>Hello&Goodbye</p>"
        result = html_to_text(html)
        assert "Hello&Goodbye" == result

    def test_normalizes_whitespace(self):
        html = "<p>Hello   world</p>\n\n\n<p>Again</p>"
        result = html_to_text(html)
        assert "Hello world" in result
        assert result.count("Again") == 1


class TestSplitAddrs:
    def test_empty_returns_empty_list(self):
        assert split_addrs("") == []
        assert split_addrs("   ") == []

    def test_single_address(self):
        assert split_addrs("user@example.com") == ["user@example.com"]

    def test_multiple_addresses(self):
        assert split_addrs("a@a.com, b@b.com, c@c.com") == ["a@a.com", "b@b.com", "c@c.com"]

    def test_handles_display_names(self):
        result = split_addrs('"John Doe" <john@example.com>, jane@example.com')
        assert "john@example.com" in result
        assert "jane@example.com" in result

    def test_handles_angle_brackets(self):
        result = split_addrs("<user@example.com>")
        assert result == ["user@example.com"]


class TestBuildMime:
    def test_builds_text_only_message(self):
        msg = build_mime(
            from_addr="me@example.com",
            to=["you@example.com"],
            subject="Test",
            text_body="Hello",
        )
        assert msg["From"] == "me@example.com"
        assert msg["To"] == "you@example.com"
        assert msg["Subject"] == "Test"
        assert msg.get_content().strip() == "Hello"

    def test_builds_html_only_message(self):
        msg = build_mime(
            from_addr="me@example.com",
            to=["you@example.com"],
            subject="Test",
            html_body="<p>Hello</p>",
        )
        assert msg.get_content().strip() == "<p>Hello</p>"
        assert msg.get_content_subtype() == "html"

    def test_builds_multipart_alternative(self):
        msg = build_mime(
            from_addr="me@example.com",
            to=["you@example.com"],
            subject="Test",
            text_body="Hello",
            html_body="<p>Hello</p>",
        )
        assert msg.is_multipart()
        parts = list(msg.walk())
        # Should have the outer message + the alternative part + the two text parts
        assert len(parts) >= 3

    def test_includes_cc_and_bcc(self):
        msg = build_mime(
            from_addr="me@example.com",
            to=["you@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            subject="Test",
            text_body="Hello",
        )
        assert msg["Cc"] == "cc@example.com"
        assert msg["Bcc"] == "bcc@example.com"

    def test_includes_reply_headers(self):
        msg = build_mime(
            from_addr="me@example.com",
            to=["you@example.com"],
            subject="Re: Test",
            text_body="Hello",
            in_reply_to="<original@example.com>",
            references=["<ref1@example.com>", "<ref2@example.com>"],
        )
        assert msg["In-Reply-To"] == "<original@example.com>"
        assert msg["References"] == "<ref1@example.com> <ref2@example.com>"

    def test_includes_message_id(self):
        msg = build_mime(
            from_addr="me@example.com",
            to=["you@example.com"],
            subject="Test",
            text_body="Hello",
            message_id="<myid@example.com>",
        )
        assert msg["Message-ID"] == "<myid@example.com>"


