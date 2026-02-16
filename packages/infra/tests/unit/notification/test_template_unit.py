"""Template engine unit tests."""

from datetime import datetime
from pathlib import Path

import pytest
from ditto_infra.services.notification.message import (
    Notification,
    NotificationLevel,
)
from ditto_infra.services.notification.template import TemplateEngine
from jinja2 import TemplateNotFound


class TestTemplateEngine:
    """TemplateEngine tests."""

    def test_init_with_paths(self, tmp_path: Path) -> None:
        """Test initialization with template paths."""
        engine = TemplateEngine([tmp_path])
        assert engine is not None

    def test_render_basic_template(self, tmp_path: Path) -> None:
        """Test rendering a basic template."""
        # Create test template
        template_file = tmp_path / "test_email.j2"
        template_file.write_text("Hello {{ name }}!")

        engine = TemplateEngine([tmp_path])

        message = Notification(
            template="test",
            context={"name": "World"},
            level=NotificationLevel.INFO,
        )

        result = engine.render(message, "email")
        assert result == "Hello World!"

    def test_render_with_level(self, tmp_path: Path) -> None:
        """Test rendering with notification level."""
        template_file = tmp_path / "alert_telegram.j2"
        template_file.write_text("Level: {{ level }}")

        engine = TemplateEngine([tmp_path])

        message = Notification(
            template="alert",
            context={},
            level=NotificationLevel.ERROR,
        )

        result = engine.render(message, "telegram")
        assert result == "Level: error"

    def test_render_with_timestamp(self, tmp_path: Path) -> None:
        """Test rendering with timestamp."""
        template_file = tmp_path / "event_email.j2"
        template_file.write_text("Time: {{ timestamp }}")

        engine = TemplateEngine([tmp_path])

        now = datetime.now()
        message = Notification(
            template="event",
            context={},
            level=NotificationLevel.INFO,
            timestamp=now,
        )

        result = engine.render(message, "email")
        assert "Time:" in result
        assert str(now) in result

    def test_template_fallback(self, tmp_path: Path) -> None:
        """Test template fallback to secondary path."""
        # Primary path - no template
        primary = tmp_path / "primary"
        primary.mkdir()

        # Secondary path - has template
        secondary = tmp_path / "secondary"
        secondary.mkdir()
        template_file = secondary / "fallback_email.j2"
        template_file.write_text("Fallback content")

        engine = TemplateEngine([primary, secondary])

        message = Notification(
            template="fallback",
            context={},
            level=NotificationLevel.INFO,
        )

        result = engine.render(message, "email")
        assert result == "Fallback content"

    def test_template_not_found(self, tmp_path: Path) -> None:
        """Test error when template is not found."""
        engine = TemplateEngine([tmp_path])

        message = Notification(
            template="nonexistent",
            context={},
            level=NotificationLevel.INFO,
        )

        # Jinja2 raises TemplateNotFound when template doesn't exist
        with pytest.raises(TemplateNotFound):
            engine.render(message, "email")

    def test_render_with_complex_context(self, tmp_path: Path) -> None:
        """Test rendering with complex context data."""
        template_file = tmp_path / "complex_email.j2"
        template_file.write_text(
            "Dataset: {{ dataset }}, Date: {{ date }}, Errors: {{ errors|length }}"
        )

        engine = TemplateEngine([tmp_path])

        message = Notification(
            template="complex",
            context={
                "dataset": "stock_daily",
                "date": "2026-01-22",
                "errors": ["error1", "error2", "error3"],
            },
            level=NotificationLevel.ERROR,
        )

        result = engine.render(message, "email")
        assert "Dataset: stock_daily" in result
        assert "Date: 2026-01-22" in result
        assert "Errors: 3" in result
