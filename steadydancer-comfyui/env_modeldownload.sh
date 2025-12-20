#!/bin/bash

# Exit on error
set -e

echo "开始安装和配置 SteadyDancer ComfyUI 环境..."



WORKDIR="/"


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

# ===== SteadyDancer 工作流专用模型 =====
# SteadyDancer 主模型
echo "下载 SteadyDancer 主模型..."
MODEL_PATH="$WORKDIR/ComfyUI/models/diffusion_models/WanVideo/SteadyDancer/Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors"
if [ ! -f "$MODEL_PATH" ]; then
    mkdir -p "$WORKDIR/ComfyUI/models/diffusion_models/WanVideo/SteadyDancer"
    hfd.sh Kijai/WanVideo_comfy_fp8_scaled \
          --include "SteadyDancer/Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_steadydancer
    mv /tmp/hfd_steadydancer/SteadyDancer/Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors "$WORKDIR/ComfyUI/models/diffusion_models/WanVideo/SteadyDancer/"
    rm -rf /tmp/hfd_steadydancer
else
    echo "SteadyDancer 主模型已存在，跳过下载"
fi

# SteadyDancer LoRA模型
echo "下载 SteadyDancer LoRA 模型..."
LORA_PATH="$WORKDIR/ComfyUI/models/loras/WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
if [ ! -f "$LORA_PATH" ]; then
    mkdir -p "$WORKDIR/ComfyUI/models/loras/WanVideo/Lightx2v"
    hfd.sh Kijai/WanVideo_comfy \
          --include "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_lightx2v
    mv /tmp/hfd_lightx2v/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors "$WORKDIR/ComfyUI/models/loras/WanVideo/Lightx2v/"
    rm -rf /tmp/hfd_lightx2v
else
    echo "SteadyDancer LoRA 模型已存在，跳过下载"
fi

# CLIP Vision 模型 (SteadyDancer需要)
echo "下载 CLIP Vision 模型..."
if [ ! -f "$WORKDIR/ComfyUI/models/clip_vision/clip_vision_h.safetensors" ]; then
    hfd.sh Comfy-Org/Wan_2.1_ComfyUI_repackaged \
          --include "split_files/clip_vision/clip_vision_h.safetensors" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_wan21
    mv /tmp/hfd_wan21/split_files/clip_vision/clip_vision_h.safetensors "$WORKDIR/ComfyUI/models/clip_vision/"
    rm -rf /tmp/hfd_wan21
else
    echo "CLIP Vision 模型已存在，跳过下载"
fi

# 姿态检测模型 (YOLO + ViTPose H) - SteadyDancer工作流使用
# OnnxDetectionModelLoader 从 ComfyUI/models/detection 目录加载模型
echo "下载 YOLO 模型..."
if [ ! -f "$WORKDIR/ComfyUI/models/detection/yolov10m.onnx" ]; then
    hfd.sh Wan-AI/Wan2.2-Animate-14B \
          --include "process_checkpoint/det/yolov10m.onnx" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_yolo
    mv /tmp/hfd_yolo/process_checkpoint/det/yolov10m.onnx "$WORKDIR/ComfyUI/models/detection/"
    rm -rf /tmp/hfd_yolo
else
    echo "YOLO 模型已存在，跳过下载"
fi

echo "下载 ViTPose H 模型..."
if [ ! -f "$WORKDIR/ComfyUI/models/detection/vitpose_h_wholebody_model.onnx" ]; then
    hfd.sh JunkyByte/easy_ViTPose \
          --include "onnx/wholebody/vitpose-h-wholebody.onnx" \
          --tool aria2c \
          -x 8 -j 8 \
          --local-dir /tmp/hfd_vitpose_h
    mv /tmp/hfd_vitpose_h/onnx/wholebody/vitpose-h-wholebody.onnx "$WORKDIR/ComfyUI/models/detection/vitpose_h_wholebody_model.onnx"
    rm -rf /tmp/hfd_vitpose_h
else
    echo "ViTPose H 模型已存在，跳过下载"
fi

# 创建 ONNX 模型符号链接（某些节点可能从 onnx 目录读取）
echo "创建 ONNX 模型符号链接..."
if [ -d "$WORKDIR/ComfyUI/models/detection" ]; then
    for file in "$WORKDIR/ComfyUI/models/detection"/*.onnx; do
        if [ -f "$file" ]; then
            ln -sf "$file" "$WORKDIR/ComfyUI/models/onnx/$(basename "$file")" 2>/dev/null || true
        fi
    done
    echo "ONNX 模型符号链接创建完成"
fi

# Copy files if needed
echo "复制配置文件..."
if [ -f "$SCRIPT_DIR/extra_model_paths.yaml" ]; then
    cp "$SCRIPT_DIR/extra_model_paths.yaml" "$WORKDIR/ComfyUI/extra_model_paths.yaml"
fi

if [ -f "$SCRIPT_DIR/entrypoint.sh" ]; then
    chmod +x "$SCRIPT_DIR/entrypoint.sh"
fi

echo "安装 sageattention..."
pip install sageattention

# 验证模型文件
echo "验证模型文件..."
echo "=== SteadyDancer 主模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/diffusion_models/WanVideo/SteadyDancer/Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors" 2>/dev/null || echo "警告: SteadyDancer 主模型未找到"

echo "=== T5 文本编码器 ==="
ls -lh "$WORKDIR/ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors" 2>/dev/null || echo "警告: T5 文本编码器未找到"

echo "=== VAE 模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors" 2>/dev/null || echo "警告: VAE 模型未找到"

echo "=== SteadyDancer LoRA 模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/loras/WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors" 2>/dev/null || echo "警告: SteadyDancer LoRA 模型未找到"

echo "=== CLIP Vision 模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/clip_vision/clip_vision_h.safetensors" 2>/dev/null || echo "警告: CLIP Vision 模型未找到"

echo "=== 姿态检测模型 ==="
ls -lh "$WORKDIR/ComfyUI/models/detection/yolov10m.onnx" 2>/dev/null || echo "警告: YOLO 模型未找到"
ls -lh "$WORKDIR/ComfyUI/models/detection/vitpose_h_wholebody_model.onnx" 2>/dev/null || echo "警告: ViTPose H 模型未找到"

echo "安装和配置完成！"

