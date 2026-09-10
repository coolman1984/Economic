"""Economic — local-first personal investment office for the Egyptian Exchange.

Layering rule (see PROJECT_MAP.md):
    cli -> application -> domain
    application -> persistence / agents adapters
The domain layer never imports persistence, agents, or CLI code.
"""

__version__ = "0.1.0"
CONTRACT_VERSION = "1.0"
ENGINE_VERSION = "portfolio-engine/1.0"
