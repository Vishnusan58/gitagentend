import os
import sys
import subprocess
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)

# Load GitHub Webhook Secret from environment variable
GITHUB_SECRET ="a3b9f4e2c1d8e7f3a6b1c0d5e4f7g2h3"

def verify_signature(payload, signature):
    """Verifies GitHub Webhook payload signature."""
    if not GITHUB_SECRET:
        print("⚠️ Warning: No GITHUB_WEBHOOK_SECRET set. Skipping signature verification.")
        return True  # Allow all requests if no secret is set (not recommended for production)

    mac = hmac.new(GITHUB_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={mac}"

    return hmac.compare_digest(expected_signature, signature)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Listens for GitHub webhook events and triggers the optimization script."""
    signature = request.headers.get('X-Hub-Signature-256', '')
    payload = request.data

    if not verify_signature(payload, signature):
        print(" Invalid signature. Rejecting request.")
        return jsonify({"message": "Invalid signature"}), 403

    data = request.json
    if "ref" in data:
        print("🔄 Change detected in repository. Triggering optimization script...")

        try:
            process = subprocess.Popen(
                [sys.executable, os.path.join(os.getcwd(), "gitagent.py")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()

            print("✅ Optimization script executed successfully!")
            print("📜 STDOUT:", stdout.decode().strip())
            print("⚠️ STDERR:", stderr.decode().strip())

            return jsonify({"message": "Optimization script triggered successfully"}), 200

        except Exception as e:
            print(f"❌ Error while executing gitagent.py: {e}")
            return jsonify({"message": f"Error executing script: {str(e)}"}), 500

    return jsonify({"message": "Invalid webhook event"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
