import os
import asyncio
import aiohttp
import base64
from urllib.parse import urlparse
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import KernelArguments


async def extract_owner_repo(repo_url):
    """Extracts owner and repository names from a GitHub URL."""
    parsed_url = urlparse(repo_url)
    path_parts = parsed_url.path.strip('/').split('/')
    return path_parts[0], path_parts[1] if len(path_parts) >= 2 else None


async def get_file_content(session, owner, repo, path, token):

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

                if not isinstance(items, list):
                    items = [items]

                for item in items:
                    if item["type"] == "file":
                        if item.get("size", 0) <= max_size and not item["name"].endswith(
                                (".jpg", ".png", ".gif", ".mp4", ".zip")
                        ):
                            file_list.append(item["path"])
                    elif item["type"] == "dir":
                        sub_files = await get_all_files_recursive(
                            session, owner, repo, item["path"], token, max_size
                        )
                        file_list.extend(sub_files)
            else:
                print(f"Error retrieving file list: {response.status}")
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


async def analyze_file_chunk(kernel, repo_url: str, file_chunk: dict):
    """Analyze a chunk of repository files."""
    prompt_template = """
    Analyzing part of GitHub Repository: {{$repo_url}}

    Analyzing the following files:
    {{$file_list}}

    File Contents:
    {{$file_contents}}

    For these specific files, please provide:

    1. File Structure Analysis
    - Purpose of each file
    - Dependencies and relationships
    - Key functionality

    2. Code Review
    - Main components
    - Code patterns used
    - Potential issues

    3. Optimization Opportunities
    - Performance improvements
    - Code structure enhancements
    - Security considerations

    4. If you find a good candidate for optimization, provide:
    - Original code snippet
    - Optimized version with comments
    - Explanation of improvements

    Focus on practical, actionable improvements.
    Use markdown for formatting.
    """

    # Prepare file list and contents
    file_list = "\n".join([f"- {path}" for path in file_chunk.keys()])
    file_contents = "\n\n".join([
        f"### {path}\n```\n{content[:1000]}...\n```"  # Limit content size
        for path, content in file_chunk.items()
    ])

    arguments = KernelArguments(
        repo_url=repo_url,
        file_list=file_list,
        file_contents=file_contents
    )

    try:
        result = await kernel.invoke_prompt(
            prompt_template,
            arguments=arguments
        )
        return str(result)
    except Exception as e:
        return f"Error analyzing chunk: {str(e)}"


async def analyze_repository(repo_url: str, github_token: str | None = None):
    """Main function to analyze a GitHub repository."""
    try:
        # Initialize Semantic Kernel
        kernel = sk.Kernel()

        # Configure OpenAI as AI service

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found")

        chat_service = OpenAIChatCompletion(
            service_id="chat-gpt",
            ai_model_id="gpt-3.5-turbo-16k",  # Using 16k context model
            api_key=api_key
        )
        kernel.add_service(chat_service)

        # Extract repository information
        owner, repo = await extract_owner_repo(repo_url)
        if not owner or not repo:
            return "Invalid GitHub URL format."

        # Set up HTTP session
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print(f"Fetching files from {owner}/{repo}...")

            # Get list of files
            file_list = await get_all_files_recursive(session, owner, repo, "", github_token)
            if not file_list:
                return "No files found or access denied."

            print(f"Found {len(file_list)} files. Fetching contents...")

            # Get file contents
            file_contents = await get_multiple_file_contents(
                session, owner, repo, file_list, github_token
            )
            if not file_contents:
                return "Could not retrieve file contents."

            print(f"Successfully retrieved {len(file_contents)} files. Analyzing in chunks...")

            # Split files into chunks to handle token limits
            chunk_size = 3  # Analyze 3 files at a time
            file_chunks = []
            current_chunk = {}

            for i, (path, content) in enumerate(file_contents.items()):
                current_chunk[path] = content
                if (i + 1) % chunk_size == 0:
                    file_chunks.append(current_chunk)
                    current_chunk = {}

            if current_chunk:
                file_chunks.append(current_chunk)

            # Analyze each chunk
            analyses = []
            for i, chunk in enumerate(file_chunks):
                print(f"Analyzing chunk {i + 1} of {len(file_chunks)}...")
                chunk_analysis = await analyze_file_chunk(kernel, repo_url, chunk)
                analyses.append(chunk_analysis)

            # Combine the analyses
            final_prompt = f"""
            Combine and summarize the following analyses of the GitHub repository {repo_url}:

            {'/n/n'.join(analyses)}

            Provide a consolidated summary including:
            1. Overall repository structure and purpose
            2. Key findings across all files
            3. Most important optimization opportunities
            4. Best example of optimized code
            5. Priority recommendations
            6. Show one code that can be optimized

            Format using markdown for readability.
            """

            arguments = KernelArguments(prompt=final_prompt)
            final_analysis = await kernel.invoke_prompt(
                final_prompt,
                arguments=arguments
            )

            return str(final_analysis)

    except Exception as e:
        return f"Analysis failed: {str(e)}"


async def main():
    """Main execution function."""
    try:
        repo_url = "https://github.com/Vishnusan58/youreditorfriend"
        github_token = os.getenv("GITHUB_TOKEN")
        print(f"Starting analysis of: {repo_url}")
        result = await analyze_repository(repo_url, github_token)
        print("\n===== REPOSITORY ANALYSIS =====\n")
        print(result)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())