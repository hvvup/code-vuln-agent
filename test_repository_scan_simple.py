"""Simple test script for repository scanning without LLM (CodeQL only)."""

import os
from pathlib import Path
from dotenv import load_dotenv

from core.codeql_local_executor import CodeQLLocalExecutor
from core.codeql_docker_executor import CodeQLDockerExecutor

# Load environment variables
load_dotenv()


def test_juice_shop_codeql_only():
    """Test CodeQL scanning on juice-shop repository without LLM agent."""
    
    repository_path = r"D:\juice-shop"
    
    # Validate path exists
    repo_path = Path(repository_path)
    if not repo_path.exists():
        print(f"❌ Repository not found: {repository_path}")
        return
    
    if not repo_path.is_dir():
        print(f"❌ Path is not a directory: {repository_path}")
        return

    print("\n" + "=" * 80)
    print(f"Running CodeQL scan on: {repository_path}")
    print("=" * 80 + "\n")

    try:
        # Check if local CodeQL is available
        codeql_cli_path = os.getenv("CODEQL_CLI_PATH")
        
        if codeql_cli_path:
            print("Using local CodeQL CLI...")
            executor = CodeQLLocalExecutor(codeql_path=codeql_cli_path)
        else:
            print("Using Docker-based CodeQL...")
            executor = CodeQLDockerExecutor()

        # Run CodeQL analysis
        sarif_path = executor.analyze_repository(
            repository_path=repository_path,
            query_suite="javascript-security-extended.qls",
            language="javascript",
        )

        print(f"\n✅ CodeQL analysis complete!")
        print(f"SARIF report saved at: {sarif_path}")
        
        # Parse and display summary
        from core.sarif_parser import SARIFParser
        findings = SARIFParser.parse_sarif(sarif_path)
        
        print(f"\n📊 Summary:")
        print(f"  Total findings: {len(findings)}")
        
        # Group by severity
        severity_counts = {}
        for finding in findings:
            severity = finding.get("severity", "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        print(f"  By severity:")
        for severity, count in sorted(severity_counts.items()):
            print(f"    {severity}: {count}")
        
        # Show first 10 findings
        print(f"\n📋 First 10 findings:")
        for i, finding in enumerate(findings[:10], 1):
            print(f"\n  {i}. {finding.get('ruleId', 'Unknown')}")
            print(f"     Severity: {finding.get('severity', 'unknown')}")
            print(f"     CWE: {finding.get('cwe', 'N/A')}")
            print(f"     Message: {finding.get('message', '')[:100]}...")
            if finding.get('locations'):
                loc = finding['locations'][0]
                print(f"     Location: {loc.get('file', 'Unknown')}:{loc.get('startLine', '?')}")
        
        if len(findings) > 10:
            print(f"\n  ... and {len(findings) - 10} more findings")
        
    except Exception as e:
        print(f"\n❌ Error during CodeQL scan: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_juice_shop_codeql_only()

