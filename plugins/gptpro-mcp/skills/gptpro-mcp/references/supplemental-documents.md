# External evidence

Use repeatable `--evidence-file safe-id=/absolute/private/file` only for task-relevant strict UTF-8 artifacts outside the repository. The source path must be absolute. Preparation securely captures a current-user-owned, single-link, non-group/world-writable regular file, rejects secrets/NUL/unsafe paths, and stores only safe label/size/hash metadata.

Evidence is not uploaded through ChatGPT UI. After exact-package approval, `gptpro_artifact_read` returns bounded slices from the immutable copy. Machine-global standing approval never automatically covers external evidence.
