# Vulnerability Analysis Agent

This directory contains the autonomous agent implementation for vulnerability analysis.

## Overview

The `VulnerabilityAnalysisAgent` uses the ReAct (Reasoning + Acting) pattern to autonomously analyze JavaScript code for security vulnerabilities. It combines static analysis tools with LLM reasoning to:

1. Detect vulnerabilities that traditional static analyzers miss
2. Filter false positives from static analysis
3. Provide context-aware security insights
4. Generate actionable remediation recommendations

## How It Works

### ReAct Pattern

The agent follows the ReAct pattern:

```
Question → Thought → Action → Observation → ... → Final Answer
```

At each step, the agent:
1. **Thinks** about what information it needs
2. **Acts** by calling one of the available tools
3. **Observes** the tool's output
4. **Reasons** about the next step

This continues until the agent has enough information to provide a final answer.

### Available Tools

The agent has access to three specialized tools:

#### 1. CodeQL Tool (`codeql_auto_analyze`)
- Runs CodeQL static analysis using Docker
- Scans for known vulnerability patterns
- Returns SARIF-formatted results
- No local CodeQL installation required

#### 2. SARIF Parser Tool (`parse_codeql_sarif`)
- Parses CodeQL SARIF output
- Extracts vulnerability findings
- Normalizes severity levels and CWE mappings
- Can return JSON or human-readable summary

#### 3. CFG Generator Tool (`cfg_generator`)
- Generates Control Flow Graphs from JavaScript
- Produces multiple analysis artifacts:
  - `cfg.json`: Complete CFG structure
  - `node_spans.json`: Source location mapping
  - `line2node.json`: Line-to-node mapping
  - `paths.json`: Enumerated execution paths
  - `sampled_blocks.json`: Token-budget-aware samples

## Usage

### Basic Usage

```python
from langchain_openai import ChatOpenAI
from agents import create_vulnerability_agent

# Initialize with your preferred LLM
llm = ChatOpenAI(model="gpt-4", temperature=0)

# Create the agent
agent = create_vulnerability_agent(llm=llm, verbose=True)

# Analyze a file
result = agent.analyze_file("path/to/vulnerable.js")
print(result["output"])
```

### Advanced Configuration

```python
from agents import VulnerabilityAnalysisAgent

agent = VulnerabilityAnalysisAgent(
    llm=llm,
    verbose=True,
    max_iterations=20,  # Maximum reasoning steps
    max_execution_time=600,  # 10 minutes timeout
)

# Analyze multiple files
results = agent.analyze_multiple_files([
    "file1.js",
    "file2.js",
    "file3.js"
])

# Custom queries
result = agent.query(
    "Check file.js for authentication bypass vulnerabilities"
)
```

### Return Format

The `analyze_file` method returns a dictionary:

```python
{
    "file_path": "/absolute/path/to/file.js",
    "analysis_date": "2025-11-02T14:30:00",
    "output": "Detailed vulnerability analysis...",
    "intermediate_steps": [
        (AgentAction(...), "observation"),
        ...
    ],
    "iterations": 8
}
```

## Analysis Strategy

The agent typically follows this strategy:

1. **Initial Scan**: Run CodeQL to detect known vulnerability patterns
2. **Parse Results**: Extract and normalize findings from SARIF output
3. **Deep Analysis**: Generate CFG for complex cases requiring data flow analysis
4. **Verification**: Use reasoning to verify if findings are exploitable
5. **Report**: Provide comprehensive analysis with remediation advice

## Prompt Engineering

The agent's behavior is controlled by prompts in `../prompts/agent_prompts.py`:

- `AGENT_SYSTEM_PROMPT`: Defines the agent's role and capabilities
- `ANALYSIS_PROMPT_TEMPLATE`: Template for file analysis requests
- `VULNERABILITY_REPORT_TEMPLATE`: Structure for final reports

You can customize these prompts to adjust the agent's focus areas or output format.

## LLM Provider Support

The agent works with any LangChain-compatible LLM:

### OpenAI
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4", temperature=0)
```

### Anthropic Claude
```python
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)
```

### Other Providers
Any `BaseChatModel` implementation from LangChain will work.

## Performance Considerations

- **Iterations**: More iterations allow deeper analysis but increase cost/time
- **LLM Model**: GPT-4 or Claude 3.5 Sonnet recommended for best results
- **Timeout**: Set `max_execution_time` to prevent runaway analysis
- **Verbose Mode**: Enable for debugging, disable for production

## Examples

See `../example_usage.py` for complete examples including:
- Single file analysis
- Batch processing multiple files
- Custom security queries
- Different LLM configurations

## Limitations

- Currently only supports JavaScript/TypeScript files
- Requires Docker for CodeQL analysis
- LLM API costs scale with file size and iterations
- Analysis quality depends on the LLM's reasoning capabilities
