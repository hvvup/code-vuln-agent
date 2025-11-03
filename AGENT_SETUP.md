# Agent Implementation - Setup Complete

This document summarizes the vulnerability analysis agent implementation.

## What Was Implemented

### 1. LangChain Tools (✅ Complete)

All tools have been updated and registered:

- **`tools/codeql_tool.py`**: CodeQL static analysis via Docker
- **`tools/parse_sarif_tool.py`**: SARIF result parser
- **`tools/cfg_generator_tool.py`**: Control Flow Graph generator
- **`tools/__init__.py`**: Exports all three tools

### 2. Prompt Templates (✅ Complete)

Created comprehensive prompts for the agent:

- **`prompts/agent_prompts.py`**: System prompts and templates
  - `AGENT_SYSTEM_PROMPT`: Agent's role and capabilities
  - `ANALYSIS_PROMPT_TEMPLATE`: File analysis request format
  - `VULNERABILITY_REPORT_TEMPLATE`: Report structure
- **`prompts/__init__.py`**: Exports all prompts

### 3. Autonomous Agent (✅ Complete)

Implemented ReAct-based agent:

- **`agents/vulnerability_agent.py`**: Main agent implementation
  - `VulnerabilityAnalysisAgent`: Core agent class
  - `create_vulnerability_agent()`: Factory function
  - Supports single/multi-file analysis
  - Custom query capability
- **`agents/__init__.py`**: Exports agent classes
- **`agents/README.md`**: Comprehensive usage documentation

### 4. Examples and Tests (✅ Complete)

Created working examples:

- **`example_usage.py`**: Complete usage examples
  - Single file analysis
  - Multi-file batch processing
  - Custom security queries
  - Both OpenAI and Anthropic configurations
- **`tests/sample_vulnerable_code.js`**: Sample vulnerable code with 8 different vulnerability types for testing

### 5. Documentation Updates (✅ Complete)

- **`CLAUDE.md`**: Updated with agent usage and architecture
- **`requirements.txt`**: Updated with correct LangChain versions

## Quick Start

### 1. Install Dependencies

```bash
pip install -r vulnerability_analyzer/requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
cp vulnerability_analyzer/.env.example vulnerability_analyzer/.env
```

Add your API key to `.env`:

```bash
# For OpenAI
OPENAI_API_KEY=your_key_here

# OR for Anthropic Claude
ANTHROPIC_API_KEY=your_key_here
```

### 3. Ensure Docker is Running

```bash
docker pull ghcr.io/github/codeql-cli2:latest
```

### 4. Run Example

```bash
python vulnerability_analyzer/example_usage.py
```

## Usage Examples

### Example 1: Analyze a Single File (Full Mode - with CodeQL)

```python
from langchain_openai import ChatOpenAI
from agents import VulnerabilityAnalysisAgent

# Create agent with CodeQL (default)
llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = VulnerabilityAnalysisAgent(llm=llm, verbose=True)

# Analyze
result = agent.analyze_file("tests/sample_vulnerable_code.js")

print(f"Analysis completed in {result['iterations']} iterations")
print(result["output"])
```

### Example 1b: Analyze WITHOUT CodeQL (No Docker Required)

```python
from langchain_openai import ChatOpenAI
from agents import VulnerabilityAnalysisAgent

# Create agent WITHOUT CodeQL
llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = VulnerabilityAnalysisAgent(
    llm=llm,
    verbose=True,
    use_codeql=False,  # Disable CodeQL - only use CFG analysis
)

# Analyze (works without Docker!)
result = agent.analyze_file("tests/sample_vulnerable_code.js")
print(result["output"])
```

**📖 See `USING_WITHOUT_CODEQL.md` for complete guide on CFG-only analysis.**

### Example 2: Custom Security Query

```python
# Ask specific questions
result = agent.query("""
    Analyze sample_vulnerable_code.js for SQL injection vulnerabilities.
    For each finding, explain:
    1. Why it's vulnerable
    2. How an attacker could exploit it
    3. How to fix it
""")

print(result["answer"])
```

### Example 3: Batch Analysis

```python
# Analyze multiple files
files = ["auth.js", "api.js", "database.js"]
results = agent.analyze_multiple_files(files)

for result in results:
    print(f"\n=== {result['file_path']} ===")
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(result["output"])
```

## How the Agent Works

### ReAct Pattern

The agent uses ReAct (Reasoning + Acting):

