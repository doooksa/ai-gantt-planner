"""Domain layer: models, deterministic scheduler, validators, patches.

This package has NO dependency on FastAPI, the LLM, or MCP. It is the source of
truth for *structure* (tasks + dependencies + durations). Dates are always
*derived* by the scheduler and never stored on the model.
"""
