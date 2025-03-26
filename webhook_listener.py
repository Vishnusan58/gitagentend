import asyncio
import hashlib
import hmac
import os
from datetime import datetime

import markdown2
from flask import Flask, request, jsonify, render_template
from markupsafe import Markup

from gitagent import summarize_repo_with_content

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Load GitHub Webhook Secret from environment variable
GITHUB_SECRET = "a3b9f4e2c1d8e7f3a6b1c0d5e4f7g2h3"

# Store analysis results
analysis_results = {}


def verify_signature(payload, signature):
    """Verifies GitHub Webhook payload signature."""
    if not GITHUB_SECRET:
        print("⚠️ Warning: No GITHUB_WEBHOOK_SECRET set. Skipping signature verification.")
        return True

    mac = hmac.new(GITHUB_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={mac}"
    return hmac.compare_digest(expected_signature, signature)


def format_markdown(text):
    """Convert markdown to HTML with syntax highlighting."""
    return Markup(markdown2.markdown(text, extras=["fenced-code-blocks", "tables"]))


@app.template_filter('format_datetime')
def format_datetime(timestamp):
    """Format datetime for display"""
    try:
        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S UTC')
        return dt.strftime('%B %d, %Y at %H:%M:%S UTC')
    except:
        return timestamp


@app.route('/')
def index():
    """Display the main page with analysis results."""
    formatted_analyses = {}
    for repo_url, analysis in analysis_results.items():
        formatted_analyses[repo_url] = {
            'timestamp': analysis['timestamp'],
            'result': format_markdown(analysis['result']),
            'commit_message': analysis.get('commit_message', ''),
            'commit_author': analysis.get('commit_author', '')
        }
    return render_template('index.html', analyses=formatted_analyses)


@app.route('/webhook', methods=['POST'])
def webhook():
    """Handles webhook events and triggers the analysis."""

    async def process_webhook():
        signature = request.headers.get('X-Hub-Signature-256', '')
        payload = request.data

        if not verify_signature(payload, signature):
            print("❌ Invalid signature. Rejecting request.")
            return jsonify({"message": "Invalid signature"}), 403

        data = request.json
        if "ref" in data and "repository" in data:
            # Only process push events to the main/master branch
            branch = data["ref"].split('/')[-1]
            if branch not in ['main', 'master']:
                return jsonify({"message": f"Ignoring push to {branch} branch"}), 200

            repo_url = data["repository"]["html_url"]
            print(f"🔄 Change detected in repository: {repo_url}")

            # Extract commit information
            commit_info = data.get("head_commit", {})
            commit_message = commit_info.get("message", "No commit message")
            commit_author = commit_info.get("author", {}).get("name", "Unknown")

            try:
                github_token = os.getenv("GITHUB_TOKEN")
                analysis = await summarize_repo_with_content(repo_url, github_token)

                # Store the analysis result with additional information
                timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
                analysis_results[repo_url] = {
                    'timestamp': timestamp,
                    'result': analysis,
                    'commit_message': commit_message,
                    'commit_author': commit_author
                }

                print("✅ Analysis completed successfully!")
                print(f"📝 Commit by {commit_author}: {commit_message}")

                return jsonify({
                    "message": "Analysis completed successfully",
                    "repository": repo_url,
                    "timestamp": timestamp,
                    "commit_info": {
                        "author": commit_author,
                        "message": commit_message
                    }
                }), 200

            except Exception as e:
                error_message = f"❌ Error during analysis: {str(e)}"
                print(error_message)
                return jsonify({"message": error_message}), 500

        return jsonify({"message": "Invalid webhook event"}), 400

    return asyncio.run(process_webhook())


if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)