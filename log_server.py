import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import glob
import json

# Initialize the Flask app
app = Flask(__name__)
CORS(app) # Enable CORS

NERDGRAPH_URL = 'https://api.newrelic.com/graphql'

def find_html_file(pattern="log_explorer.html"):
    """Finds the specified HTML file in the current directory."""
    html_files = glob.glob(pattern)
    if html_files:
        print(f"Found HTML file: {html_files[0]}")
        return html_files[0]
    print(f"ERROR: '{pattern}' not found in the current directory.")
    return None

HTML_FILE = find_html_file()

@app.route('/')
def serve_index():
    """Serves the main HTML user interface."""
    if HTML_FILE:
        return send_from_directory('.', HTML_FILE)
    return "<h1>Error: log_explorer.html not found</h1>", 404

@app.route('/query', methods=['POST'])
def handle_query():
    """Receives a query from the frontend and forwards it to New Relic."""
    client_data = request.json
    api_key = client_data.get('apiKey')
    if not api_key:
        return jsonify({"error": "API Key is missing in the request."}), 400

    graphql_payload = {
        "query": client_data.get('query'),
        "variables": client_data.get('variables')
    }
    
    return forward_to_nerdgraph(graphql_payload, api_key)

@app.route('/account-name', methods=['POST'])
def handle_account_name_query():
    """
    This endpoint receives an account ID and fetches its name.
    """
    client_data = request.json
    api_key = client_data.get('apiKey')
    account_id = client_data.get('accountId')

    if not api_key or not account_id:
        return jsonify({"error": "API Key and Account ID are required."}), 400
    
    graphql_payload = {
        "query": "query($accountId: Int!) { actor { account(id: $accountId) { name } } }",
        "variables": { "accountId": account_id }
    }
    
    return forward_to_nerdgraph(graphql_payload, api_key)


def forward_to_nerdgraph(payload, api_key):
    """A helper function to forward a GraphQL payload to New Relic."""
    headers = {
        'Content-Type': 'application/json',
        'API-Key': api_key
    }
    try:
        response = requests.post(NERDGRAPH_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        print(f"A network error occurred: {e}")
        return jsonify({"error": "A network error occurred while contacting New Relic."}), 503

if __name__ == '__main__':
    app.run(port=5002, debug=True)