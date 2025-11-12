# CFG 파싱 에러 해결 가이드

## 에러 내용

```
esprima.error_handler.Error: Line 9: Unexpected identifier
```

## 에러 원인

1. **JavaScript 파싱 실패**
   - CFG generator가 JavaScript 파일을 파싱할 때 esprima 파서가 문법 오류를 감지
   - 일부 JavaScript 파일이 esprima가 파싱할 수 없는 구문을 포함
   - 예: 최신 JavaScript 문법, TypeScript 구문, 빌드 도구에 의해 변환된 코드 등

2. **예외 처리 부재**
   - 파싱 실패 시 예외 처리가 없어 전체 프로세스가 중단됨
   - 하나의 파일 파싱 실패로 인해 다른 파일들도 처리되지 않음

3. **레포지토리 스캔 시 문제**
   - 레포지토리에는 다양한 형태의 JavaScript 파일이 포함될 수 있음
   - 모든 파일이 표준 JavaScript 문법을 따르지 않을 수 있음

## 수정 사항

### 1. CFG Generator에 에러 핸들링 추가 ✅

**변경 전:**
```python
file_cfgs = [self._process_file(file_path) for file_path in generation_input.files]
# 하나라도 실패하면 전체 실패
```

**변경 후:**
```python
# Process files with error handling
file_cfgs = []
for file_path in generation_input.files:
    try:
        file_cfg = self._process_file(file_path)
        file_cfgs.append(file_cfg)
    except Exception as e:
        # Log error but continue with other files
        print(f"⚠️  Warning: Failed to process {file_path}: {e}")
        print(f"   Skipping this file and continuing with others...")
        # Create an empty FileCFG to maintain structure
        empty_cfg = FileCFG(file_path=str(file_path), functions=[])
        file_cfgs.append(empty_cfg)
```

**효과:**
- 파싱 실패한 파일은 건너뛰고 다른 파일 계속 처리
- 전체 프로세스가 중단되지 않음
- 실패한 파일 정보는 경고로 출력

### 2. Parser에 더 나은 에러 메시지 추가 ✅

**변경 전:**
```python
program = parser_fn(source, **parse_kwargs)
# 에러 메시지가 불명확함
```

**변경 후:**
```python
try:
    program = parser_fn(source, **parse_kwargs)
    # ...
except Exception as e:
    # Provide more context about the parsing error
    error_msg = f"Failed to parse JavaScript: {str(e)}"
    if hasattr(e, 'description'):
        error_msg += f" - {e.description}"
    if hasattr(e, 'lineNumber'):
        error_msg += f" at line {e.lineNumber}"
    raise ValueError(error_msg) from e
```

**효과:**
- 더 명확한 에러 메시지
- 에러 발생 위치(라인 번호) 정보 제공

### 3. CFG Generator Tool에 에러 핸들링 추가 ✅

**변경 후:**
```python
try:
    output_paths = self._generator.generate(payload)
    return json.dumps({key: str(path) for key, path in output_paths.items()}, indent=2)
except Exception as e:
    # Return error information but don't crash
    error_info = {
        "error": f"CFG generation failed: {str(e)}",
        "files_processed": len(files),
        "note": "Some files may have been skipped due to parsing errors.",
    }
    # Partial results if available
    if cfg_file.exists():
        error_info["partial_results"] = str(cfg_file)
    return json.dumps(error_info, indent=2)
```

**효과:**
- Tool 레벨에서도 에러 처리
- 부분 결과라도 반환 가능
- Agent가 에러 정보를 받아서 처리 가능

## 동작 방식 (수정 후)

1. **파일별 독립 처리**
   - 각 파일을 개별적으로 처리
   - 하나 실패해도 다른 파일 계속 처리

2. **경고 출력**
   - 실패한 파일에 대해 경고 메시지 출력
   - 어떤 파일이 왜 실패했는지 정보 제공

3. **부분 결과 반환**
   - 일부 파일만 성공해도 결과 반환
   - 빈 FileCFG로 구조 유지

4. **Agent가 에러 처리 가능**
   - Tool이 에러 정보를 반환
   - Agent가 이를 인지하고 다른 방법 시도 가능

## 예상 동작

### 성공 케이스:
```
Processing file1.js... ✅
Processing file2.js... ✅
Processing file3.js... ⚠️  Warning: Failed to process file3.js: Line 9: Unexpected identifier
   Skipping this file and continuing with others...
Processing file4.js... ✅
CFG generation complete for 3 out of 4 files
```

### 결과:
- 성공한 파일들의 CFG는 정상 생성
- 실패한 파일은 빈 FileCFG로 포함
- 전체 프로세스는 계속 진행

## 추가 개선 사항 (선택사항)

향후 개선할 수 있는 사항:

1. **파일 필터링**
   - 파싱 가능한 파일만 선택
   - TypeScript, JSX 등은 사전 필터링

2. **대체 파서 사용**
   - esprima 실패 시 다른 파서 시도
   - Babel, Acorn 등

3. **파싱 모드 선택**
   - `tolerant` 모드 강화
   - 부분 파싱 지원

현재 수정으로도 레포지토리 스캔 시 일부 파일 파싱 실패가 있어도 전체 프로세스가 계속 진행됩니다.

