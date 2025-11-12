"""Comprehensive workflow test for D:\\juice-shop repository."""

import os
import sys
from pathlib import Path
from datetime import datetime
import json

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Repository path
REPOSITORY_PATH = r"D:\juice-shop"


def test_full_workflow():
    """Test the complete workflow with all tools."""
    print("\n" + "=" * 80)
    print("COMPREHENSIVE WORKFLOW TEST")
    print("=" * 80)
    print(f"\nRepository: {REPOSITORY_PATH}")

    # Validate repository
    repo_path = Path(REPOSITORY_PATH)
    if not repo_path.exists():
        print(f"❌ Repository not found: {REPOSITORY_PATH}")
        return False

    if not repo_path.is_dir():
        print(f"❌ Path is not a directory: {REPOSITORY_PATH}")
        return False

    # Check for LLM API key
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not openai_key and not anthropic_key:
        print("❌ No LLM API key found!")
        print("Please set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env file")
        return False

    try:
        from langchain_openai import ChatOpenAI
        from agents import create_vulnerability_agent

        # Initialize LLM
        if openai_key:
            print("✓ Using OpenAI...")
            llm = ChatOpenAI(
                model="gpt-4",
                temperature=0,
                api_key=openai_key,
            )
        else:
            from langchain_anthropic import ChatAnthropic
            print("✓ Using Anthropic Claude...")
            llm = ChatAnthropic(
                model="claude-3-5-sonnet-20241022",
                temperature=0,
                api_key=anthropic_key,
            )

        # Create agent
        print("\n✓ Creating vulnerability analysis agent...")
        agent = create_vulnerability_agent(
            llm=llm,
            verbose=True,
            max_iterations=25,  # Increase for large repositories
            max_execution_time=900,  # 15 minutes
        )

        # Check available tools
        tool_names = [tool.name for tool in agent.tools]
        print(f"\n✓ Available tools: {', '.join(tool_names)}")

        expected_tools = [
            "codeql_auto_analyze",
            "parse_codeql_sarif",
            "cfg_generator",
            "cfg_reader",
            "parse_javascript_ast",
        ]

        missing_tools = [t for t in expected_tools if t not in tool_names]
        if missing_tools:
            print(f"⚠️  Missing expected tools: {missing_tools}")
        else:
            print("✅ All expected tools are available")

        # Run analysis
        print("\n" + "=" * 80)
        print("Starting Repository Analysis")
        print("=" * 80)
        print("\n⏳ This will take 10-30 minutes depending on repository size...")
        print("   The workflow will:")
        print("   1. Run CodeQL static analysis")
        print("   2. Parse SARIF results")
        print("   3. Generate CFG for critical files")
        print("   4. Read and summarize CFG results")
        print("   5. Parse AST for code structure")
        print("   6. Analyze all findings with LLM")
        print()

        result = agent.analyze_repository(
            repository_path=REPOSITORY_PATH,
            output_dir="output/juice-shop",
        )

        # Analyze results
        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)

        print(f"\nRepository: {result['repository_path']}")
        print(f"Analysis Date: {result['analysis_date']}")
        print(f"Iterations: {result['iterations']}")
        print(f"Tool Calls: {len(result['intermediate_steps'])}")

        # Analyze tool usage
        tool_usage = {}
        for step in result.get("intermediate_steps", []):
            tool_name = step.get("tool", "unknown")
            tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1

        print(f"\n📊 Tool Usage Statistics:")
        for tool, count in sorted(tool_usage.items(), key=lambda x: x[1], reverse=True):
            print(f"   {tool}: {count} calls")

        # Verify all tools were used
        critical_tools = ["codeql_auto_analyze", "parse_codeql_sarif"]
        used_critical = [t for t in critical_tools if t in tool_usage]
        
        if len(used_critical) == len(critical_tools):
            print("\n✅ All critical tools were used")
        else:
            print(f"\n⚠️  Some critical tools were not used: {[t for t in critical_tools if t not in tool_usage]}")

        # Check if CFG tools were used
        cfg_tools_used = any(t in tool_usage for t in ["cfg_generator", "cfg_reader"])
        ast_tool_used = "parse_javascript_ast" in tool_usage

        print(f"\n📈 Analysis Tools Usage:")
        print(f"   CFG tools (generator/reader): {'✅ Used' if cfg_tools_used else '❌ Not used'}")
        print(f"   AST parser: {'✅ Used' if ast_tool_used else '❌ Not used'}")

        # Display analysis output
        print("\n" + "-" * 80)
        print("ANALYSIS RESULTS")
        print("-" * 80)
        output = result.get("output", "")
        if output:
            # Truncate if too long
            if len(output) > 2000:
                print(output[:2000])
                print("\n... [truncated, see full report in output file]")
            else:
                print(output)
        else:
            print("No output generated")

        # Save full report
        output_file = Path("output/juice-shop/workflow_test_report.txt")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("Workflow Test Report\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Repository: {result['repository_path']}\n")
            f.write(f"Analysis Date: {result['analysis_date']}\n")
            f.write(f"Iterations: {result['iterations']}\n")
            f.write(f"Tool Calls: {len(result['intermediate_steps'])}\n\n")
            f.write("Tool Usage:\n")
            for tool, count in sorted(tool_usage.items(), key=lambda x: x[1], reverse=True):
                f.write(f"  {tool}: {count}\n")
            f.write("\n" + "=" * 80 + "\n")
            f.write("ANALYSIS RESULTS\n")
            f.write("=" * 80 + "\n\n")
            f.write(output)
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("INTERMEDIATE STEPS\n")
            f.write("=" * 80 + "\n\n")
            for i, step in enumerate(result['intermediate_steps'], 1):
                f.write(f"Step {i}: {step.get('tool', 'Unknown')}\n")
                f.write("-" * 40 + "\n")
                content = step.get('content', '')
                if len(content) > 500:
                    content = content[:500] + "\n... [truncated]"
                f.write(f"{content}\n\n")

        print(f"\n✅ Full report saved to: {output_file}")

        # Save JSON report
        json_file = output_file.with_suffix(".json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)

        print(f"✅ JSON report saved to: {json_file}")

        # Analyze token usage
        print("\n" + "=" * 80)
        print("Analyzing Token Usage...")
        print("=" * 80)
        try:
            from monitor_llm_input import analyze_agent_execution, print_analysis
            token_analysis = analyze_agent_execution(result['intermediate_steps'])
            print_analysis(token_analysis)
        except Exception as e:
            print(f"Could not analyze token usage: {e}")

        # Final summary
        print("\n" + "=" * 80)
        if cfg_tools_used and ast_tool_used:
            print("✅ WORKFLOW TEST PASSED")
            print("   All tools (CodeQL, SARIF, CFG, AST) were used successfully")
        elif cfg_tools_used or ast_tool_used:
            print("⚠️  WORKFLOW TEST PARTIALLY PASSED")
            print("   Some analysis tools were not used")
        else:
            print("❌ WORKFLOW TEST FAILED")
            print("   CFG and AST tools were not used")
        print("=" * 80)

        return cfg_tools_used and ast_tool_used

    except Exception as e:
        print(f"\n❌ Error during workflow test: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_full_workflow()
    sys.exit(0 if success else 1)

