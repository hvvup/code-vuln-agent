from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
from core.sarif_parser import SARIFParser


class ParseSarifInput(BaseModel):
    file_path: str = Field(..., description="Path to SARIF file")
    return_format: Optional[str] = Field(
        default="json", description="Output type: json or summary"
    )


class ParseSarifTool(BaseTool):
    name: str = "parse_codeql_sarif"
    description: str = (
        "Parse a CodeQL SARIF report file and extract structured vulnerability findings. "
        "Takes the file path to a SARIF file (returned by codeql_auto_analyze) and returns "
        "detailed information about each finding including rule IDs, severity levels, messages, "
        "file locations, and CWE mappings. Use this immediately after running CodeQL analysis "
        "to review and understand the static analysis results."
    )
    args_schema: type[BaseModel] = ParseSarifInput

    def _run(self, file_path: str, return_format: str = "summary"):
        """
        Parse SARIF file. Default to 'summary' format to save tokens.
        
        Args:
            file_path: Path to SARIF file
            return_format: 'summary' (compact text) or 'json' (full structured data)
        """
        findings = SARIFParser.parse_sarif(file_path)
        
        if return_format == "summary":
            # Compact summary format
            if not findings:
                return "No vulnerabilities found."
            
            lines = []
            # Group by severity
            severity_counts = {}
            for f in findings:
                severity = f.get("severity", "unknown")
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            lines.append(f"Total: {len(findings)} findings")
            for severity, count in sorted(severity_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {severity.upper()}: {count}")
            lines.append("")
            
            # Top findings (limit to 50 to save tokens)
            for f in findings[:50]:
                file = f["locations"][0]["file"] if f["locations"] else "<unknown>"
                line = f["locations"][0].get("startLine", "?") if f["locations"] else "?"
                message = f['message'][:80]  # Truncate long messages
                lines.append(
                    f"[{f['severity'].upper()}] {f['ruleId']} - {message} ({file}:{line})"
                )
            
            if len(findings) > 50:
                lines.append(f"\n... and {len(findings) - 50} more findings")
            
            return "\n".join(lines)
        
        # Full JSON format (use with caution - can be very large)
        return findings

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async parsing not supported.")
