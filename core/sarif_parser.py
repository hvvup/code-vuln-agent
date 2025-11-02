import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class SARIFParser:
    """Parses SARIF results from CodeQL and normalizes them."""

    @staticmethod
    def load_json(path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def extract_rules_map(runs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        rules_map = {}
        for run in runs:
            driver = run.get("tool", {}).get("driver", {})
            for rule in driver.get("rules", []):
                rid = rule.get("id")
                if rid:
                    rules_map[rid] = rule
        return rules_map

    @staticmethod
    def extract_cwe(rule_meta: Dict[str, Any]) -> Optional[str]:
        if not rule_meta:
            return None
        tags = rule_meta.get("properties", {}).get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        for t in tags:
            m = re.search(r"CWE[-_ ]?(\d+)", t, flags=re.I)
            if m:
                return f"CWE-{m.group(1)}"
        return None

    @staticmethod
    def parse_sarif(file_path: str) -> List[Dict[str, Any]]:
        path = Path(file_path)
        data = SARIFParser.load_json(path)
        runs = data.get("runs", [])
        rules_map = SARIFParser.extract_rules_map(runs)
        findings = []

        for run in runs:
            for res in run.get("results", []):
                rule_id = res.get("ruleId")
                rule_meta = rules_map.get(rule_id, {})
                message = res.get("message", {}).get("text", "")
                severity = res.get("level", "unknown")
                cwe = SARIFParser.extract_cwe(rule_meta)
                locations = res.get("locations", [])

                loc_list = []
                for loc in locations:
                    pl = loc.get("physicalLocation", {})
                    uri = pl.get("artifactLocation", {}).get("uri", "")
                    region = pl.get("region", {})
                    loc_list.append(
                        {
                            "file": uri,
                            "startLine": region.get("startLine"),
                            "endLine": region.get("endLine"),
                        }
                    )

                findings.append(
                    {
                        "ruleId": rule_id,
                        "message": message,
                        "severity": severity,
                        "cwe": cwe,
                        "locations": loc_list,
                    }
                )

        return findings
