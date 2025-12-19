#!/bin/bash

# Exit on error
set -e

echo "开始安装和配置..."

# 先固定 NumPy 版本（避免 onnxruntime-gpu 兼容性问题）
# onnxruntime-gpu 需要 NumPy < 2.0
echo "安装 NumPy < 2.0..."
pip install "numpy<2.0"

echo "安装 huggingface_hub..."
pip install -U "huggingface_hub[hf_transfer]"

echo "安装 runpod 和 websocket-client..."
pip install runpod websocket-client

# Install dependencies for hfd.sh and handler.py
echo "安装系统依赖..."
apt-get update
apt-get install -y curl aria2 wget
rm -rf /var/lib/apt/lists/*

# Copy and setup hfd.sh
echo "设置 hfd.sh..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/hfd.sh" ]; then
    cp "$SCRIPT_DIR/hfd.sh" /usr/local/bin/hfd.sh
    chmod +x /usr/local/bin/hfd.sh
else
    echo "警告: hfd.sh 文件未找到"
fi

WORKDIR="/"

echo "克隆 ComfyUI..."
cd "$WORKDIR"
if [ ! -d "ComfyUI" ]; then
    git clone https://github.com/comfyanonymous/ComfyUI.git
    cd ComfyUI
    pip install -r requirements.txt
else
    echo "ComfyUI 已存在，跳过克隆"
    cd ComfyUI
fi

echo "安装 ComfyUI-Manager..."
cd custom_nodes
if [ ! -d "ComfyUI-Manager" ]; then
    git clone https://github.com/Comfy-Org/ComfyUI-Manager.git
    cd ComfyUI-Manager
    pip install -r requirements.txt
    cd ..
else
    echo "ComfyUI-Manager 已存在，跳过克隆"
fi

echo "安装 ComfyUI-GGUF..."
if [ ! -d "ComfyUI-GGUF" ]; then
    git clone https://github.com/city96/ComfyUI-GGUF.git
    cd ComfyUI-GGUF
    pip install -r requirements.txt
    cd ..
else
    echo "ComfyUI-GGUF 已存在，跳过克隆"
fi

echo "安装 ComfyUI-KJNodes..."
if [ ! -d "ComfyUI-KJNodes" ]; then
    git clone https://github.com/kijai/ComfyUI-KJNodes.git
    cd ComfyUI-KJNodes
    pip install -r requirements.txt
    cd ..
else
    echo "ComfyUI-KJNodes 已存在，跳过克隆"
fi

echo "安装 ComfyUI-VideoHelperSuite..."
if [ ! -d "ComfyUI-VideoHelperSuite" ]; then
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
    cd ComfyUI-VideoHelperSuite
    pip install -r requirements.txt
    cd ..
else
    echo "ComfyUI-VideoHelperSuite 已存在，跳过克隆"
fi

echo "安装 ComfyUI-Custom-Scripts..."
if [ ! -d "ComfyUI-Custom-Scripts" ]; then
    git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts
else
    echo "ComfyUI-Custom-Scripts 已存在，跳过克隆"
fi

echo "安装 ComfyUI-Easy-Use..."
if [ ! -d "ComfyUI-Easy-Use" ]; then
    git clone https://github.com/yolain/ComfyUI-Easy-Use.git
    cd ComfyUI-Easy-Use
    pip install -r requirements.txt
    cd ..
else
    echo "ComfyUI-Easy-Use 已存在，跳过克隆"
fi

echo "安装 ComfyUI-Logic..."
if [ ! -d "ComfyUI-Logic" ]; then
    git clone https://github.com/theUpsider/ComfyUI-Logic.git
    cd ComfyUI-Logic
    if [ -f requirements.txt ]; then
        pip install -r requirements.txt
    fi
    cd ..
else
    echo "ComfyUI-Logic 已存在，跳过克隆"
fi

echo "安装 ComfyUI_essentials..."
if [ ! -d "ComfyUI_essentials" ]; then
    git clone https://github.com/cubiq/ComfyUI_essentials.git
    cd ComfyUI_essentials
    pip install -r requirements.txt
    cd ..
else
    echo "ComfyUI_essentials 已存在，跳过克隆"
fi

echo "安装 ComfyUI_CreaPrompt..."
if [ ! -d "ComfyUI_CreaPrompt" ]; then
    git clone https://github.com/tritant/ComfyUI_CreaPrompt.git
else
    echo "ComfyUI_CreaPrompt 已存在，跳过克隆"
fi

echo "安装 masquerade-nodes-comfyui..."
if [ ! -d "masquerade-nodes-comfyui" ]; then
    git clone https://github.com/BadCafeCode/masquerade-nodes-comfyui.git
else
    echo "masquerade-nodes-comfyui 已存在，跳过克隆"
fi

echo "安装 ComfyUI-SelectStringFromListWithIndex..."
if [ ! -d "ComfyUI-SelectStringFromListWithIndex" ]; then
    git clone https://github.com/mr-pepe69/ComfyUI-SelectStringFromListWithIndex.git
else
    echo "ComfyUI-SelectStringFromListWithIndex 已存在，跳过克隆"
fi

echo "安装 ComfyUI-wanBlockswap..."
if [ ! -d "ComfyUI-wanBlockswap" ]; then
    git clone https://github.com/orssorbit/ComfyUI-wanBlockswap.git
else
    echo "ComfyUI-wanBlockswap 已存在，跳过克隆"
fi

echo "安装 ComfyUI-WanVideoWrapper..."
if [ ! -d "ComfyUI-WanVideoWrapper" ]; then
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git
    cd ComfyUI-WanVideoWrapper
    pip install -r requirements.txt
    cd ..
else
    echo "ComfyUI-WanVideoWrapper 已存在，跳过克隆"
fi

echo "安装 ComfyUI-WanAnimatePreprocess..."
if [ ! -d "ComfyUI-WanAnimatePreprocess" ]; then
    git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess.git
    cd ComfyUI-WanAnimatePreprocess
    if [ -f requirements.txt ]; then
        pip install -r requirements.txt
    fi
    cd ..
else
    echo "ComfyUI-WanAnimatePreprocess 已存在，跳过克隆"
fi

echo "安装 IntelligentVRAMNode 和其他节点..."
if [ ! -d "IntelligentVRAMNode" ]; then
    git clone https://github.com/eddyhhlure1Eddy/IntelligentVRAMNode.git
else
    echo "IntelligentVRAMNode 已存在，跳过克隆"
fi

if [ ! -d "auto_wan2.2animate_freamtowindow_server" ]; then
    git clone https://github.com/eddyhhlure1Eddy/auto_wan2.2animate_freamtowindow_server.git
else
    echo "auto_wan2.2animate_freamtowindow_server 已存在，跳过克隆"
fi

if [ ! -d "ComfyUI-AdaptiveWindowSize" ]; then
    git clone https://github.com/eddyhhlure1Eddy/ComfyUI-AdaptiveWindowSize.git
    cd ComfyUI-AdaptiveWindowSize/ComfyUI-AdaptiveWindowSize
    mv * ../
    cd ../..
else
    echo "ComfyUI-AdaptiveWindowSize 已存在，跳过克隆"
fi

# Install ONNX Runtime GPU for pose detection models (ViTPose, YOLO)
# Required for running ONNX models with GPU acceleration
# Note: NumPy < 2.0 is already installed above, ensure it's not upgraded
echo "安装 ONNX Runtime GPU..."
pip install onnx==1.16.0 onnxruntime-gpu==1.18.0
pip install --force-reinstall --no-deps "numpy<2.0" || true

# Create model directories
echo "创建模型目录..."
mkdir -p "$WORKDIR/ComfyUI/models/diffusion_models"
mkdir -p "$WORKDIR/ComfyUI/models/loras"
mkdir -p "$WORKDIR/ComfyUI/models/clip_vision"
mkdir -p "$WORKDIR/ComfyUI/models/text_encoders"
mkdir -p "$WORKDIR/ComfyUI/models/vae"
mkdir -p "$WORKDIR/ComfyUI/models/onnx"
mkdir -p "$WORKDIR/ComfyUI/models/detection"

# ===== 所有工作流共享的基础模型 =====
# T5 文本编码器和 VAE (所有工作流都需要)
echo "下载 T5 文本编码器和 VAE..."
if [ ! -f "$WORKDIR/ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors" ] || [ ! -f "$WORKDIR/ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors" ]; then
    hfd.sh Kijai/WanVideo_comfy \
          --include "umt5-xxl-enc-bf16.safetensors" \
          --include "Wan2_1_VAE_bf16.safetensors" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_wanvideo
    mv /tmp/hfd_wanvideo/umt5-xxl-enc-bf16.safetensors "$WORKDIR/ComfyUI/models/text_encoders/"
    mv /tmp/hfd_wanvideo/Wan2_1_VAE_bf16.safetensors "$WORKDIR/ComfyUI/models/vae/"
    rm -rf /tmp/hfd_wanvideo
else
    echo "T5 文本编码器和 VAE 已存在，跳过下载"
fi

# ===== Wan21_OneToAllAnimation 工作流专用模型 =====
# Wan21-OneToAllAnimation 主模型
# 注意：模型在 Kijai/WanVideo_comfy_fp8_scaled 仓库中，路径为 OneToAllAnimation/
echo "下载 Wan21-OneToAllAnimation 主模型..."
MODEL_PATH="$WORKDIR/ComfyUI/models/diffusion_models/WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors"
if [ ! -f "$MODEL_PATH" ]; then
    mkdir -p "$WORKDIR/ComfyUI/models/diffusion_models/WanVideo/OneToAll"
    hfd.sh Kijai/WanVideo_comfy_fp8_scaled \
          --include "OneToAllAnimation/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_wan21_otoa
    mv /tmp/hfd_wan21_otoa/OneToAllAnimation/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors "$WORKDIR/ComfyUI/models/diffusion_models/WanVideo/OneToAll/"
    rm -rf /tmp/hfd_wan21_otoa
else
    echo "Wan21-OneToAllAnimation 主模型已存在，跳过下载"
fi

# 姿态检测模型 (YOLO + ViTPose) - 用于参考视频的姿态提取
echo "下载 YOLO 模型..."
if [ ! -f "$WORKDIR/ComfyUI/models/onnx/yolov10m.onnx" ]; then
    hfd.sh Wan-AI/Wan2.2-Animate-14B \
          --include "process_checkpoint/det/yolov10m.onnx" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_yolo
    mv /tmp/hfd_yolo/process_checkpoint/det/yolov10m.onnx "$WORKDIR/ComfyUI/models/onnx/"
    rm -rf /tmp/hfd_yolo
else
    echo "YOLO 模型已存在，跳过下载"
fi

echo "下载 ViTPose 模型..."
if [ ! -f "$WORKDIR/ComfyUI/models/onnx/vitpose-l-wholebody.onnx" ]; then
    hfd.sh JunkyByte/easy_ViTPose \
          --include "onnx/wholebody/vitpose-l-wholebody.onnx" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_vitpose
    mv /tmp/hfd_vitpose/onnx/wholebody/vitpose-l-wholebody.onnx "$WORKDIR/ComfyUI/models/onnx/"
    rm -rf /tmp/hfd_vitpose
else
    echo "ViTPose 模型已存在，跳过下载"
fi

# 创建 detection 目录的符号链接（某些节点可能从 detection 目录读取 ONNX 模型）
echo "创建 ONNX 模型符号链接..."
if [ -d "$WORKDIR/ComfyUI/models/onnx" ]; then
    for file in "$WORKDIR/ComfyUI/models/onnx"/*.onnx "$WORKDIR/ComfyUI/models/onnx"/*.bin; do
        if [ -f "$file" ]; then
            ln -sf "$file" "$WORKDIR/ComfyUI/models/detection/$(basename "$file")" 2>/dev/null || true
        fi
    done
    echo "ONNX 模型符号链接创建完成"
fi

# ===== LoRA 模型 =====
# Lightx2v LoRA 模型（用于 Wan21_OneToAllAnimation 工作流）
echo "下载 Lightx2v LoRA 模型..."
LORA_PATH="$WORKDIR/ComfyUI/models/loras/WanVideo/Lightx2v/lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16.safetensors"
if [ ! -f "$LORA_PATH" ]; then
    mkdir -p "$WORKDIR/ComfyUI/models/loras/WanVideo/Lightx2v"
    hfd.sh Kijai/WanVideo_comfy \
          --include "Lightx2v/lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16.safetensors" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_lora
    mv /tmp/hfd_lora/Lightx2v/lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16.safetensors "$WORKDIR/ComfyUI/models/loras/WanVideo/Lightx2v/"
    rm -rf /tmp/hfd_lora
else
    echo "Lightx2v LoRA 模型已存在，跳过下载"
fi

# ===== 注意：以下模型已移除（仅用于 Wan21_OneToAllAnimation 工作流）=====
# 如果将来需要支持 MEGA 或标准 Wan22 工作流，可以取消注释以下部分：
#
# # MEGA/AIO 工作流专用模型
# hfd.sh Phr00t/WAN2.2-14B-Rapid-AllInOne ...
# hfd.sh Comfy-Org/Wan_2.1_ComfyUI_repackaged ...
#
# # 标准 Wan22 工作流可选模型
# hfd.sh lightx2v/Wan2.2-Lightning ...

# Copy files if needed
echo "复制配置文件..."
if [ -f "$SCRIPT_DIR/extra_model_paths.yaml" ]; then
    cp "$SCRIPT_DIR/extra_model_paths.yaml" "$WORKDIR/ComfyUI/extra_model_paths.yaml"
fi

if [ -f "$SCRIPT_DIR/entrypoint.sh" ]; then
    chmod +x "$SCRIPT_DIR/entrypoint.sh"
fi

pip install sageattention

# 验证模型文件
echo "验证模型文件..."
echo "=== 主模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/diffusion_models/WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors" 2>/dev/null || echo "警告: 主模型未找到"

echo "=== T5 文本编码器 ==="
ls -lh "$WORKDIR/ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors" 2>/dev/null || echo "警告: T5 文本编码器未找到"

echo "=== VAE 模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors" 2>/dev/null || echo "警告: VAE 模型未找到"

echo "=== LoRA 模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/loras/WanVideo/Lightx2v/lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16.safetensors" 2>/dev/null || echo "警告: LoRA 模型未找到"

echo "=== ONNX 模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/onnx/yolov10m.onnx" 2>/dev/null || echo "警告: YOLO 模型未找到"
ls -lh "$WORKDIR/ComfyUI/models/onnx/vitpose-l-wholebody.onnx" 2>/dev/null || echo "警告: ViTPose 模型未找到"

echo "安装和配置完成！"

