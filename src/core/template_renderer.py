"""Template rendering service with include resolution."""
import re
from typing import Any, Callable, Awaitable

from src.core.variable_resolver import VariableResolver


class CircularIncludeError(Exception):
    """Raised when circular template includes are detected."""
    pass


class MaxIncludeDepthError(Exception):
    """Raised when include depth exceeds maximum."""
    pass


class TemplateRenderer:
    """Render templates with includes and variable substitution.

    The rendering process:
    1. Fetch template content (or use provided content)
    2. Recursively resolve ${include:template-name} directives
    3. Apply variable substitution using VariableResolver

    Include syntax:
        ${include:template-name}      - Include latest version
        ${include:template-name:v2}   - Include major version 2
        ${include:template-name:v2.1} - Include specific version 2.1
    """

    INCLUDE_PATTERN = re.compile(
        r'\$\{include:([a-zA-Z0-9_-]+)(?::v?(\d+)(?:\.(\d+))?)?\}'
    )
    MAX_INCLUDE_DEPTH = 10

    def __init__(
        self,
        get_content: Callable[[str, str | None], Awaitable[str]],
    ):
        """Initialize with content fetcher function.

        Args:
            get_content: Async function that fetches template content.
                         Takes (template_name, version) and returns content string.
        """
        self._get_content = get_content

    async def render(
        self,
        template_name: str,
        version: str | None,
        context: dict[str, dict[str, Any]],
        content: str | None = None,
    ) -> str:
        """Render template with includes and variables resolved.

        Args:
            template_name: Name of the template to render
            version: Optional version string (e.g., "v1.2")
            context: Variable context for substitution
            content: Optional content to use instead of fetching

        Returns:
            Fully rendered template content

        Raises:
            CircularIncludeError: If circular includes detected
            MaxIncludeDepthError: If include depth exceeds limit
        """
        if content is None:
            content = await self._get_content(template_name, version)

        # Resolve includes first
        content = await self._resolve_includes(content, set())

        # Then resolve variables
        resolver = VariableResolver(context)
        content = resolver.resolve(content)

        return content

    async def _resolve_includes(
        self,
        content: str,
        visited: set[str],
        depth: int = 0,
    ) -> str:
        """Recursively resolve ${include:...} references.

        Args:
            content: Template content with include directives
            visited: Set of already-visited template references
            depth: Current include depth

        Returns:
            Content with all includes resolved
        """
        if depth > self.MAX_INCLUDE_DEPTH:
            raise MaxIncludeDepthError(
                f"Include depth exceeded {self.MAX_INCLUDE_DEPTH}"
            )

        matches = list(self.INCLUDE_PATTERN.finditer(content))
        if not matches:
            return content

        # Build result using positional replacement
        result_parts = []
        last_end = 0

        for match in matches:
            template_name, major, minor = match.groups()

            # Build version string
            version = None
            if major and minor:
                version = f"v{major}.{minor}"
            elif major:
                version = f"v{major}"

            ref_key = f"{template_name}:{version}" if version else template_name

            if ref_key in visited:
                raise CircularIncludeError(
                    f"Circular include detected: {ref_key}"
                )

            visited_copy = visited | {ref_key}

            try:
                included_content = await self._get_content(template_name, version)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load included template '{template_name}'"
                    f"{f' version {version}' if version else ''}: {e}"
                ) from e

            included_content = await self._resolve_includes(
                included_content, visited_copy, depth + 1
            )

            # Append content before this match, then the resolved include
            result_parts.append(content[last_end:match.start()])
            result_parts.append(included_content)
            last_end = match.end()

        # Append remaining content after last match
        result_parts.append(content[last_end:])

        return "".join(result_parts)
