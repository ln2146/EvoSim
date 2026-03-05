"""
Malicious bot subsystem for EvoCorps.

Simulates coordinated adversarial agents for research purposes.

Public API:
    MaliciousBotManager  - top-level manager, called by simulation.py
    SimpleMaliciousCluster - bot cluster that generates malicious content
    MaliciousPersona       - data class for a single bot's identity
"""

from .malicious_bot_manager import MaliciousBotManager
from .simple_malicious_agent import SimpleMaliciousCluster, MaliciousPersona
from .bot_role_overlay import BotRole, RoleOverlay, assign_bot_roles, get_role_overlay

__all__ = [
    "MaliciousBotManager",
    "SimpleMaliciousCluster",
    "MaliciousPersona",
    "BotRole",
    "RoleOverlay",
    "assign_bot_roles",
    "get_role_overlay",
]
