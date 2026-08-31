# Legacy receipt handling

과거 `browser`, `github`, `paste`, `text-file`, Schema 2/3 package의 완료 receipt와 hash chain은 감사 목적으로 offline verification할 수 있습니다. 이 호환성은 과거 사실을 읽기 위한 것입니다.

다음에는 사용할 수 없습니다.

- 새 prompt 전송
- Browser/Chrome/Web fallback
- 새 standing approval source
- Desktop UI submission evidence 대체
- Tunnel activation 또는 repository disclosure 재개

Legacy runtime이 terminal인지 불명확한 설치 전환은 `gptpro-mcp`의 `transition-evidence`, `mcp-status|stop|recover` 계약을 사용합니다. `ownership_transferred=true`는 `exact_child_stop_proven=true`를 의미하지 않습니다.
