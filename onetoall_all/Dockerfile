# Use specific version of nvidia cuda image
# FROM wlsdml1114/my-comfy-models:v1 as model_provider
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404 as runtime

# 先固定 NumPy 版本（避免 onnxruntime-gpu 兼容性问题）
# onnxruntime-gpu 需要 NumPy < 2.0
RUN pip install "numpy<2.0"

RUN pip install -U "huggingface_hub[hf_transfer]"
RUN pip install runpod websocket-client

# Install dependencies for hfd.sh and handler.py
RUN apt-get update && apt-get install -y curl aria2 wget && rm -rf /var/lib/apt/lists/*

# Copy and setup hfd.sh
COPY hfd.sh /usr/local/bin/hfd.sh
RUN chmod +x /usr/local/bin/hfd.sh

WORKDIR /

RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd /ComfyUI && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Comfy-Org/ComfyUI-Manager.git && \
    cd ComfyUI-Manager && \
    pip install -r requirements.txt 
    
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/city96/ComfyUI-GGUF && \
    cd ComfyUI-GGUF && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes && \
    cd ComfyUI-KJNodes && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite && \
    cd ComfyUI-VideoHelperSuite && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/yolain/ComfyUI-Easy-Use && \
    cd ComfyUI-Easy-Use && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/theUpsider/ComfyUI-Logic && \
    cd ComfyUI-Logic && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/cubiq/ComfyUI_essentials && \
    cd ComfyUI_essentials && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/tritant/ComfyUI_CreaPrompt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/BadCafeCode/masquerade-nodes-comfyui

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/mr-pepe69/ComfyUI-SelectStringFromListWithIndex
    
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/orssorbit/ComfyUI-wanBlockswap

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper && \
    cd ComfyUI-WanVideoWrapper && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess && \
    cd ComfyUI-WanAnimatePreprocess && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
    
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/eddyhhlure1Eddy/IntelligentVRAMNode && \
    git clone https://github.com/eddyhhlure1Eddy/auto_wan2.2animate_freamtowindow_server && \
    git clone https://github.com/eddyhhlure1Eddy/ComfyUI-AdaptiveWindowSize && \
    cd ComfyUI-AdaptiveWindowSize/ComfyUI-AdaptiveWindowSize && \
    mv * ../

# Install ONNX Runtime GPU for pose detection models (ViTPose, YOLO)
# Required for running ONNX models with GPU acceleration
# Note: NumPy < 2.0 is already installed above, ensure it's not upgraded
RUN pip install onnx==1.16.0 onnxruntime-gpu==1.18.0 && \
    pip install --force-reinstall --no-deps "numpy<2.0" || true

# Create model directories
RUN mkdir -p /ComfyUI/models/diffusion_models /ComfyUI/models/loras /ComfyUI/models/clip_vision /ComfyUI/models/text_encoders /ComfyUI/models/vae /ComfyUI/models/onnx /ComfyUI/models/detection

# ===== 所有工作流共享的基础模型 =====
# T5 文本编码器和 VAE (所有工作流都需要)
RUN hfd.sh Kijai/WanVideo_comfy \
      --include "umt5-xxl-enc-bf16.safetensors" \
      --include "Wan2_1_VAE_bf16.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_wanvideo && \
    mv /tmp/hfd_wanvideo/umt5-xxl-enc-bf16.safetensors /ComfyUI/models/text_encoders/ && \
    mv /tmp/hfd_wanvideo/Wan2_1_VAE_bf16.safetensors /ComfyUI/models/vae/ && \
    rm -rf /tmp/hfd_wanvideo

# ===== Wan21_OneToAllAnimation 工作流专用模型 =====
# Wan21-OneToAllAnimation 主模型
# 注意：模型在 Kijai/WanVideo_comfy_fp8_scaled 仓库中，路径为 OneToAllAnimation/
RUN mkdir -p /ComfyUI/models/diffusion_models/WanVideo/OneToAll && \
    hfd.sh Kijai/WanVideo_comfy_fp8_scaled \
      --include "OneToAllAnimation/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_wan21_otoa && \
    mv /tmp/hfd_wan21_otoa/OneToAllAnimation/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors /ComfyUI/models/diffusion_models/WanVideo/OneToAll/ && \
    rm -rf /tmp/hfd_wan21_otoa

# 姿态检测模型 (YOLO + ViTPose) - 用于参考视频的姿态提取
RUN hfd.sh Wan-AI/Wan2.2-Animate-14B \
      --include "process_checkpoint/det/yolov10m.onnx" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_yolo && \
    mv /tmp/hfd_yolo/process_checkpoint/det/yolov10m.onnx /ComfyUI/models/onnx/ && \
    rm -rf /tmp/hfd_yolo

RUN hfd.sh JunkyByte/easy_ViTPose \
      --include "onnx/wholebody/vitpose-l-wholebody.onnx" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_vitpose && \
    mv /tmp/hfd_vitpose/onnx/wholebody/vitpose-l-wholebody.onnx /ComfyUI/models/onnx/ && \
    rm -rf /tmp/hfd_vitpose

# 创建 detection 目录的符号链接（某些节点可能从 detection 目录读取 ONNX 模型）
RUN if [ -d /ComfyUI/models/onnx ]; then \
        for file in /ComfyUI/models/onnx/*.onnx /ComfyUI/models/onnx/*.bin; do \
            if [ -f "$file" ]; then \
                ln -sf "$file" "/ComfyUI/models/detection/$(basename "$file")" 2>/dev/null || true; \
            fi; \
        done; \
    fi

# ===== LoRA 模型 =====
# Lightx2v LoRA 模型（用于 Wan21_OneToAllAnimation 工作流）
RUN mkdir -p /ComfyUI/models/loras/WanVideo/Lightx2v && \
    hfd.sh Kijai/WanVideo_comfy \
      --include "Lightx2v/lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16_.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_lora && \
    mv /tmp/hfd_lora/Lightx2v/lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16_.safetensors /ComfyUI/models/loras/WanVideo/Lightx2v/ && \
    rm -rf /tmp/hfd_lora

# ===== 注意：以下模型已移除（仅用于 Wan21_OneToAllAnimation 工作流）=====
# 如果将来需要支持 MEGA 或标准 Wan22 工作流，可以取消注释以下部分：
#
# # MEGA/AIO 工作流专用模型
# RUN hfd.sh Phr00t/WAN2.2-14B-Rapid-AllInOne ...
# RUN hfd.sh Comfy-Org/Wan_2.1_ComfyUI_repackaged ...
#
# # 标准 Wan22 工作流可选模型
# RUN hfd.sh lightx2v/Wan2.2-Lightning ...

# Install sageattention
RUN pip install sageattention

COPY . .
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
