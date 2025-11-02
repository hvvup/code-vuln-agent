# Vulnerability Analyzer

AI-powered static code analysis tool combining CodeQL, AST analysis, and LLM reasoning.

## Architecture

```
vulnerability_analyzer/
├── tools/              # LangChain Tools (thin wrappers)
├── agents/             # Autonomous vulnerability analysis agent
├── core/               # Pure business logic (LangChain-independent)
├── prompts/            # LLM prompt templates
├── output/             # Generated reports and visualizations
└── tests/              # Sample vulnerable code for testing
```

## Design Principles

1. **Separation of Concerns**: Core logic independent from LangChain
2. **Autonomous Agent**: ReAct-based agent dynamically chooses analysis strategy
3. **Hybrid Approach**: Static analysis (CodeQL) + LLM context understanding
4. **Tool-Based Architecture**: Agent orchestrates multiple specialized tools

## Goals

- **Primary**: Detect vulnerabilities that static analyzers miss (context-aware)
- **Secondary**: Filter false positives from static analysis
- **Tertiary**: Provide actionable remediation suggestions

## Configuration

Copy `.env.example` to `.env` and update the values to match your local CodeQL
installation:

```
cp .env.example .env
```
## Development Status

- [x] Project structure setup
- [x] AST parser implementation
- [x] CFG generator implementation
- [x] CodeQL integration (Docker-based)
- [x] LangChain agent design (ReAct pattern)
- [x] LLM prompt engineering
- [x] Support for CodeQL-free analysis (CFG-only mode)
- [ ] Visualization and reporting

## Quick Start

See `AGENT_SETUP.md` for complete setup instructions.

### With CodeQL (Full Analysis)
```python
from langchain_openai import ChatOpenAI
from agents import VulnerabilityAnalysisAgent

llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = VulnerabilityAnalysisAgent(llm=llm, verbose=True)
result = agent.analyze_file("file.js")
```

### Without CodeQL (CFG-Only Analysis - No Docker)
```python
agent = VulnerabilityAnalysisAgent(
    llm=llm,
    use_codeql=False  # No Docker required!
)
result = agent.analyze_file("file.js")
```

📖 See `USING_WITHOUT_CODEQL.md` for details on CFG-only analysis.
