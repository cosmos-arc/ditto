"""Template engine for notification rendering."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ditto_foundation.notification.message import Notification


class TemplateEngine:
    """
    Jinja2 template engine for multi-channel notification rendering.

    Supports template fallback and channel-specific rendering.
    """

    def __init__(self, template_paths: list[Path]) -> None:
        """
        Initialize template engine with search paths.

        Args:
            template_paths: List of template directories (highest priority first).
                           Application templates can override Foundation templates.

        """
        # Convert Path objects to strings for Jinja2
        path_strings = [str(p) for p in template_paths]

        self._env = Environment(
            loader=FileSystemLoader(path_strings),
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=False,  # Use sync rendering for now
        )

    def render(
        self,
        message: Notification,
        channel: str,  # "email", "telegram", "webhook"
    ) -> str:
        """
        Render message for specific channel.

        Template lookup: {template_name}_{channel}.j2
        Example: "dq_failure_email.html.j2"

        Args:
            message: Notification message with template name and context.
            channel: Channel identifier (e.g., "email", "telegram").

        Returns:
            Rendered content string.

        Raises:
            TemplateNotFound: If template file is not found in any search path.

        """
        # Build template filename: {template}_{channel}.j2
        template_name = f"{message.template}_{channel}.j2"

        # Get template (will raise TemplateNotFound if not found)
        template = self._env.get_template(template_name)

        # Build render context with message metadata
        render_context: dict[str, Any] = {
            "level": message.level.value,
            "timestamp": message.timestamp,
            **message.context,
        }

        # Render and return
        return template.render(**render_context)


__all__ = ["TemplateEngine"]
