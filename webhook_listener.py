import os
import sys
from flask import Flask, request, jsonify, render_template, flash, redirect, url_for
import hmac
from markupsafe import Markup
import hashlib
import asyncio
import markdown2
import re
from datetime import datetime
from functools import wraps
# Import the required functions from gitagent.py
from gitagent import summarize_repo_with_content, extract_owner_repo

app = Flask(__name__)
app.secret_key = os.urandom(24)
# Register the template filter properly
@app.template_filter('format_datetime')
def format_datetime(timestamp):
    """Format datetime for display"""
    try:
        if isinstance(timestamp, str):
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S UTC')
        else:
            dt = timestamp
        return dt.strftime('%B %d, %Y at %H:%M:%S UTC')
    except Exception:
        return timestamp


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
    return Markup(markdown2.markdown(text, extras=[
        "fenced-code-blocks",
        "tables",
        "break-on-newline",
        "header-ids",
        "task-lists"
    ]))


def is_valid_github_url(url):
    """Validate GitHub repository URL format."""
    pattern = r'^https?://github\.com/[\w-]+/[\w.-]+/?$'
    return bool(re.match(pattern, url))


@app.route('/')
def index():
    """Display the main page with analysis results."""
    formatted_analyses = {}
    for repo_url, analysis in analysis_results.items():
        formatted_analyses[repo_url] = {
            'timestamp': analysis['timestamp'],
            'result': format_markdown(analysis['result']),
            'commit_message': analysis.get('commit_message', ''),
            'commit_author': analysis.get('commit_author', ''),
            'repo_name': repo_url.split('/')[-1]
        }

    current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

    return render_template('index.html',
                           analyses=formatted_analyses,
                           current_user="Vishnusan58",
                           current_time=current_time)


@app.route('/analyze', methods=['POST'])
def analyze():
    """Handle manual repository analysis requests."""

    async def run_analysis():
        repo_url = request.form.get('repo_url', '').strip()

        if not repo_url:
            flash('Please provide a repository URL', 'error')
            return redirect(url_for('index'))

        if not is_valid_github_url(repo_url):
            flash('Invalid GitHub repository URL format', 'error')
            return redirect(url_for('index'))

        try:
            # Show processing status
            flash(f'Processing repository: {repo_url}...', 'info')

            # Get GitHub token from environment
            github_token = os.getenv("GITHUB_TOKEN")

            # Validate repository access
            owner, repo = extract_owner_repo(repo_url)
            if not owner or not repo:
                flash('Invalid repository URL format', 'error')
                return redirect(url_for('index'))

            # Use the summarize_repo_with_content function from gitagent.py
            analysis = await summarize_repo_with_content(repo_url, github_token)

            if analysis and not analysis.startswith("Error"):
                timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
                analysis_results[repo_url] = {
                    'timestamp': timestamp,
                    'result': analysis,
                    'commit_message': 'Manual Analysis',
                    'commit_author': request.form.get('username', 'Anonymous')
                }
                flash('Repository analysis completed successfully!', 'success')
            else:
                flash(f'Analysis failed: {analysis}', 'error')

            return redirect(url_for('index'))

        except Exception as e:
            flash(f'Error during analysis: {str(e)}', 'error')
            return redirect(url_for('index'))

    return asyncio.run(run_analysis())


@app.route('/webhook', methods=['POST'])
def webhook():
    """Handles webhook events and triggers the analysis."""

    async def process_webhook():
        signature = request.headers.get('X-Hub-Signature-256', '')
        payload = request.data

        if not verify_signature(payload, signature):
            return jsonify({"message": "Invalid signature"}), 403

        data = request.json
        if "ref" in data and "repository" in data:
            branch = data["ref"].split('/')[-1]
            if branch not in ['main', 'master']:
                return jsonify({"message": f"Ignoring push to {branch} branch"}), 200

            repo_url = data["repository"]["html_url"]
            commit_info = data.get("head_commit", {})
            commit_message = commit_info.get("message", "No commit message")
            commit_author = commit_info.get("author", {}).get("name", "Unknown")

            try:
                github_token = os.getenv("GITHUB_TOKEN")
                analysis = await summarize_repo_with_content(repo_url, github_token)

                if analysis and not analysis.startswith("Error"):
                    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
                    analysis_results[repo_url] = {
                        'timestamp': timestamp,
                        'result': analysis,
                        'commit_message': commit_message,
                        'commit_author': commit_author
                    }
                    return jsonify({
                        "message": "Analysis completed successfully",
                        "repository": repo_url,
                        "timestamp": timestamp,
                        "commit_info": {
                            "author": commit_author,
                            "message": commit_message
                        }
                    }), 200
                else:
                    return jsonify({"message": f"Analysis failed: {analysis}"}), 500

            except Exception as e:
                return jsonify({"message": str(e)}), 500

        return jsonify({"message": "Invalid webhook event"}), 400

    return asyncio.run(process_webhook())


@app.route('/clear/<path:repo_url>')
def clear_analysis(repo_url):
    """Clear a specific analysis result."""
    if repo_url in analysis_results:
        del analysis_results[repo_url]
        flash('Analysis cleared successfully', 'success')
    return redirect(url_for('index'))


# Add status endpoint to check analysis progress
@app.route('/status/<path:repo_url>')
def analysis_status(repo_url):
    """Check the status of an analysis."""
    if repo_url in analysis_results:
        return jsonify({
            "status": "completed",
            "result": analysis_results[repo_url]
        })
    return jsonify({
        "status": "not_found"
    }), 404


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)