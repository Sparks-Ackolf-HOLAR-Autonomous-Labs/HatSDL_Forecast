#!/bin/bash
# vLLM server for the agent-latency bench (E3, E3b, E3c). Needs vllm on PATH and the model in the
# Hugging Face cache.
export HF_HUB_OFFLINE=1
echo "start $(date +%s.%N)" > serve.times
vllm serve Qwen/Qwen3.5-9B --port 8720 --host 127.0.0.1 --max-model-len 32768 \
  --gpu-memory-utilization 0.35 --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 --limit-mm-per-prompt '{"image":2,"video":0}' > serve.log 2>&1
echo "exit $? $(date +%s.%N)" >> serve.times
