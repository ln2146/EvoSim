"""
Standalone Control API Server

This script runs just the FastAPI control server without starting the full simulation.
It allows the frontend to toggle moderation, attack, aftercare, and other flags.

Usage:
    python src/run_control_server.py [port]

Default port is 8000.
"""

import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import control_flags


# =============================
# FastAPI control server setup
# =============================

control_app = FastAPI(title="Simulation Control API", version="1.0.0")

control_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ToggleRequest(BaseModel):
    """Simple request body for enabling / disabling a flag."""
    enabled: bool


@control_app.get("/control/status")
def get_control_status():
    """Return current values of all runtime control flags."""
    return control_flags.as_dict()


@control_app.post("/control/moderation")
def set_moderation_flag(body: ToggleRequest):
    """Enable or disable content moderation at runtime."""
    control_flags.moderation_enabled = body.enabled
    return {"status": "success", "moderation_enabled": control_flags.moderation_enabled}


@control_app.post("/control/attack")
def set_attack_flag(body: ToggleRequest):
    """Enable or disable malicious bot attacks at runtime."""
    control_flags.attack_enabled = body.enabled
    return {"status": "success", "attack_enabled": control_flags.attack_enabled}


@control_app.post("/control/aftercare")
def set_aftercare_flag(body: ToggleRequest):
    """Enable or disable fact-checking aftercare at runtime."""
    control_flags.aftercare_enabled = body.enabled
    return {"status": "success", "aftercare_enabled": control_flags.aftercare_enabled}


@control_app.post("/control/auto-status")
def set_auto_status(body: ToggleRequest):
    """Enable or disable opinion-balance auto monitoring/intervention at runtime."""
    control_flags.auto_status_enabled = body.enabled
    return {"status": "success", "auto_status_enabled": control_flags.auto_status_enabled}


def main():
    # Get port from command line or use default
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    print(f"Starting Control API server at http://0.0.0.0:{port}")
    print("Available endpoints:")
    print("  GET  /control/status")
    print("  POST /control/moderation")
    print("  POST /control/attack")
    print("  POST /control/aftercare")
    print("  POST /control/auto-status")

    uvicorn.run(control_app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
