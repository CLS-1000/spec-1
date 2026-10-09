import json
import ollama
from flask import Blueprint, request, jsonify

from src.agent.tools_schema import AGENT_TOOLS
from src.agent.prompts import AGENT_SYSTEM_PROMPT

# Uncomment and adjust these when ready to link your actual pipeline:
# from src.pipeline.core import execute_harvest_pipeline, update_provenance_threshold

agent_api = Blueprint('agent_api', __name__)

# Map the string names from the LLM to your actual Python functions
# Neither tool is wired to the real pipeline yet. They report "not_implemented"
# rather than a fabricated success, so the synthesis pass cannot tell the
# operator that a harvest ran or a threshold changed when nothing happened.
NOT_IMPLEMENTED = "not_implemented"


def _not_implemented(action: str):
    def handler(**_kwargs):
        return {"status": NOT_IMPLEMENTED, "detail": f"{action} is not wired to the pipeline; nothing was executed"}
    return handler


FUNCTION_REGISTRY = {
    "execute_harvest_pipeline": _not_implemented("execute_harvest_pipeline"),
    "update_provenance_threshold": _not_implemented("update_provenance_threshold"),
}

@agent_api.route('/api/agent/command', methods=['POST'])
def handle_agent_command():
    payload = request.get_json(silent=True) or {}
    user_command = payload.get('command')
    if not user_command:
        return jsonify({"error": "No command provided"}), 400

    # PASS 1: Intention & Action
    action_response = ollama.chat(
        model='llama3.1',
        messages=[{'role': 'user', 'content': user_command}],
        tools=AGENT_TOOLS
    )

    execution_results = []

    # Execute the requested tools
    if action_response.get('message', {}).get('tool_calls'):
        for tool in action_response['message']['tool_calls']:
            func_name = tool['function']['name']
            func_args = tool['function']['arguments']

            if func_name in FUNCTION_REGISTRY:
                try:
                    raw_result = FUNCTION_REGISTRY[func_name](**func_args)
                    execution_results.append({
                        "action": func_name,
                        "status": raw_result.get("status", "unknown"),
                        "output": raw_result
                    })
                except Exception as e:
                    execution_results.append({
                        "action": func_name,
                        "status": "error",
                        "error_message": str(e)
                    })
    else:
        execution_results.append({"status": "no_action_taken"})

    # PASS 2: Observation & Reflection
    synthesis_prompt = f"""
    The user originally commanded: "{user_command}"

    Raw system execution results:
    {json.dumps(execution_results, indent=2)}

    Provide the final briefing to the user.
    """

    final_response = ollama.chat(
        model='llama3.1',
        messages=[
            {'role': 'system', 'content': AGENT_SYSTEM_PROMPT},
            {'role': 'user', 'content': synthesis_prompt}
        ]
    )

    return jsonify({"message": final_response['message']['content']})
