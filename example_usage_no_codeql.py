"""Example usage of the vulnerability analysis agent WITHOUT CodeQL.

This example shows how to use the agent with only CFG analysis,
without requiring Docker or CodeQL installation.
"""

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
    """Demonstrate how to use the agent without CodeQL."""

    print("=" * 80)
    print("Vulnerability Analysis Agent (CFG-only mode - No CodeQL)")
    print("=" * 80)
    print()

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

    # Method 1: Use use_codeql=False parameter
    print("Creating agent without CodeQL (use_codeql=False)...")
    agent = VulnerabilityAnalysisAgent(
        llm=llm,
        verbose=True,
        max_iterations=15,
        use_codeql=False,  # This disables CodeQL tools
    )

    print(f"\nAgent initialized with {len(agent.tools)} tool(s):")
    for tool in agent.tools:
        print(f"  - {tool.name}")
    print()

    # Example: Analyze a file
    test_file = Path("tests/sample_vulnerable_code.js")

    if test_file.exists():
        print(f"\nAnalyzing: {test_file}")
        print("-" * 80)

        result = agent.analyze_file(
            file_path=str(test_file),
            output_dir="output",
        )

        print("\n" + "=" * 80)
        print("ANALYSIS RESULTS")
        print("=" * 80)
        print(f"\nFile: {result['file_path']}")
        print(f"Date: {result['analysis_date']}")
        print(f"Iterations: {result['iterations']}")
        print("\nFindings:")
        print(result["output"])

    else:
        print(f"\nTest file not found: {test_file}")
        print("Demonstrating with a custom query instead...")

        # Custom query without needing a file
        result = agent.query("""
        Explain what types of vulnerabilities you can detect using only
        control flow graph analysis, without static analysis tools like CodeQL.
        """)

        print("\n" + "=" * 80)
        print("QUERY RESULTS")
        print("=" * 80)
        print(result["answer"])

    # Method 2: Provide custom tools list (advanced)
    print("\n\n" + "=" * 80)
    print("Alternative: Creating agent with custom tools")
    print("=" * 80)

    from tools import CFGGeneratorTool

    custom_tools = [CFGGeneratorTool()]  # Only CFG tool

    agent2 = VulnerabilityAnalysisAgent(
        llm=llm,
        verbose=False,  # Less verbose this time
        tools=custom_tools,  # Custom tools list
    )

    print(f"\nAgent initialized with custom tools: {[t.name for t in agent2.tools]}")
    print("This agent will only use CFG analysis.")


if __name__ == "__main__":
    main()
