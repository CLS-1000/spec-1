# @domain:   spec-1
# @module:   anthropic_smoke
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

from dotenv import load_dotenv
import os
from anthropic import Anthropic

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
client = Anthropic(api_key=api_key)

from spec1_core.intelligence.store import spec1_home
from spec1_core.llm import model_config

response = client.messages.create(
    model=model_config.load(spec1_home()).claude_model,
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "What is SPEC-1?"}
    ]
)

print(response.content[0].text)
