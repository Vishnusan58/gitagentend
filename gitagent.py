import os
import asyncio
import aiohttp
import base64
import json
from urllib.parse import urlparse
import google.generativeai as genai
import semantic_kernel as sk
from semantic_kernel.connectors.ai.google.google_ai import GoogleAIChatCompletion
from semantic_kernel.kernel import KernelArguments

# Configure your Gemini API key
genai.configure(api_key=os.getenv("GENAI_API_KEY"))

def extract_owner_repo(repo_url):
    """Extracts owner and repository names from a GitHub URL."""
    parsed_url = urlparse(repo_url)
    path_parts = parsed_url.path.strip('/').split('/')

    if len(path_parts) < 2 or parsed_url.netloc != 'github.com':
        return None, None

    return path_parts[0], path_parts[1]

async def get_github_repo_info(session, repo_url, token=None):
    """Retrieves repository information from a GitHub URL using aiohttp."""
    try:
        owner, repo = extract_owner_repo(repo_url)
        if not owner or not repo:
            return None, "Invalid GitHub URL format."

        headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        if token:
            headers["Authorization"] = f"token {token}"

        url = f"https://api.github.com/repos/{owner}/{repo}/contents"

        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json(), None
            else:
                error_text = await response.text()
                return None, f"Error retrieving repository: {response.status} - {error_text}"

    except Exception as e:
        return None, f"An error occurred: {e}"

async def get_file_content(session, owner, repo, path, token):
    """Retrieves file content from a GitHub repository using aiohttp."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                content_json = await response.json()
                if isinstance(content_json, dict) and "content" in content_json:
                    # GitHub API returns base64 encoded content
                    # Some files might be binary, so we'll try to decode as text
                    try:
                        decoded_content = base64.b64decode(content_json["content"]).decode('utf-8')
                        return decoded_content
                    except UnicodeDecodeError:
                        return f"[Binary file: {path}]"
                else:
                    return None
            else:
                print(f"Error retrieving {path}: {response.status}")
                return None
    except Exception as e:
        print(f"Exception retrieving {path}: {e}")
        return None

async def get_all_files_recursive(session, owner, repo, path, token, max_size=100000):
    """Recursively retrieves all files from a GitHub repository using aiohttp."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    file_list = []

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                items = await response.json()

                # Handle case when response is a file, not a directory
                if not isinstance(items, list):
                    items = [items]

                for item in items:
                    if item["type"] == "file":
                        # Skip large files and binary files that are likely not code
                        if item.get("size", 0) <= max_size and not item["name"].endswith((".jpg", ".png", ".gif", ".mp4", ".zip")):
                            file_list.append(item["path"])
                    elif item["type"] == "dir":
                        sub_files = await get_all_files_recursive(session, owner, repo, item["path"], token, max_size)
                        file_list.extend(sub_files)
            else:
                error_text = await response.text()
                print(f"Error retrieving file list: {response.status} - {error_text}")
    except Exception as e:
        print(f"Exception in recursive file retrieval: {e}")

    return file_list

async def get_multiple_file_contents(session, owner, repo, file_paths, token):
    """Fetch multiple file contents concurrently."""
    tasks = []
    for file_path in file_paths:
        task = asyncio.create_task(get_file_content(session, owner, repo, file_path, token))
        tasks.append((file_path, task))

    file_contents = {}
    for file_path, task in tasks:
        content = await task
        if content:
            file_contents[file_path] = content

    return file_contents

# Placeholder for Semantic Kernel Orchestration
async def orchestrate_analysis(repo_url, file_contents):
    """
    Placeholder for Semantic Kernel orchestration.  Currently uses Gemini
    directly, but will be replaced with SK logic.
    """
    summary_prompt = f"""
    Summarize the following GitHub repository, including the contents of its files:
    Repository URL: {repo_url}

    Identify specific optimization opportunities, highlighting:
    1. Performance bottlenecks
    2. Code structure improvements
    3. Security concerns
    4. Best practices that aren't being followed
    5. Give one optimsed code for one file

    For each issue found, precisely mention where modifications should be made.

    File Contents:
    """

    # Add file contents to prompt, limiting total size
    total_content_size = 0
    max_prompt_size = 100000  # Adjust based on Gemini's limitations

    for file_path, content in file_contents.items():
        file_section = f"\n--- {file_path} ---\n{content}\n"
        if total_content_size + len(file_section) < max_prompt_size:
            summary_prompt += file_section
            total_content_size += len(file_section)
        else:
            # Add a note that some files were omitted
            summary_prompt += f"\n[Additional {len(file_contents) - len(summary_prompt.split('---')) + 1} files omitted due to size constraints]"
            break

    # Generate summary with Gemini
    try:
        # --- Azure OpenAI Replacement Start ---
        # If using Azure OpenAI, replace the Gemini call with the following:
        # import openai
        # openai.api_type = "azure"
        # openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT") # Replace with your endpoint
        # openai.api_version = "2023-05-15" # Or the version you are using
        # openai.api_key = os.getenv("AZURE_OPENAI_API_KEY") # Replace with your API key

        # response = openai.ChatCompletion.create(
        #    engine="your-deployment-name", # Replace with your deployment name
        #    messages=[{"role": "user", "content": summary_prompt}]
        # )
        # return response['choices'][0]['message']['content']
        # --- Azure OpenAI Replacement End ---
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content(summary_prompt)
        return response.text
    except Exception as e:
        return f"Error generating summary: {e}"

async def summarize_repo_with_content(repo_url, token=None):
    """Summarizes a GitHub repository with file contents."""
    owner, repo = extract_owner_repo(repo_url)
    if not owner or not repo:
        return "Invalid GitHub URL format."

    # Use a timeout to prevent hanging on slow connections
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Get repository file structure
        print(f"Retrieving files from {owner}/{repo}...")
        file_list = await get_all_files_recursive(session, owner, repo, "", token)

        if not file_list:
            return "No files found or access denied. Please check your token and repository URL."

        print(f"Found {len(file_list)} files. Fetching contents...")

        # Get file contents with improved concurrency
        file_contents = await get_multiple_file_contents(session, owner, repo, file_list, token)

        if not file_contents:
            return "Could not retrieve any file contents. Please check permissions."

        print(f"Successfully retrieved {len(file_contents)} file contents. Generating summary...")

        # Orchestrate the analysis using the placeholder function
        summary = await orchestrate_analysis(repo_url, file_contents)
        return summary

async def main():
    """Main function to summarize a GitHub repository."""
    try:
        repo_url ="https://github.com/Vishnusan58/youreditorfriend"

        # Get token from environment variable or directly
        github_token =os.getenv("GITHUB_TOKEN")


        print(f"Analyzing repository: {repo_url}")
        summary = await summarize_repo_with_content(repo_url, github_token)
        print("\n===== REPOSITORY ANALYSIS =====\n")
        print(summary)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())