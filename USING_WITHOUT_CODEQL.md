# Using the Agent Without CodeQL

You can absolutely use the vulnerability analysis agent without CodeQL! This guide shows you how.

## Why Use Without CodeQL?

You might want to skip CodeQL if:
- You don't have Docker installed
- You want faster analysis (no Docker overhead)
- You only need CFG-based analysis
- You're analyzing code patterns that CFG analysis is better suited for
- You want to reduce dependencies

## Option 1: Use the `use_codeql=False` Parameter (Recommended)

This is the simplest way:

```python
from langchain_openai import ChatOpenAI
from agents import VulnerabilityAnalysisAgent

llm = ChatOpenAI(model="gpt-4", temperature=0)

# Create agent WITHOUT CodeQL
agent = VulnerabilityAnalysisAgent(
    llm=llm,
    verbose=True,
    use_codeql=False,  # Disables CodeQL and SARIF parser
)

# Use it normally
result = agent.analyze_file("myfile.js")
print(result["output"])
```

The agent will:
- ✅ Only include the CFG generator tool
- ✅ Use a different system prompt optimized for CFG-only analysis
- ✅ Not require Docker
- ✅ Still detect vulnerabilities through reasoning and control flow analysis

## Option 2: Provide Custom Tools List

For more control, you can specify exactly which tools to use:

```python
from agents import VulnerabilityAnalysisAgent
from tools import CFGGeneratorTool

# Create custom tools list
my_tools = [CFGGeneratorTool()]

# Create agent with only these tools
agent = VulnerabilityAnalysisAgent(
    llm=llm,
    tools=my_tools,  # Custom tools override defaults
)
```

You can also add your own custom tools:

```python
from langchain.tools import BaseTool

class MyCustomTool(BaseTool):
    name = "my_analyzer"
    description = "Custom analysis tool"

    def _run(self, input_str: str):
        # Your custom analysis logic
        return "analysis results"

my_tools = [
    CFGGeneratorTool(),
    MyCustomTool(),
]

agent = VulnerabilityAnalysisAgent(llm=llm, tools=my_tools)
```

## What Analysis Can You Do Without CodeQL?

### CFG-Based Vulnerability Detection

The agent can still find many vulnerabilities using CFG analysis and LLM reasoning:

#### ✅ Detectable Without CodeQL:

1. **Authentication/Authorization Flaws**
   - Missing authentication checks
   - Broken access control
   - Privilege escalation paths

2. **Business Logic Vulnerabilities**
   - Race conditions
   - Logic errors in workflows
   - Incorrect state transitions

3. **Data Flow Issues**
   - Unvalidated input reaching sensitive sinks
   - Missing sanitization
   - Data exposure through control flow

4. **Code Quality Issues**
   - Dead code
   - Unreachable error handlers
   - Complex control flow patterns

#### ⚠️ Harder Without CodeQL:

1. **Known CVE Patterns** - CodeQL has pre-built queries for these
2. **Complex Regex Patterns** - CodeQL excels at pattern matching
3. **CWE Categorization** - CodeQL provides automatic CWE tagging

### How CFG Analysis Works

The CFG (Control Flow Graph) generator provides:

1. **`cfg.json`** - Complete control flow graph
   - Nodes (code blocks)
   - Edges (control flow transitions)
   - Entry and exit points

2. **`node_spans.json`** - Source location mapping
   - Line numbers for each node
   - Column positions
   - Code ranges

3. **`line2node.json`** - Line-to-node mapping
   - Which nodes cover which lines
   - Useful for correlating code with CFG

4. **`paths.json`** - Execution paths
   - All possible paths through the code
   - Loop unrolling
   - Branch coverage

5. **`sampled_blocks.json`** - Token-aware sampling
   - Important code blocks selected by policy
   - Respects LLM token limits

The agent can reason about:
- Where user input enters the system
- How data flows through the program
- Which paths lead to sensitive operations
- Missing validation or authorization checks

## Example: Full Analysis Without CodeQL

