"""Test script for repository-level vulnerability scanning."""

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


def test_juice_shop_scan():
    """Test scanning the juice-shop repository."""

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
        verbose=False,  # Print reasoning steps
        max_iterations=20,  # Increase for large repositories
        max_execution_time=600,  # 10 minutes max for large repos
    )

    # Repository path to scan
    repository_path = r"D:\juice-shop"

    # Validate path exists
    repo_path = Path(repository_path)
    if not repo_path.exists():
        print(f"❌ Repository not found: {repository_path}")
        print("Please check the path and try again.")
        return

    if not repo_path.is_dir():
        print(f"❌ Path is not a directory: {repository_path}")
        return

    print("\n" + "=" * 80)
    print(f"Scanning repository: {repository_path}")
    print("=" * 80 + "\n")

    try:
        # Analyze the repository
        result = agent.analyze_repository(
            repository_path=repository_path,
            output_dir="output/juice-shop",
        )

        print("\n" + "=" * 80)
        print("Analysis Complete!")
        print("=" * 80 + "\n")

        print(f"Repository: {result['repository_path']}")
        print(f"Analysis Date: {result['analysis_date']}")
        print(f"Iterations: {result['iterations']}")
        print(f"\nNumber of tool calls: {len(result['intermediate_steps'])}")

        print("\n--- Analysis Results ---")
        print(result["output"])

        # Save results to file
        output_file = Path("output/juice-shop/analysis_report.txt")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"Repository Analysis Report\n")
            f.write(f"{'=' * 80}\n\n")
            f.write(f"Repository: {result['repository_path']}\n")
            f.write(f"Analysis Date: {result['analysis_date']}\n")
            f.write(f"Iterations: {result['iterations']}\n\n")
            f.write(f"Analysis Results:\n")
            f.write(f"{'-' * 80}\n")
            f.write(result["output"])
            f.write(f"\n\n{'=' * 80}\n")
            f.write("Intermediate Steps:\n")
            for i, step in enumerate(result["intermediate_steps"], 1):
                f.write(f"\nStep {i}:\n")
                f.write(f"  Tool: {step.get('tool', 'Unknown')}\n")
                f.write(f"  Content: {step.get('content', '')[:500]}...\n")

        print(f"\n✅ Full report saved to: {output_file}")

    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_juice_shop_scan()
