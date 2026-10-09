from flask import Flask, send_file
from src.agent.controller import agent_api

app = Flask(__name__)

# Register the Agent Two-Pass Loop
app.register_blueprint(agent_api)

# Serve the Operator UI
@app.route('/')
def serve_ui():
    return send_file('spec1_ui.html')

if __name__ == '__main__':
    # Bound to loopback only: this Flask app sits outside spec1_api's
    # ApiKeyMiddleware, so it must not be reachable from other hosts.
    print("Starting Operator Interface Server on http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False)
