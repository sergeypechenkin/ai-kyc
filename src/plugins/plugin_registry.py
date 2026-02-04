"""Plugin registry for managing shared plugins."""

from typing import Any

from semantic_kernel import Kernel

from src.plugins.base_plugin import KycPlugin


class PluginRegistry:
    """Registry for managing plugin instances.

    Provides plugin discovery, instantiation, and injection into kernels.
    """

    def __init__(self):
        """Initialize the registry."""
        self._plugins: dict[str, KycPlugin] = {}
        self._plugin_classes: dict[str, type[KycPlugin]] = {}

    def register_class(self, plugin_class: type[KycPlugin]) -> None:
        """Register a plugin class for later instantiation.

        Args:
            plugin_class: The plugin class to register
        """
        if not hasattr(plugin_class, "name"):
            raise ValueError(f"{plugin_class.__name__} must define a 'name' attribute")
        self._plugin_classes[plugin_class.name] = plugin_class

    def register(self, plugin: KycPlugin) -> None:
        """Register a plugin instance.

        Args:
            plugin: The plugin instance to register
        """
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> KycPlugin | None:
        """Get a plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None
        """
        return self._plugins.get(name)

    def get_all(self) -> list[KycPlugin]:
        """Get all registered plugin instances."""
        return list(self._plugins.values())

    def create(
        self,
        name: str,
        **dependencies: Any,
    ) -> KycPlugin:
        """Create a plugin instance from a registered class.

        Args:
            name: Plugin name
            **dependencies: Dependencies to inject

        Returns:
            Created plugin instance
        """
        if name not in self._plugin_classes:
            raise ValueError(f"Plugin class '{name}' not registered")

        plugin = self._plugin_classes[name](**dependencies)
        self.register(plugin)
        return plugin

    def add_to_kernel(
        self,
        kernel: Kernel,
        plugin_names: list[str] | None = None,
    ) -> None:
        """Add plugins to a Semantic Kernel instance.

        Args:
            kernel: The kernel to add plugins to
            plugin_names: Specific plugins to add, or None for all
        """
        plugins_to_add = (
            [self._plugins[name] for name in plugin_names if name in self._plugins]
            if plugin_names
            else self._plugins.values()
        )

        for plugin in plugins_to_add:
            kernel.add_plugin(plugin, plugin.name)
