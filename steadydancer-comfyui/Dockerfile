# Use specific version of nvidia cuda image
# FROM wlsdml1114/my-comfy-models:v1 as model_provider
FROM wlsdml1114/multitalk-base:1.7 as runtime

RUN pip install -U "huggingface_hub[hf_transfer]"
RUN pip install runpod websocket-client

# Install dependencies for hfd.sh
RUN apt-get update && apt-get install -y curl aria2 && rm -rf /var/lib/apt/lists/*

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

# ===== SteadyDancer 工作流专用模型 =====
# SteadyDancer 主模型
RUN mkdir -p /ComfyUI/models/diffusion_models/WanVideo/SteadyDancer && \
    hfd.sh Kijai/WanVideo_comfy_fp8_scaled \
      --include "SteadyDancer/Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_steadydancer && \
    mv /tmp/hfd_steadydancer/SteadyDancer/Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors /ComfyUI/models/diffusion_models/WanVideo/SteadyDancer/ && \
    rm -rf /tmp/hfd_steadydancer

# SteadyDancer LoRA模型
RUN mkdir -p /ComfyUI/models/loras/WanVideo/Lightx2v && \
    hfd.sh Kijai/WanVideo_comfy \
      --include "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_lightx2v && \
    mv /tmp/hfd_lightx2v/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors /ComfyUI/models/loras/WanVideo/Lightx2v/ && \
    rm -rf /tmp/hfd_lightx2v

# CLIP Vision 模型 (SteadyDancer需要)
RUN hfd.sh Comfy-Org/Wan_2.1_ComfyUI_repackaged \
      --include "split_files/clip_vision/clip_vision_h.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_wan21 && \
    mv /tmp/hfd_wan21/split_files/clip_vision/clip_vision_h.safetensors /ComfyUI/models/clip_vision/ && \
    rm -rf /tmp/hfd_wan21

# 姿态检测模型 (YOLO + ViTPose H) - SteadyDancer工作流使用
# OnnxDetectionModelLoader 从 ComfyUI/models/detection 目录加载模型
RUN hfd.sh Wan-AI/Wan2.2-Animate-14B \
      --include "process_checkpoint/det/yolov10m.onnx" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_yolo && \
    mv /tmp/hfd_yolo/process_checkpoint/det/yolov10m.onnx /ComfyUI/models/detection/ && \
    rm -rf /tmp/hfd_yolo

RUN hfd.sh JunkyByte/easy_ViTPose \
      --include "onnx/wholebody/vitpose-h-wholebody.onnx" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_vitpose_h && \
    mv /tmp/hfd_vitpose_h/onnx/wholebody/vitpose-h-wholebody.onnx /ComfyUI/models/detection/vitpose_h_wholebody_model.onnx && \
    rm -rf /tmp/hfd_vitpose_h


COPY . .
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
