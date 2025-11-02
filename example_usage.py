"""Example usage of the vulnerability analysis agent."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Choose your LLM provider (uncomment one)
# Option 1: OpenAI
from langchain_openai import ChatOpenAI

# Option 2: Anthropic Claude (uncomment to use)
# from langchain_anthropic import ChatAnthropic

from agents import create_vulnerability_agent

# Load environment variables
load_dotenv()


def main():
    """Demonstrate how to use the vulnerability analysis agent."""

    # Initialize LLM
    # For OpenAI:
    llm = ChatOpenAI(
        model="gpt-4",
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # For Anthropic Claude (uncomment to use):
    # llm = ChatAnthropic(
    #     model="claude-3-5-sonnet-20241022",
    #     temperature=0,
    #     api_key=os.getenv("ANTHROPIC_API_KEY"),
    # )

    # Create the vulnerability analysis agent
    agent = create_vulnerability_agent(
        llm=llm,
        verbose=True,  # Print reasoning steps
        max_iterations=15,
        max_execution_time=300,  # 5 minutes max
    )

    # Example 1: Analyze a single file
    print("\n" + "=" * 80)
    print("Example 1: Analyzing a single JavaScript file")
    print("=" * 80 + "\n")

    # Replace with your actual file path
    test_file = Path("tests/sample_vulnerable_code.js")

    if test_file.exists():
        result = agent.analyze_file(
            file_path=str(test_file),
            output_dir="output",
        )

        print("\n--- Analysis Results ---")
        print(f"File: {result['file_path']}")
        print(f"Date: {result['analysis_date']}")
        print(f"Iterations: {result['iterations']}")
        print("\nFindings:")
        print(result["output"])
    else:
        print(f"Test file not found: {test_file}")
        print("Please create a test JavaScript file first.")

    # Example 2: Analyze multiple files
    print("\n" + "=" * 80)
    print("Example 2: Analyzing multiple files")
    print("=" * 80 + "\n")

    test_files = [
        "tests/test1.js",
        "tests/test2.js",
    ]

    # Filter to only existing files
    existing_files = [f for f in test_files if Path(f).exists()]

    if existing_files:
        results = agent.analyze_multiple_files(
            file_paths=existing_files,
            output_dir="output",
        )

        for i, result in enumerate(results, 1):
            print(f"\n--- File {i}: {result.get('file_path', 'Unknown')} ---")
            if "error" in result:
                print(f"Error: {result['error']}")
            else:
                print(f"Iterations: {result['iterations']}")
                print(result["output"][:500] + "..." if len(result["output"]) > 500 else result["output"])
    else:
        print("No test files found. Skipping multi-file analysis.")

    # Example 3: Custom query
    print("\n" + "=" * 80)
    print("Example 3: Custom query to the agent")
    print("=" * 80 + "\n")

    if test_file.exists():
        custom_question = f"""
        Analyze {test_file} for SQL injection vulnerabilities specifically.
        Use CodeQL to scan it, then examine the code flow to see if user input
        reaches database queries without proper sanitization.
        """

        result = agent.query(custom_question)
        print("\n--- Custom Query Results ---")
        print(f"Question: {result['question'].strip()}")
        print(f"Iterations: {result['iterations']}")
        print("\nAnswer:")
        print(result["answer"])


if __name__ == "__main__":
    main()
