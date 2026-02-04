"""Base plugin class for KYC plugins."""

from abc import ABC
from typing import Any


class KycPlugin(ABC):
    """Base class for all KYC plugins.

    Plugins provide reusable functionality that can be shared across agents.
    They use Semantic Kernel's @kernel_function decorator for exposing
    functions to the AI model.
    """

    name: str
    description: str

    def __init__(self, **dependencies: Any):
        """Initialize the plugin with dependencies.

        Args:
            **dependencies: Named dependencies (repositories, services, etc.)
        """
        self._dependencies = dependencies

    def get_dependency(self, name: str) -> Any:
        """Get a dependency by name.

        Args:
            name: Name of the dependency

        Returns:
            The dependency instance

        Raises:
            KeyError: If dependency not found
        """
        if name not in self._dependencies:
            raise KeyError(f"Dependency '{name}' not found in plugin '{self.name}'")
        return self._dependencies[name]
