AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_harvest_pipeline",
            "description": "Initiates the OSINT feed ingestion and the 4-gate deterministic triage filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "force_refresh": {
                        "type": "boolean",
                        "description": "Whether to bypass the cache and force a fresh harvest."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_provenance_threshold",
            "description": "Adjusts the minimum credibility score required to pass the Provenance Gate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_score": {
                        "type": "number",
                        "description": "The new threshold, between 0.0 and 1.0."
                    }
                },
                "required": ["new_score"]
            }
        }
    }
]