```
1. Receive task (analyze file X)
2. Think: "I should run CodeQL first to find known vulnerabilities"
3. Act: Call codeql_auto_analyze tool
4. Observe: SARIF file path returned
5. Think: "Now I need to parse the SARIF results"
6. Act: Call parse_codeql_sarif tool
7. Observe: List of 5 vulnerabilities found
8. Think: "I should generate CFG to verify data flow for SQL injection"
9. Act: Call cfg_generator tool
10. Observe: CFG generated successfully
11. Think: "I have enough information to provide analysis"
12. Final Answer: Comprehensive vulnerability report
```

### Available Tools

1. **`codeql_auto_analyze`**
   - Input: Source file path, query suite (optional)
   - Output: SARIF file path
   - Purpose: Run static analysis

2. **`parse_codeql_sarif`**
   - Input: SARIF file path, return format
   - Output: Structured findings or summary
   - Purpose: Extract vulnerabilities from SARIF

3. **`cfg_generator`**
   - Input: JSON payload with files and options
   - Output: Paths to generated CFG artifacts
   - Purpose: Control flow analysis

## Agent Configuration Options

```python
agent = VulnerabilityAnalysisAgent(
    llm=llm,                      # Required: LLM instance
    verbose=True,                 # Show reasoning steps
    max_iterations=15,            # Max reasoning loops
    max_execution_time=300,       # Timeout in seconds
)
```

## Testing the Implementation

### Test with Sample Vulnerable Code

The `tests/sample_vulnerable_code.js` file contains 8 intentional vulnerabilities:

1. SQL Injection (user endpoint)
2. Command Injection (backup endpoint)
3. Cross-Site Scripting (search endpoint)
4. Path Traversal (download endpoint)
5. Insecure Authentication (login endpoint)
6. Insecure Deserialization (eval usage)
7. Missing Access Control (admin delete)
8. Information Disclosure (error details)

Run the agent on this file to see how it detects and analyzes these vulnerabilities.

## Customization

### Modify Agent Behavior

Edit `prompts/agent_prompts.py` to change:
- Focus areas (e.g., prioritize certain vulnerability types)
- Output format (report structure)
- Analysis depth (how thorough the agent should be)

### Add New Tools

To add a new analysis tool:

1. Create tool in `tools/new_tool.py`:
```python
from langchain.tools import BaseTool
from pydantic import BaseModel

class NewToolInput(BaseModel):
    param: str

class NewTool(BaseTool):
    name = "new_tool"
    description = "What this tool does"
    args_schema = NewToolInput

    def _run(self, param: str):
        # Implementation
        return result
```

2. Export from `tools/__init__.py`
3. Agent will automatically have access to it

## Troubleshooting

### "Docker command failed"
- Ensure Docker is running
- Pull the CodeQL image: `docker pull ghcr.io/github/codeql-cli2:latest`

### "API key not found"
- Create `.env` file with `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
- Use `python-dotenv` to load it: `load_dotenv()`

### "Module not found"
- Install all dependencies: `pip install -r vulnerability_analyzer/requirements.txt`

### Agent doesn't find vulnerabilities
- Try increasing `max_iterations`
- Use a more capable model (GPT-4 or Claude 3.5 Sonnet)
- Check if CodeQL is working: test tools individually

## Next Steps

1. **Test the agent** with your own JavaScript files
2. **Customize prompts** for your specific security requirements
3. **Add visualization** for CFG and analysis results
4. **Implement reporting** to generate PDF/HTML reports
5. **Add more tools** (e.g., dependency scanning, secret detection)

## Architecture Diagram

```
User Request
    ↓
VulnerabilityAnalysisAgent (ReAct Pattern)
    ↓
┌─────────────────────────────────────┐
│  Tools (LangChain Wrappers)         │
├─────────────────────────────────────┤
│  • CodeQL Tool                      │
│  • SARIF Parser Tool                │
│  • CFG Generator Tool               │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Core Logic (Framework-agnostic)    │
├─────────────────────────────────────┤
│  • CodeQL Docker Executor           │
│  • SARIF Parser                     │
│  • JavaScript Parser (esprima)      │
│  • CFG Builder & Generator          │
└─────────────────────────────────────┘
    ↓
Analysis Results
```

## Support

For issues or questions:
- Check `agents/README.md` for detailed agent documentation
- See `example_usage.py` for working code examples
- Review `CLAUDE.md` for architecture overview