```python
from langchain_openai import ChatOpenAI
from agents import VulnerabilityAnalysisAgent

llm = ChatOpenAI(model="gpt-4", temperature=0)

agent = VulnerabilityAnalysisAgent(
    llm=llm,
    use_codeql=False,
    verbose=True,
    max_iterations=15,
)

# The agent will:
# 1. Generate CFG for the file
# 2. Analyze control flow paths
# 3. Reason about data flow
# 4. Identify vulnerabilities
# 5. Provide remediation advice

result = agent.analyze_file("tests/sample_vulnerable_code.js")

print("\n=== VULNERABILITIES FOUND ===")
print(result["output"])
```

## Running the Example

```bash
# Run the no-CodeQL example
python example_usage_no_codeql.py
```

This example demonstrates:
- Creating an agent without CodeQL
- Analyzing files with CFG-only mode
- Using custom tools lists

## Performance Comparison

| Aspect | With CodeQL | Without CodeQL |
|--------|-------------|----------------|
| Setup | Requires Docker | No Docker needed |
| Speed | Slower (Docker overhead) | Faster |
| Vulnerabilities Found | More (pattern-based) | Fewer but context-aware |
| False Positives | More (needs verification) | Fewer (LLM reasoning) |
| Dependencies | Docker + CodeQL image | Just Python packages |
| Best For | Known CVEs, patterns | Logic flaws, business rules |

## Recommended Use Cases

### Use CFG-Only When:
- ✅ Analyzing business logic
- ✅ Finding authentication/authorization bugs
- ✅ Understanding complex control flow
- ✅ Docker is not available
- ✅ You need fast iteration

### Use With CodeQL When:
- ✅ Scanning for known vulnerability patterns
- ✅ Need CWE categorization
- ✅ Want comprehensive coverage
- ✅ Analyzing unfamiliar codebases
- ✅ Compliance requirements (SARIF reports)

### Use Both (Default):
- ✅ Most comprehensive analysis
- ✅ Combines pattern matching + reasoning
- ✅ Best for production security reviews

## Custom Prompts for CFG-Only Analysis

You can customize the analysis focus by modifying `prompts/agent_prompts.py`:

```python
# Edit AGENT_SYSTEM_PROMPT_NO_CODEQL to focus on specific areas
AGENT_SYSTEM_PROMPT_NO_CODEQL = """
You are a security expert specializing in authentication vulnerabilities.

Focus your analysis on:
1. Missing authentication checks
2. Authorization bypass opportunities
3. Session management issues
4. Token validation problems

Use the CFG to trace:
- How users access protected resources
- Where authentication checks occur (or don't)
- Alternative code paths that bypass security
...
"""
```

## Troubleshooting

### "No vulnerabilities found"

If the CFG-only agent doesn't find issues:
1. Increase `max_iterations` for deeper analysis
2. Use a more powerful model (GPT-4, Claude 3.5 Sonnet)
3. Provide more specific queries
4. Check if the code actually has security issues

### "CFG generation failed"

If CFG generation fails:
1. Ensure the JavaScript file is valid
2. Check file path is correct
3. Look at error messages in verbose mode
4. Verify esprima can parse the syntax

### "Agent keeps saying it needs CodeQL"

The agent might hallucinate needing CodeQL if:
1. The prompt still mentions it (check `AGENT_SYSTEM_PROMPT_NO_CODEQL`)
2. Previous context mentioned CodeQL
3. Use a fresh agent instance with `use_codeql=False`

## Combining Approaches

You can also run both separately and compare:

```python
# Analyze with CodeQL
agent_full = VulnerabilityAnalysisAgent(llm=llm, use_codeql=True)
result_full = agent_full.analyze_file("file.js")

# Analyze without CodeQL
agent_cfg = VulnerabilityAnalysisAgent(llm=llm, use_codeql=False)
result_cfg = agent_cfg.analyze_file("file.js")

# Compare findings
print("CodeQL + CFG found:", result_full["output"])
print("\nCFG-only found:", result_cfg["output"])
```

## Summary

**Yes, you can absolutely use the agent without CodeQL!**

Just use:
```python
agent = VulnerabilityAnalysisAgent(llm=llm, use_codeql=False)
```

The agent will work perfectly fine using only CFG analysis and LLM reasoning. It's particularly good at finding logic vulnerabilities that static analyzers miss.

For the most comprehensive analysis, use both (default behavior), but CFG-only mode is perfect when you need fast, dependency-free analysis.
