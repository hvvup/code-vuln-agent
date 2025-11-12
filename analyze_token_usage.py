"""Analyze what information is being sent to LLM and identify token usage issues."""

import json
from pathlib import Path
from typing import Dict, Any, List

def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 characters per token."""
    return len(text) // 4

def analyze_sarif_size(sarif_path: str) -> Dict[str, Any]:
    """Analyze SARIF file size and content."""
    path = Path(sarif_path)
    if not path.exists():
        return {"error": "File not found"}
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    findings = []
    for run in data.get("runs", []):
        findings.extend(run.get("results", []))
    
    # Full JSON size
    full_json = json.dumps(findings, indent=2)
    full_tokens = estimate_tokens(full_json)
    
    # Summary format size
    summary_lines = []
    for f in findings[:100]:  # Limit to first 100
        file = f.get("locations", [{}])[0].get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "<unknown>")
        summary_lines.append(
            f"[{f.get('level', 'unknown').upper()}] {f.get('ruleId', 'Unknown')} - {f.get('message', {}).get('text', '')[:80]} ({file})"
        )
    summary_text = "\n".join(summary_lines)
    summary_tokens = estimate_tokens(summary_text)
    
    return {
        "total_findings": len(findings),
        "full_json_tokens": full_tokens,
        "summary_tokens": summary_tokens,
        "token_savings": full_tokens - summary_tokens,
        "savings_percentage": ((full_tokens - summary_tokens) / full_tokens * 100) if full_tokens > 0 else 0,
    }

def analyze_cfg_size(cfg_path: str) -> Dict[str, Any]:
    """Analyze CFG file size."""
    path = Path(cfg_path)
    if not path.exists():
        return {"error": "File not found"}
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    full_json = json.dumps(data, indent=2)
    full_tokens = estimate_tokens(full_json)
    
    # Simulate CFG reader summary
    total_functions = sum(len(f.get("functions", [])) for f in data.get("files", []))
    total_nodes = sum(
        len(node)
        for file_info in data.get("files", [])
        for func in file_info.get("functions", [])
        for node in func.get("nodes", [])
    )
    
    # Estimate summary size (100 nodes max)
    summary_size = min(100, total_nodes) * 50  # ~50 chars per node summary
    summary_tokens = estimate_tokens(str(summary_size))
    
    return {
        "total_files": len(data.get("files", [])),
        "total_functions": total_functions,
        "total_nodes": total_nodes,
        "full_json_tokens": full_tokens,
        "estimated_summary_tokens": summary_tokens,
        "token_savings": full_tokens - summary_tokens,
        "savings_percentage": ((full_tokens - summary_tokens) / full_tokens * 100) if full_tokens > 0 else 0,
    }

def analyze_prompt_size() -> Dict[str, Any]:
    """Analyze system prompt size."""
    from prompts.agent_prompts import AGENT_SYSTEM_PROMPT
    
    tokens = estimate_tokens(AGENT_SYSTEM_PROMPT)
    
    return {
        "prompt_tokens": tokens,
        "prompt_length": len(AGENT_SYSTEM_PROMPT),
    }

def analyze_tool_outputs(output_dir: str = "output/juice-shop") -> Dict[str, Any]:
    """Analyze all tool outputs in the output directory."""
    output_path = Path(output_dir)
    
    results = {
        "sarif_files": [],
        "cfg_files": [],
        "total_estimated_tokens": 0,
    }
    
    # Find SARIF files
    sarif_files = list(output_path.rglob("*.sarif"))
    for sarif_file in sarif_files[:5]:  # Analyze first 5
        analysis = analyze_sarif_size(str(sarif_file))
        if "error" not in analysis:
            results["sarif_files"].append({
                "file": str(sarif_file),
                **analysis
            })
            results["total_estimated_tokens"] += analysis.get("full_json_tokens", 0)
    
    # Find CFG files
    cfg_files = list(output_path.rglob("cfg.json"))
    for cfg_file in cfg_files[:5]:  # Analyze first 5
        analysis = analyze_cfg_size(str(cfg_file))
        if "error" not in analysis:
            results["cfg_files"].append({
                "file": str(cfg_file),
                **analysis
            })
            results["total_estimated_tokens"] += analysis.get("full_json_tokens", 0)
    
    # Analyze prompt
    prompt_analysis = analyze_prompt_size()
    results["system_prompt"] = prompt_analysis
    results["total_estimated_tokens"] += prompt_analysis["prompt_tokens"]
    
    return results

def main():
    """Main analysis function."""
    print("\n" + "=" * 80)
    print("TOKEN USAGE ANALYSIS")
    print("=" * 80)
    
    # Analyze output directory
    results = analyze_tool_outputs()
    
    print("\n📊 System Prompt:")
    print(f"   Tokens: {results['system_prompt']['prompt_tokens']}")
    print(f"   Length: {results['system_prompt']['prompt_length']} characters")
    
    print("\n📄 SARIF Files Analysis:")
    if results["sarif_files"]:
        for sarif in results["sarif_files"]:
            print(f"\n   File: {Path(sarif['file']).name}")
            print(f"   Total Findings: {sarif['total_findings']}")
            print(f"   Full JSON Tokens: {sarif['full_json_tokens']:,}")
            print(f"   Summary Tokens: {sarif['summary_tokens']:,}")
            print(f"   Potential Savings: {sarif['token_savings']:,} tokens ({sarif['savings_percentage']:.1f}%)")
            print(f"   ⚠️  RECOMMENDATION: Use return_format='summary' to save {sarif['token_savings']:,} tokens")
    else:
        print("   No SARIF files found")
    
    print("\n🔷 CFG Files Analysis:")
    if results["cfg_files"]:
        for cfg in results["cfg_files"]:
            print(f"\n   File: {Path(cfg['file']).name}")
            print(f"   Total Functions: {cfg['total_functions']}")
            print(f"   Total Nodes: {cfg['total_nodes']:,}")
            print(f"   Full JSON Tokens: {cfg['full_json_tokens']:,}")
            print(f"   Summary Tokens (estimated): {cfg['estimated_summary_tokens']:,}")
            print(f"   Potential Savings: {cfg['token_savings']:,} tokens ({cfg['savings_percentage']:.1f}%)")
            print(f"   ⚠️  RECOMMENDATION: Use cfg_reader tool to save {cfg['token_savings']:,} tokens")
    else:
        print("   No CFG files found")
    
    print("\n" + "=" * 80)
    print("TOTAL ESTIMATED TOKENS (if all tools return full data):")
    print(f"   {results['total_estimated_tokens']:,} tokens")
    print("=" * 80)
    
    print("\n💡 RECOMMENDATIONS:")
    print("   1. Use parse_codeql_sarif with return_format='summary'")
    print("   2. Always use cfg_reader after cfg_generator")
    print("   3. Limit the number of files analyzed with CFG/AST")
    print("   4. Use max_nodes parameter in cfg_reader (default: 100)")
    
    # Save analysis
    report_file = Path("output/juice-shop/token_analysis.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Analysis saved to: {report_file}")

if __name__ == "__main__":
    main()

