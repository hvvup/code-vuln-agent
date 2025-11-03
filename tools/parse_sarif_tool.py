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

    def _run(self, file_path: str, return_format: str = "json"):
        findings = SARIFParser.parse_sarif(file_path)
        if return_format == "summary":
            lines = []
            for f in findings:
                file = f["locations"][0]["file"] if f["locations"] else "<unknown>"
                lines.append(
                    f"[{f['severity'].upper()}] {f['ruleId']} - {f['message']} ({file})"
                )
            return "\n".join(lines)
        return findings

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async parsing not supported.")
