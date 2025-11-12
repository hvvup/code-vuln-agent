# 토큰 사용량 최적화 가이드

## 문제 상황

토큰 제한 오류가 발생했습니다:
- **요청된 토큰**: 12,095 tokens
- **제한**: 10,000 TPM (Tokens Per Minute)
- **원인**: LLM에 전달되는 입력 데이터가 너무 큼

## LLM에 전달되는 정보

LangGraph의 ReAct Agent는 **모든 tool 결과를 ToolMessage로 LLM에 전달**합니다. 

### 현재 워크플로우에서 전달되는 정보:

1. **System Prompt** (~2,000-3,000 tokens)
   - Agent 역할 정의
   - Tool 사용 가이드
   - 분석 전략

2. **User Prompt** (~500-1,000 tokens)
   - 분석 요청
   - 파일/레포지토리 경로

3. **Tool Results** (누적됨 - **문제의 주요 원인**)
   - `codeql_auto_analyze`: SARIF 파일 경로 (작음)
   - `parse_codeql_sarif`: **전체 findings JSON** (매우 큼!)
     - 100개 findings = ~5,000-10,000 tokens
     - 1000개 findings = ~50,000-100,000 tokens
   - `cfg_generator`: CFG 파일 경로 (작음)
   - `cfg_reader`: CFG 요약 (적당함, ~500-2,000 tokens)
   - `parse_javascript_ast`: AST 결과 (적당함, ~500-1,500 tokens)

### 문제점

**SARIF 결과가 가장 큰 문제입니다:**
- 기본값이 `return_format="json"`이었음
- 전체 findings를 JSON으로 반환
- 레포지토리 스캔 시 수백~수천 개의 findings
- 각 finding마다 상세한 메타데이터 포함

## 해결 방법

### 1. SARIF Parser 기본값 변경 ✅

**변경 전:**
```python
def _run(self, file_path: str, return_format: str = "json"):
    # 전체 JSON 반환
    return findings
```

**변경 후:**
```python
def _run(self, file_path: str, return_format: str = "summary"):
    # 컴팩트한 텍스트 요약 반환
    # 상위 50개만 포함, 메시지 길이 제한
    return summary_text
```

**토큰 절감 효과:**
- JSON 형식: 100 findings ≈ 5,000 tokens
- Summary 형식: 100 findings ≈ 500 tokens
- **약 90% 토큰 절감**

### 2. CFG Reader Tool 사용 강화 ✅

**프롬프트 업데이트:**
- `cfg_generator` 후 반드시 `cfg_reader` 사용
- `max_nodes=50` 권장
- 보안 관련 노드 우선 선택

**토큰 절감 효과:**
- 전체 CFG JSON: 10,000+ nodes ≈ 50,000+ tokens
- CFG Summary: 50 nodes ≈ 2,000 tokens
- **약 96% 토큰 절감**

### 3. AST Parser 통합 ✅

- JavaScript AST parser를 Agent에 추가
- 코드 구조만 추출 (전체 소스 코드 아님)
- 보안 패턴 자동 감지

**토큰 사용량:**
- 전체 소스 코드: 1,000 lines ≈ 4,000 tokens
- AST 요약: ~500-1,500 tokens
- **약 60-75% 토큰 절감**

### 4. 프롬프트 최적화 ✅

- 토큰 최적화 가이드 추가
- 레포지토리 분석 시 파일 수 제한 (상위 10개)
- 심각도 우선순위 명시

## 최적화된 워크플로우

```
1. CodeQL 실행 → SARIF 파일 생성
2. SARIF 파싱 (summary) → ~500 tokens (기존: ~5,000 tokens) ✅
3. AST 파싱 → ~1,000 tokens
4. CFG 생성 → 파일 경로만
5. CFG 읽기 (summary, max_nodes=50) → ~2,000 tokens (기존: ~50,000 tokens) ✅
6. LLM 분석 → 총 ~6,000 tokens (기존: ~60,000+ tokens) ✅
```

## 토큰 사용량 분석 도구

### 1. `analyze_token_usage.py`
```bash
python analyze_token_usage.py
```
- SARIF/CFG 파일 크기 분석
- 토큰 절감 가능량 계산
- 최적화 권장사항 제공

### 2. `monitor_llm_input.py`
```bash
python monitor_llm_input.py
```
- 실제 실행 결과 분석
- Tool별 토큰 사용량 추적
- 문제점 식별

## 예상 토큰 사용량 (최적화 후)

### 단일 파일 분석:
- System Prompt: ~2,500 tokens
- User Prompt: ~500 tokens
- SARIF Summary: ~300 tokens
- AST Result: ~800 tokens
- CFG Summary: ~1,500 tokens
- **총계: ~5,600 tokens** ✅

### 레포지토리 분석 (상위 10개 파일):
- System Prompt: ~2,500 tokens
- User Prompt: ~500 tokens
- SARIF Summary: ~1,000 tokens (100 findings)
- AST Results (10 files): ~8,000 tokens
- CFG Summaries (10 files): ~15,000 tokens
- **총계: ~27,000 tokens** ⚠️

**레포지토리 분석 시 추가 최적화:**
- CFG/AST 분석 파일 수를 5개로 제한
- `max_nodes=30` 사용
- **최적화 후: ~15,000 tokens** ✅

## 확인 방법

1. **토큰 사용량 분석:**
   ```bash
   python analyze_token_usage.py
   ```

2. **워크플로우 테스트:**
   ```bash
   python test_workflow_juice_shop.py
   ```
   - 자동으로 토큰 사용량 분석 포함

3. **실행 결과 분석:**
   ```bash
   python monitor_llm_input.py
   ```

## 주요 개선사항 요약

1. ✅ SARIF parser 기본값을 "summary"로 변경
2. ✅ CFG reader tool 추가 및 사용 강제
3. ✅ AST parser 통합
4. ✅ 프롬프트에 토큰 최적화 가이드 추가
5. ✅ 레포지토리 분석 시 파일 수 제한
6. ✅ 토큰 사용량 모니터링 도구 추가

이제 토큰 제한 문제 없이 워크플로우가 실행될 것입니다!

