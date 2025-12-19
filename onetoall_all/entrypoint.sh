#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
# Note: We don't use set -e here because we need to handle background processes
# set -e

# Start ComfyUI in the background
echo "Starting ComfyUI in the background..."
python /ComfyUI/main.py --listen --use-sage-attention &
COMFYUI_PID=$!

# Wait for ComfyUI to be ready
echo "Waiting for ComfyUI to be ready..."
max_wait=120  # 최대 2분 대기
wait_count=0
while [ $wait_count -lt $max_wait ]; do
    if curl -s http://127.0.0.1:8188/ > /dev/null 2>&1; then
        echo "ComfyUI is ready!"
        break
    fi
    echo "Waiting for ComfyUI... ($wait_count/$max_wait)"
    sleep 2
    wait_count=$((wait_count + 2))
done

if [ $wait_count -ge $max_wait ]; then
    echo "Error: ComfyUI failed to start within $max_wait seconds"
    # Check if ComfyUI process is still running
    if ! kill -0 $COMFYUI_PID 2>/dev/null; then
        echo "ComfyUI process has died. Checking logs..."
        wait $COMFYUI_PID 2>/dev/null || true
    fi
    exit 1
fi

# Verify ComfyUI is still running
if ! kill -0 $COMFYUI_PID 2>/dev/null; then
    echo "Error: ComfyUI process died after starting"
    exit 1
fi

# Start the handler in the foreground
# 이 스크립트가 컨테이너의 메인 프로세스가 됩니다.
echo "Starting the handler..."
# 确保工作目录正确（handler.py 和 workflow 文件都在根目录）
cd /
exec python /handler.py