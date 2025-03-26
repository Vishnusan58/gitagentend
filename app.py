from flask import Flask, render_template, request, jsonify, flash
import asyncio
from gitagent import summarize_repo_with_content
import os
from datetime import datetime
import hmac
import hashlib
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For flash messages

# Your existing webhook secret
GITHUB_SECRET = "a3b9f4e2c1d8e7f3a6b1c0d5e4f7g2h3"

# Store analysis results (in a real application, you'd want to use a database)
analysis_results = {}


def verify_signature(payload, signature):
    """Verifies GitHub Webhook payload signature."""
    if not GITHUB_SECRET:
        return True

    mac = hmac.new(GITHUB_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={mac}"
    return hmac.compare_digest(expected_signature, signature)


def async_route(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapped


@app.route('/')
def index():
    return render_template('index.html', analyses=analysis_results)


@app.route('/analyze', methods=['POST'])
@async_route
async def analyze():
    repo_url = request.form.get('repo_url')
    if not repo_url:
        flash('Please provide a repository URL', 'error')
        return render_template('index.html')

    try:
        github_token = os.getenv("GITHUB_TOKEN")
        analysis = await summarize_repo_with_content(repo_url, github_token)

        # Store the analysis result
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        analysis_results[repo_url] = {
            'timestamp': timestamp,
            'result': analysis
        }

        flash('Analysis completed successfully!', 'success')
        return render_template('index.html',
                               current_analysis=analysis,
                               current_repo=repo_url,
                               analyses=analysis_results)

    except Exception as e:
        flash(f'Error during analysis: {str(e)}', 'error')
        return render_template('index.html', analyses=analysis_results)


@app.route('/webhook', methods=['POST'])
@async_route
async def webhook():
    signature = request.headers.get('X-Hub-Signature-256', '')
    payload = request.data

    if not verify_signature(payload, signature):
        return jsonify({"message": "Invalid signature"}), 403

    data = request.json
    if "repository" in data:
        repo_url = data["repository"]["html_url"]
        try:
            github_token = os.getenv("GITHUB_TOKEN")
            analysis = await summarize_repo_with_content(repo_url, github_token)

            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            analysis_results[repo_url] = {
                'timestamp': timestamp,
                'result': analysis
            }

            return jsonify({
                "message": "Analysis completed successfully",
                "repository": repo_url,
                "timestamp": timestamp
            }), 200

        except Exception as e:
            return jsonify({"message": f"Error during analysis: {str(e)}"}), 500

    return jsonify({"message": "Invalid webhook event"}), 400


@app.route('/api/results/<path:repo_url>')
def get_results(repo_url):
    if repo_url in analysis_results:
        return jsonify(analysis_results[repo_url])
    return jsonify({"error": "No analysis found for this repository"}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)