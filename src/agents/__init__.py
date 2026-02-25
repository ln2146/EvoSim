"""
MOSAIC Agent System
Multi-Agent Opinion Sentiment Analysis and Intervention Coordination

This module provides a comprehensive multi-agent system for opinion balance
and sentiment analysis with automatic defense mechanisms.
"""

# Core agents
from .simple_coordination_system import (
    SimpleCoordinationSystem,
    SimpleAnalystAgent,
    SimpleStrategistAgent,
    SimpleLeaderAgent,
    SimpleamplifierAgent
)

# Enhanced leader agent with USC workflow
try:
    from .enhanced_leader_agent import EnhancedLeaderAgent, ArgumentDatabase
except ImportError:
    pass

# Defense system components (automatic role enhancement)
try:
    from .defense_agent_types import (
        DefenseAgentType,
        DefenseContext,
        DefenseRoleConfig,
        create_defense_role_configs,
        get_defense_agent_description
    )
except ImportError:
    pass

try:
    from .defense_evolution_system import (
        DefenseEvolutionSystem,
        DefenseEvolutionConfig,
        DefenseAction,
        DefenseOutcome
    )
except ImportError:
    pass

try:
    from .defense_monitoring_center import (
        DefenseMonitoringCenter,
        MonitoringConfig,
        ThreatLevel,
        DefenseAlert
    )
except ImportError:
    pass

try:
    from .defense_integration import (
        DefenseIntegration,
        integrate_defense_system,
        create_defense_enhanced_coordination_system
    )
except ImportError:
    pass

try:
    from .amplifier_role_enhancer import (
        AmplifierRoleEnhancer,
        EnhancedRoleConfig,
        enhance_amplifier_roles,
        get_role_instructions
    )
except ImportError:
    pass

try:
    from .role_enhancement_patch import (
        calculate_context_parameters,
        enhanced_assign_roles_to_agents,
        enhanced_generate_fallback_instruction,
        integrate_with_coordination_system,
        _ROLE_ENHANCEMENT_AVAILABLE
    )
except ImportError:
    _ROLE_ENHANCEMENT_AVAILABLE = False

# Defense agent prompts (specialized prompts for each defense role)
try:
    from .defense_agent_prompts import (
        DefenseAgentRole,
        EmpathPrompts,
        FactCheckerPrompts,
        AmplifierPrompts,
        NicheFillerPrompts,
        DefensePromptManager,
        get_empath_system_prompt,
        get_fact_checker_system_prompt,
        get_amplifier_system_prompt,
        get_niche_filler_system_prompt
    )
except ImportError:
    pass

# Version info
__version__ = "1.0.0"
__author__ = "MOSAIC Team"

# Public API
__all__ = [
    # Core coordination
    "SimpleCoordinationSystem",
    "SimpleAnalystAgent", 
    "SimpleStrategistAgent",
    "SimpleLeaderAgent",
    "SimpleamplifierAgent",
    
    # Enhanced leader
    "EnhancedLeaderAgent",
    "ArgumentDatabase",
    
    # Defense system
    "DefenseAgentType",
    "DefenseContext", 
    "DefenseRoleConfig",
    "create_defense_role_configs",
    "get_defense_agent_description",
    
    # Evolution system
    "DefenseEvolutionSystem",
    "DefenseEvolutionConfig",
    "DefenseAction",
    "DefenseOutcome",
    
    # Monitoring
    "DefenseMonitoringCenter",
    "MonitoringConfig",
    "ThreatLevel",
    "DefenseAlert",
    
    # Integration
    "DefenseIntegration",
    "integrate_defense_system",
    "create_defense_enhanced_coordination_system",
    
    # Role enhancement
    "AmplifierRoleEnhancer",
    "EnhancedRoleConfig",
    "enhance_amplifier_roles",
    "get_role_instructions",
    
    # Auto-integration
    "calculate_context_parameters",
    "enhanced_assign_roles_to_agents",
    "enhanced_generate_fallback_instruction",
    "integrate_with_coordination_system",
    "_ROLE_ENHANCEMENT_AVAILABLE",
    
    # Defense prompts
    "DefenseAgentRole",
    "EmpathPrompts",
    "FactCheckerPrompts",
    "AmplifierPrompts",
    "NicheFillerPrompts",
    "DefensePromptManager",
    "get_empath_system_prompt",
    "get_fact_checker_system_prompt",
    "get_amplifier_system_prompt",
    "get_niche_filler_system_prompt"
]