# Using CodeQL with Docker

This guide explains how to use CodeQL analysis with Docker in this vulnerability analyzer.

## Overview

The vulnerability analyzer supports **two Docker execution modes**:

1. **Ephemeral Containers (Default)**: Creates temporary containers that are automatically removed after analysis
2. **Running Container Reuse**: Uses `docker exec` on a persistent container for better performance

## Mode 1: Ephemeral Containers (Default)

This is the default mode - no setup required!

### Requirements
- Docker Desktop running
- Internet connection (to pull the CodeQL image on first run)

### Usage

```python
from langchain_openai import ChatOpenAI
from agents import create_vulnerability_agent

llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = create_vulnerability_agent(llm=llm, verbose=True)

# Analyze a file - will automatically create and cleanup containers
result = agent.analyze_file("tests/sample_vulnerable_code.js")
print(result['output'])
```

### How It Works

1. Downloads `ghcr.io/github/codeql-cli2:latest` image (first time only)
2. Creates a temporary container with `docker run --rm`
3. Mounts source files and runs CodeQL analysis
4. Returns results and automatically removes the container

### Pros & Cons

✅ **Pros**:
- No manual setup required
- Isolated execution (no state conflicts)
- Automatic cleanup

❌ **Cons**:
- Slower (creates new container each time)
- Downloads image every time if not cached

---

## Mode 2: Running Container Reuse

Use a persistent container for faster repeated analyses.

### Setup

#### Step 1: Start a CodeQL Container

```bash
# Pull the CodeQL image
docker pull ghcr.io/github/codeql-cli2:latest

# Start a persistent container
docker run -d \
  --name codeql-server \
  ghcr.io/github/codeql-cli2:latest \
  tail -f /dev/null
```

The container is now running in the background and ready to accept analysis requests.

#### Step 2: Configure Environment Variable

Create or edit `.env` file:

```bash
# Copy example
cp .env.example .env

# Edit .env and add:
CODEQL_CONTAINER_ID=codeql-server
```

Or set it temporarily:
```bash
export CODEQL_CONTAINER_ID=codeql-server  # Linux/Mac
set CODEQL_CONTAINER_ID=codeql-server     # Windows CMD
$env:CODEQL_CONTAINER_ID="codeql-server"  # Windows PowerShell
```

### Usage

Same Python code as before - it will automatically detect and use the running container:

```python
from langchain_openai import ChatOpenAI
from agents import create_vulnerability_agent

llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = create_vulnerability_agent(llm=llm, verbose=True)

# Will use the running container via docker exec
result = agent.analyze_file("tests/sample_vulnerable_code.js")
```

### How It Works

1. Validates the container exists and is running
2. Copies source file to container with `docker cp`
3. Runs CodeQL inside the container with `docker exec`
4. Copies SARIF results back to host
5. Container stays running for next analysis

### Pros & Cons

✅ **Pros**:
- **Much faster** (no container startup overhead)
- Great for repeated analyses
- Container stays warm

❌ **Cons**:
- Requires manual container management
- Potential state issues between runs (database overwrites)

### Managing the Container

```bash
# Check container status
docker ps -a | grep codeql-server

# Stop the container
docker stop codeql-server

# Start the container again
docker start codeql-server

# Remove the container
docker rm -f codeql-server

# View container logs
docker logs codeql-server
```

---

## Advanced: Direct API Usage

You can also use the executor directly without the agent:

```python
from core.codeql_docker_executor import CodeQLDockerExecutor

# Ephemeral mode
executor = CodeQLDockerExecutor()
sarif_path = executor.analyze_file("tests/sample_vulnerable_code.js")

# Running container mode
executor = CodeQLDockerExecutor(container_id="codeql-server")
sarif_path = executor.analyze_file("tests/sample_vulnerable_code.js")

# With custom Docker options (ephemeral only)
executor = CodeQLDockerExecutor(
    docker_args=["--memory=4g", "--cpus=2.0"]
)
sarif_path = executor.analyze_file("tests/sample_vulnerable_code.js")
```

---

## Troubleshooting

### Container Not Found

```
RuntimeError: Container 'codeql-server' not found
```

**Solution**: Start the container or check the name:
```bash
docker ps -a                    # List all containers
docker start codeql-server      # Start if stopped
```

### Container Not Running

```
RuntimeError: Container 'codeql-server' exists but is not running
```

**Solution**: Start the container:
```bash
docker start codeql-server
```

### Permission Denied (Linux)

If you get permission errors when using `docker cp`:

```bash
# Add your user to docker group
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker
```

### Out of Memory

For large files, increase container memory:

**Ephemeral mode**:
```python
executor = CodeQLDockerExecutor(docker_args=["--memory=8g"])
```

**Running container mode**:
```bash
# Recreate container with more memory
docker rm -f codeql-server
docker run -d --name codeql-server --memory=8g \
  ghcr.io/github/codeql-cli2:latest tail -f /dev/null
```

---

## Performance Comparison

Based on typical JavaScript file analysis:

| Mode | First Run | Subsequent Runs | Best For |
|------|-----------|----------------|----------|
| Ephemeral | ~30-60s | ~30-60s | One-off analyses, CI/CD |
| Running Container | ~35-65s (includes setup) | ~10-20s | Development, bulk scans |

**Recommendation**: Use **running container mode** if you're analyzing multiple files in a session.

---

## CI/CD Integration

For CI/CD pipelines, ephemeral mode is recommended:

```yaml
# GitHub Actions example
- name: Run vulnerability analysis
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    python example_usage.py
```

No `CODEQL_CONTAINER_ID` needed - will automatically use ephemeral containers.
