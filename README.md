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

- [ ] Project structure setup
- [ ] AST parser implementation
- [ ] CFG generator implementation
- [x] CodeQL integration
- [ ] LangChain agent design
- [ ] LLM prompt engineering
- [ ] Visualization and reporting
