"""
EvoCorps Active Defense System - Agents Module
Contains refined agent type definitions and evolution strategy system
"""

from .defense_agent_types import (
    DefenseAgentType,
    DefenseAgentConfig,
    EMPATH_CONFIG,
    FACT_CHECKER_CONFIG,
    AMPLIFIER_CONFIG,
    NICHE_FILLER_CONFIG,
    DEFENSE_AGENT_CONFIGS,
    AgentAllocationStrategy,
    EvolutionParameters,
    get_recommended_agent_type,
    calculate_agent_effectiveness
)

from .defense_evolution_system import (
    FeedbackMetrics,
    AgentPerformance,
    EvolutionEngine,
    DefenseCoordinator
)

__all__ = [
    # Agent types
    'DefenseAgentType',
    'DefenseAgentConfig',
    
    # Preset configurations
    'EMPATH_CONFIG',
    'FACT_CHECKER_CONFIG',
    'AMPLIFIER_CONFIG',
    'NICHE_FILLER_CONFIG',
    'DEFENSE_AGENT_CONFIGS',
    
    # Strategy and parameters
    'AgentAllocationStrategy',
    'EvolutionParameters',
    
    # Helper functions
    'get_recommended_agent_type',
    'calculate_agent_effectiveness',
    
    # Evolution system
    'FeedbackMetrics',
    'AgentPerformance',
    'EvolutionEngine',
    'DefenseCoordinator'
]