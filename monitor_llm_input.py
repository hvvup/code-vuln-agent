"""Monitor what information is being sent to LLM during agent execution."""

import json
from typing import Dict, Any, List
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 characters per token."""
    return len(text) // 4


def analyze_message_content(content: Any) -> Dict[str, Any]:
    """Analyze a single message content."""
    if isinstance(content, str):
        return {
            "type": "text",
            "length": len(content),
            "tokens": estimate_tokens(content),
            "preview": content[:200] + "..." if len(content) > 200 else content,
        }
    elif isinstance(content, list):
        total_tokens = 0
        parts = []
        for part in content:
            if isinstance(part, dict):
                part_analysis = analyze_message_content(part.get("text", ""))
                total_tokens += part_analysis["tokens"]
                parts.append(part_analysis)
        return {
            "type": "multipart",
            "parts": len(parts),
            "tokens": total_tokens,
            "parts_detail": parts,
        }
    else:
        return {
            "type": "unknown",
            "tokens": 0,
        }


def analyze_tool_result(tool_name: str, content: str) -> Dict[str, Any]:
    """Analyze a tool result to estimate token usage."""
    analysis = {
        "tool": tool_name,
        "content_type": "unknown",
        "length": len(content),
        "tokens": estimate_tokens(content),
    }
    
    # Try to parse as JSON
    try:
        data = json.loads(content)
        if isinstance(data, list):
            analysis["content_type"] = "json_array"
            analysis["item_count"] = len(data)
            if tool_name == "parse_codeql_sarif":
                analysis["recommendation"] = f"Use return_format='summary' to reduce from {analysis['tokens']} to ~{analysis['tokens'] // 5} tokens"
        elif isinstance(data, dict):
            analysis["content_type"] = "json_object"
            if "files" in data and tool_name == "cfg_generator":
                analysis["recommendation"] = "Use cfg_reader tool to summarize CFG results"
            elif "key_functions" in data:
                analysis["content_type"] = "cfg_summary"
        else:
            analysis["content_type"] = "json_other"
    except:
        # Not JSON, treat as text
        analysis["content_type"] = "text"
        if tool_name == "parse_codeql_sarif" and analysis["tokens"] > 1000:
            analysis["recommendation"] = "Consider using return_format='summary'"
    
    # Add preview
    if analysis["length"] > 500:
        analysis["preview"] = content[:500] + "..."
    else:
        analysis["preview"] = content
    
    return analysis


def analyze_agent_execution(intermediate_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze what information was passed to LLM during agent execution."""
    analysis = {
        "total_steps": len(intermediate_steps),
        "tool_calls": {},
        "total_tool_tokens": 0,
        "recommendations": [],
    }
    
    for step in intermediate_steps:
        tool_name = step.get("tool", "unknown")
        content = step.get("content", "")
        
        if tool_name not in analysis["tool_calls"]:
            analysis["tool_calls"][tool_name] = {
                "count": 0,
                "total_tokens": 0,
                "samples": [],
            }
        
        tool_analysis = analyze_tool_result(tool_name, str(content))
        analysis["tool_calls"][tool_name]["count"] += 1
        analysis["tool_calls"][tool_name]["total_tokens"] += tool_analysis["tokens"]
        analysis["total_tool_tokens"] += tool_analysis["tokens"]
        
        # Keep sample of first call
        if len(analysis["tool_calls"][tool_name]["samples"]) == 0:
            analysis["tool_calls"][tool_name]["samples"].append(tool_analysis)
        
        # Add recommendations
        if "recommendation" in tool_analysis:
            analysis["recommendations"].append({
                "tool": tool_name,
                "recommendation": tool_analysis["recommendation"],
            })
    
    return analysis


def print_analysis(analysis: Dict[str, Any]):
    """Print analysis results in a readable format."""
    print("\n" + "=" * 80)
    print("LLM INPUT ANALYSIS")
    print("=" * 80)
    
    print(f"\n📊 Total Tool Calls: {analysis['total_steps']}")
    print(f"📊 Total Tool Output Tokens: {analysis['total_tool_tokens']:,}")
    
    print("\n🔧 Tool Usage Breakdown:")
    for tool_name, stats in sorted(analysis["tool_calls"].items(), key=lambda x: x[1]["total_tokens"], reverse=True):
        print(f"\n   {tool_name}:")
        print(f"      Calls: {stats['count']}")
        print(f"      Total Tokens: {stats['total_tokens']:,}")
        print(f"      Avg Tokens per Call: {stats['total_tokens'] // stats['count']:,}")
        
        if stats["samples"]:
            sample = stats["samples"][0]
            print(f"      Content Type: {sample['content_type']}")
            if "item_count" in sample:
                print(f"      Items: {sample['item_count']}")
            if sample["tokens"] > 1000:
                print(f"      ⚠️  LARGE OUTPUT: {sample['tokens']:,} tokens")
    
    if analysis["recommendations"]:
        print("\n💡 Recommendations:")
        for rec in analysis["recommendations"]:
            print(f"   - {rec['tool']}: {rec['recommendation']}")
    
    # Identify problematic tools
    print("\n⚠️  Token Usage Issues:")
    issues_found = False
    for tool_name, stats in analysis["tool_calls"].items():
        if stats["total_tokens"] > 2000:
            print(f"   - {tool_name}: {stats['total_tokens']:,} tokens (consider optimization)")
            issues_found = True
        
        if tool_name == "parse_codeql_sarif" and stats["total_tokens"] > 1000:
            print(f"   - {tool_name}: Use return_format='summary' to reduce tokens")
            issues_found = True
        
        if tool_name == "cfg_generator":
            print(f"   - {tool_name}: Make sure to use cfg_reader after this")
            issues_found = True
    
    if not issues_found:
        print("   ✅ No major token usage issues detected")


def main():
    """Analyze a workflow test result."""
    result_file = Path("output/juice-shop/workflow_test_report.json")
    
    if not result_file.exists():
        print(f"❌ Result file not found: {result_file}")
        print("Run test_workflow_juice_shop.py first to generate results.")
        return
    
    with open(result_file, "r", encoding="utf-8") as f:
        result = json.load(f)
    
    intermediate_steps = result.get("intermediate_steps", [])
    
    if not intermediate_steps:
        print("❌ No intermediate steps found in result")
        return
    
    analysis = analyze_agent_execution(intermediate_steps)
    print_analysis(analysis)
    
    # Save detailed analysis
    analysis_file = Path("output/juice-shop/llm_input_analysis.json")
    analysis_file.parent.mkdir(parents=True, exist_ok=True)
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n✅ Detailed analysis saved to: {analysis_file}")


if __name__ == "__main__":
    main()

