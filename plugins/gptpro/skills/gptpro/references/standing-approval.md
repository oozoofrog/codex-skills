# Machine-global standing approval

`gptpro-standing-approval-v2`는 반복되는 package별 질문을 줄이기 위한 owner-only 권한입니다. 저장소 하나에 묶이지 않고 `all-local-git` 범위에서 사용할 수 있지만, 다음 경계를 모두 만족해야 합니다.

- transport `mcp-research`
- delivery `desktop-ui`
- 같은 Tunnel profile hash, ChatGPT app, workspace, model
- 허용 mode와 path pattern
- dirty tracked 허용 여부
- task/file/total byte 예산과 MCP call/return 예산
- 최대 30일 expiry

선택된 untracked 파일은 `allow_dirty`와 관계없이 절대 자동 승인되지 않습니다. 외부 문서, supplement, secret finding, 다른 app/workspace/model, 예산 초과도 exact-package 승인으로 돌아갑니다.

새 standing approval은 이미 사용자가 수동 승인한 정확한 Schema 4 package를 source evidence로 요구합니다. Preview와 저장은 별개입니다.

```bash
python3 <skill-dir>/scripts/gptpro.py standing-approval-create \
  --handoff-dir <manually-approved-package> \
  --name personal-default \
  --approved-by user \
  --dry-run

python3 <skill-dir>/scripts/gptpro.py standing-approval-create \
  --handoff-dir <manually-approved-package> \
  --name personal-default \
  --approved-by user \
  --confirm-standing-approval
```

목록 조회와 revoke는 새 package를 만들거나 prompt를 보내지 않습니다. Revoke는 미래 match만 막으며 이미 수행된 disclosure evidence를 지우지 않습니다.
