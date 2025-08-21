import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import glob
import google.generativeai as genai
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


# --- NEW: Route for fetching AI insights from Gemini ---
@app.route('/gemini-insights', methods=['POST'])
def handle_gemini_insights():
    """Receives log data as CSV and gets insights from the Gemini API."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({
            "error": "Gemini API key is not configured on the server. Please set the GEMINI_API_KEY environment variable to use this feature."
        }), 412 # 412 Precondition Failed is a fitting status code

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    csv_data = request.data.decode('utf-8')
    if not csv_data:
        return jsonify({"error": "Log data (CSV) is missing."}), 400

    # The detailed prompt you provided
    prompt = f"""
    Analyze this CSV data for the following:

    1. Does it appear that there are multi-line logs? These are logs that are abruptly truncated with a '\\n'. That can lead to a duplication of the entire log including all attributes. Give a summary of the % of times this occurs in the sample. And a % of bytes (estimated) in the sample set are impacted.

    2. Give a summary of whether any logs or metrics are being duplicated completely. In other words they are coming from different sources but are mostly the same. Provide some statistically summary of the impact in terms of numbers of records and potential byte size impact.

    3. Give a summary attribute count breakdown. Average, Max, P75, P95. Include some breakdowns as well if any sources are particularly to cause for a very high number of attributes (P90 or above).

    4. Give an analysis if it seems that some attributes are duplicated. This could happen in a situation where some logs have two fields like "env" and "environ" that contain more or less the same thing. In addition you may have logs that have a "message" and "Message" fields with more or less the same payload. Those are just examples.

    5. If you can find any example of garbled text or very difficult to understand text. These could be character codes, base 64, hex or just something that may not be a good fit for log data.

    Here is the data:
    ---
    {csv_data}
    ---
    """

    try:
        response = model.generate_content(prompt)
        return jsonify({"insights": response.text})
    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        return jsonify({"error": "An error occurred while contacting the AI service."}), 503


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
    # For production, it's better to use a proper WSGI server like Gunicorn or Waitress
    app.run(port=5002, debug=True)