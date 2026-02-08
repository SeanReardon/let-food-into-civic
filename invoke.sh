opencode run --model inference-server/zai-org/GLM-4.7-FP8 --agent build --format json --log-level ERROR "$(sed '1d;/^=== OPENCODE/,$d' ./attempt.txt)"
