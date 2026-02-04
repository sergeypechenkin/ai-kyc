"""Plugins package for shared Semantic Kernel plugins."""

from src.plugins.base_plugin import KycPlugin
from src.plugins.plugin_registry import PluginRegistry
from src.plugins.customer_data import CustomerDataPlugin
from src.plugins.document_search import DocumentSearchPlugin
from src.plugins.inter_agent import InterAgentPlugin
from src.plugins.kyc_verify import KycVerificationPlugin

__all__ = [
    "KycPlugin",
    "PluginRegistry",
    "CustomerDataPlugin",
    "DocumentSearchPlugin",
    "InterAgentPlugin",
    "KycVerificationPlugin",
]
