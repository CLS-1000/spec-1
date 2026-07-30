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
    print("Starting Operator Interface Server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
