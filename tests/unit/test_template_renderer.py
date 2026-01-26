"""Tests for template renderer service."""
import pytest
import asyncio

from src.core.template_renderer import TemplateRenderer, CircularIncludeError


def await_sync(coro):
    """Run async function synchronously for tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestTemplateRenderer:
    """Test TemplateRenderer."""

    def test_render_simple_template(self):
        """render returns content with variables resolved."""
        async def get_content(name, version):
            return "Hello ${node.hostname}!"

        renderer = TemplateRenderer(get_content)
        context = {"node": {"hostname": "server-01"}}

        result = await_sync(renderer.render("test", None, context))

        assert result == "Hello server-01!"

    def test_render_with_includes(self):
        """render resolves include directives."""
        templates = {
            "main": "Start\n${include:footer}\nEnd",
            "footer": "-- Footer --",
        }

        async def get_content(name, version):
            return templates[name]

        renderer = TemplateRenderer(get_content)

        result = await_sync(renderer.render("main", None, {}))

        assert result == "Start\n-- Footer --\nEnd"

    def test_render_nested_includes(self):
        """render handles nested includes."""
        templates = {
            "main": "${include:level1}",
            "level1": "L1[${include:level2}]",
            "level2": "L2",
        }

        async def get_content(name, version):
            return templates[name]

        renderer = TemplateRenderer(get_content)

        result = await_sync(renderer.render("main", None, {}))

        assert result == "L1[L2]"

    def test_render_circular_include_raises(self):
        """render raises CircularIncludeError for circular includes."""
        templates = {
            "a": "${include:b}",
            "b": "${include:a}",
        }

        async def get_content(name, version):
            return templates[name]

        renderer = TemplateRenderer(get_content)

        with pytest.raises(CircularIncludeError):
            await_sync(renderer.render("a", None, {}))

    def test_render_with_versioned_include(self):
        """render resolves versioned includes."""
        calls = []

        async def get_content(name, version):
            calls.append((name, version))
            return f"Content of {name}:{version}"

        renderer = TemplateRenderer(get_content)

        await_sync(renderer.render("main", None, {}, content="${include:base:v2.1}"))

        assert ("base", "v2.1") in calls

    def test_render_max_include_depth(self):
        """render raises MaxIncludeDepthError when depth exceeds limit."""
        from src.core.template_renderer import MaxIncludeDepthError

        # Create a chain of 15 includes (exceeds MAX_INCLUDE_DEPTH of 10)
        templates = {f"level{i}": f"${{include:level{i+1}}}" for i in range(15)}
        templates["level15"] = "end"

        async def get_content(name, version):
            return templates.get(name, "")

        renderer = TemplateRenderer(get_content)

        with pytest.raises(MaxIncludeDepthError):
            await_sync(renderer.render("level0", None, {}))

    def test_render_with_content_parameter(self):
        """render uses content parameter instead of fetching."""
        async def get_content(name, version):
            raise Exception("Should not be called")

        renderer = TemplateRenderer(get_content)
        context = {"node": {"hostname": "test-host"}}

        result = await_sync(renderer.render(
            "ignored", None, context, content="Host: ${node.hostname}"
        ))

        assert result == "Host: test-host"

    def test_render_includes_then_variables(self):
        """render resolves includes first, then variables."""
        templates = {
            "main": "Hello ${include:greeting}",
            "greeting": "${node.name}!",
        }

        async def get_content(name, version):
            return templates[name]

        renderer = TemplateRenderer(get_content)
        context = {"node": {"name": "World"}}

        result = await_sync(renderer.render("main", None, context))

        assert result == "Hello World!"

    def test_render_multiple_same_includes(self):
        """render handles multiple includes of the same template."""
        templates = {
            "main": "Header: ${include:footer}\nBody\nFooter: ${include:footer}",
            "footer": "---END---",
        }

        async def get_content(name, version):
            return templates[name]

        renderer = TemplateRenderer(get_content)

        result = await_sync(renderer.render("main", None, {}))

        assert result == "Header: ---END---\nBody\nFooter: ---END---"
        # Count occurrences to verify both were replaced
        assert result.count("---END---") == 2

    def test_render_include_not_found(self):
        """render raises RuntimeError with context when include fails."""
        templates = {
            "main": "Start ${include:missing} End",
        }

        async def get_content(name, version):
            if name not in templates:
                raise FileNotFoundError(f"Template {name} not found")
            return templates[name]

        renderer = TemplateRenderer(get_content)

        with pytest.raises(RuntimeError, match="Failed to load included template 'missing'"):
            await_sync(renderer.render("main", None, {}))
