"""Tool for summarizing SARIF results to reduce token usage."""

from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
from core.sarif_parser import SARIFParser


class SarifSummarizerInput(BaseModel):
    """Input schema for SARIF summarizer tool."""

    file_path: str = Field(..., description="Path to SARIF file")
    max_findings: int = Field(
        default=50,
        description="Maximum number of findings to include (default: 50)"
    )
    group_by_severity: bool = Field(
        default=True,
        description="Group findings by severity (default: True)"
    )


class SarifSummarizerTool(BaseTool):
    """
    Summarizes SARIF results in a compact format to reduce token usage.
    
    This tool provides a much more token-efficient summary than the full JSON format.
    """

    name: str = "sarif_summarizer"
    description: str = (
        "Get a compact summary of SARIF results to reduce token usage. "
        "Takes a SARIF file path and returns a concise text summary focusing on "
        "high-severity findings and key vulnerability patterns. "
        "Use this INSTEAD of parse_codeql_sarif when token budget is limited. "
        "The summary includes severity counts, top findings, and file locations."
    )
    args_schema: type[BaseModel] = SarifSummarizerInput

    def _run(
        self,
        file_path: str,
        max_findings: int = 50,
        group_by_severity: bool = True,
    ) -> str:
        """Summarize SARIF results."""
        findings = SARIFParser.parse_sarif(file_path)
        
        if not findings:
            return "No vulnerabilities found in SARIF report."
        
        # Group by severity
        severity_groups = {}
        for finding in findings:
            severity = finding.get("severity", "unknown")
            if severity not in severity_groups:
                severity_groups[severity] = []
            severity_groups[severity].append(finding)
        
        # Build summary
        summary_lines = []
        summary_lines.append(f"Total Findings: {len(findings)}")
        summary_lines.append("")
        
        if group_by_severity:
            summary_lines.append("By Severity:")
            for severity in ["error", "warning", "note", "unknown"]:
                if severity in severity_groups:
                    count = len(severity_groups[severity])
                    summary_lines.append(f"  {severity.upper()}: {count}")
            summary_lines.append("")
        
        # Top findings by severity
        summary_lines.append("Top Findings:")
        added = 0
        for severity in ["error", "warning", "note", "unknown"]:
            if severity in severity_groups and added < max_findings:
                for finding in severity_groups[severity][:max_findings - added]:
                    rule_id = finding.get("ruleId", "Unknown")
                    message = finding.get("message", "")[:100]  # Truncate
                    locations = finding.get("locations", [])
                    if locations:
                        loc = locations[0]
                        file_path = loc.get("file", "unknown")
                        line = loc.get("startLine", "?")
                        summary_lines.append(
                            f"  [{severity.upper()}] {rule_id} - {message} ({file_path}:{line})"
                        )
                    else:
                        summary_lines.append(
                            f"  [{severity.upper()}] {rule_id} - {message}"
                        )
                    added += 1
                    if added >= max_findings:
                        break
        
        if len(findings) > max_findings:
            summary_lines.append(f"\n... and {len(findings) - max_findings} more findings")
        
        return "\n".join(summary_lines)

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async not supported yet.")


__all__ = ["SarifSummarizerTool"]

