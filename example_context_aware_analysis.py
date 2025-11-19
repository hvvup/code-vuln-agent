"""Example usage of context-aware vulnerability analysis."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Choose your LLM provider (uncomment one)
# Option 1: OpenAI
from langchain_openai import ChatOpenAI

# Option 2: Anthropic Claude (uncomment to use)
# from langchain_anthropic import ChatAnthropic

from agents import VulnerabilityAnalysisAgent

# Load environment variables
load_dotenv()


def main():
    """Demonstrate context-aware vulnerability analysis."""

    print("\n" + "=" * 80)
    print("CONTEXT-AWARE VULNERABILITY ANALYSIS DEMO")
    print("=" * 80 + "\n")

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
    agent = VulnerabilityAnalysisAgent(
        llm=llm,
        verbose=True,  # Print reasoning steps
        max_iterations=25,  # Increase for context-aware analysis
        max_execution_time=600,  # 10 minutes max
    )

    # ==========================================================================
    # Example 1: Context-Aware Repository Analysis
    # ==========================================================================
    print("\n" + "=" * 80)
    print("Example 1: Context-Aware Repository Analysis")
    print("=" * 80 + "\n")

    # Replace with your actual repository path
    repository_path = r"D:\juice-shop"  # Or use input("Enter repository path: ")

    if Path(repository_path).exists():
        print(f"Analyzing repository with FULL CODEBASE CONTEXT: {repository_path}\n")

        result = agent.analyze_repository_context_aware(
            repository_path=repository_path,
            output_dir="output",
        )

        print("\n" + "-" * 80)
        print("ANALYSIS RESULTS:")
        print("-" * 80)
        print(result["output"])
        print("\n" + "-" * 80)
        print(f"Repository: {result['repository_path']}")
        print(f"Analysis Date: {result['analysis_date']}")
        print(f"Iterations: {result['iterations']}")
        print("-" * 80 + "\n")

    else:
        print(f"⚠️  Repository not found: {repository_path}")
        print("Please update the path in the script or create a test repository.\n")

    # ==========================================================================
    # Example 2: Context-Aware Single File Analysis
    # ==========================================================================
    print("\n" + "=" * 80)
    print("Example 2: Context-Aware Single File Analysis")
    print("=" * 80 + "\n")

    # Replace with your actual file path
    file_path = r"D:\juice-shop\routes\login.js"  # Example path

    if Path(file_path).exists():
        print(f"Analyzing file with CODEBASE CONTEXT: {file_path}\n")

        result = agent.analyze_file_with_context(
            file_path=file_path,
            repository_path=repository_path,  # Repository for context
            output_dir="output",
        )

        print("\n" + "-" * 80)
        print("ANALYSIS RESULTS:")
        print("-" * 80)
        print(result["output"])
        print("\n" + "-" * 80)
        print(f"File: {result['file_path']}")
        print(f"Repository: {result['repository_path']}")
        print(f"Analysis Date: {result['analysis_date']}")
        print(f"Iterations: {result['iterations']}")
        print("-" * 80 + "\n")

    else:
        print(f"⚠️  File not found: {file_path}")
        print("Please update the path in the script.\n")

    # ==========================================================================
    # Example 3: Custom Query with Context
    # ==========================================================================
    print("\n" + "=" * 80)
    print("Example 3: Custom Context-Aware Query")
    print("=" * 80 + "\n")

    custom_query = """
    First, build the codebase index for the repository at D:\\juice-shop using codebase_indexer.

    Then, find all functions named 'authenticate' or 'login' using codebase_query with query_type="find_symbol".

    For each function found, use codebase_query with query_type="find_callers" to see what calls it.

    Finally, analyze if there are any authentication bypass vulnerabilities by examining:
    1. The authentication function implementation
    2. All places that call these functions
    3. Whether proper validation happens before or after the calls

    Provide a comprehensive report on authentication security across the codebase.
    """

    if Path(repository_path).exists():
        print("Executing custom context-aware query...\n")

        result = agent.query(custom_query)

        print("\n" + "-" * 80)
        print("QUERY RESULTS:")
        print("-" * 80)
        print(result["answer"])
        print("\n" + "-" * 80)
        print(f"Iterations: {result['iterations']}")
        print("-" * 80 + "\n")

    # ==========================================================================
    # Example 4: Testing Context Tools Directly
    # ==========================================================================
    print("\n" + "=" * 80)
    print("Example 4: Testing Context Tools Directly")
    print("=" * 80 + "\n")

    # Test codebase indexer directly
    test_query = f"""
    Use the codebase_indexer tool to build an index of the repository at: {repository_path}

    Then use codebase_query to find:
    1. The top 5 core files (files with most dependents)
    2. Any circular dependencies in the codebase
    3. All functions named 'validate' or 'sanitize'

    Summarize the codebase structure and security-critical files.
    """

    if Path(repository_path).exists():
        print("Building codebase index and querying structure...\n")

        result = agent.query(test_query)

        print("\n" + "-" * 80)
        print("CODEBASE STRUCTURE ANALYSIS:")
        print("-" * 80)
        print(result["answer"])
        print("-" * 80 + "\n")

    print("\n" + "=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80 + "\n")

    print("📊 What's Different About Context-Aware Analysis?\n")
    print("✅ Builds complete codebase index (symbol table, call graph, dependencies)")
    print("✅ Traces vulnerabilities across file boundaries")
    print("✅ Understands import/export relationships")
    print("✅ Analyzes function call chains across modules")
    print("✅ Detects issues requiring whole-program understanding")
    print("✅ Filters false positives using codebase context")
    print("✅ Provides remediation advice considering entire architecture\n")

    print("📁 Generated Files (in output directory):")
    print("   - symbol_table.json: All imports/exports across files")
    print("   - call_graph.json: Cross-file function call relationships")
    print("   - dependency_graph.json: Module dependency analysis")
    print("   - cfg.json: Control flow graphs")
    print("   - Various other CFG artifacts\n")


if __name__ == "__main__":
    main()
