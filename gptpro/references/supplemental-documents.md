# External evidence files

Repository 밖의 특정 text artifact가 꼭 필요하면 Schema 4 `--evidence-file safe-id=/absolute/path`를 사용합니다. ChatGPT 앱에 파일을 직접 upload하지 않습니다. Preparation 시 strict UTF-8 bytes를 owner-only immutable package evidence로 복사하고 secret scan과 count/per-file/total budgets를 적용합니다.

Source는 current-user-owned, single-link, non-group/world-writable regular file이어야 합니다. Symlink, hard link, FIFO, socket, device, NUL, unsafe mode와 secret-like content는 fail-closed합니다. Raw source path는 outbound prompt나 manifest에 넣지 않습니다.

External evidence는 standing approval에 자동 포함되지 않습니다. Exact-package disclosure를 새로 검토해야 합니다. ChatGPT는 승인 후 read-only evidence tool로 복사본을 읽습니다.
