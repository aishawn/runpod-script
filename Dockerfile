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
    git clone https://github.com/orssorbit/ComfyUI-wanBlockswap

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper && \
    cd ComfyUI-WanVideoWrapper && \
    pip install -r requirements.txt

    
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/eddyhhlure1Eddy/IntelligentVRAMNode && \
    git clone https://github.com/eddyhhlure1Eddy/auto_wan2.2animate_freamtowindow_server && \
    git clone https://github.com/eddyhhlure1Eddy/ComfyUI-AdaptiveWindowSize && \
    cd ComfyUI-AdaptiveWindowSize/ComfyUI-AdaptiveWindowSize && \
    mv * ../


RUN mkdir -p /ComfyUI/models/diffusion_models /ComfyUI/models/loras /ComfyUI/models/clip_vision /ComfyUI/models/text_encoders /ComfyUI/models/vae && \
    hfd.sh Phr00t/WAN2.2-14B-Rapid-AllInOne \
      --include "Mega-v12/wan2.2-rapid-mega-aio-nsfw-v12.1.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_wan2.2 && \
    mv /tmp/hfd_wan2.2/Mega-v12/wan2.2-rapid-mega-aio-nsfw-v12.1.safetensors /ComfyUI/models/diffusion_models/ && \
    rm -rf /tmp/hfd_wan2.2

RUN hfd.sh lightx2v/Wan2.2-Lightning \
      --include "Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1/high_noise_model.safetensors" \
      --include "Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1/low_noise_model.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_lightning && \
    mv /tmp/hfd_lightning/Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1/high_noise_model.safetensors /ComfyUI/models/loras/ && \
    mv /tmp/hfd_lightning/Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1/low_noise_model.safetensors /ComfyUI/models/loras/ && \
    rm -rf /tmp/hfd_lightning

RUN hfd.sh Comfy-Org/Wan_2.1_ComfyUI_repackaged \
      --include "split_files/clip_vision/clip_vision_h.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_wan21 && \
    mv /tmp/hfd_wan21/split_files/clip_vision/clip_vision_h.safetensors /ComfyUI/models/clip_vision/ && \
    rm -rf /tmp/hfd_wan21

RUN hfd.sh Kijai/WanVideo_comfy \
      --include "umt5-xxl-enc-bf16.safetensors" \
      --include "Wan2_1_VAE_bf16.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_wanvideo && \
    mv /tmp/hfd_wanvideo/umt5-xxl-enc-bf16.safetensors /ComfyUI/models/text_encoders/ && \
    mv /tmp/hfd_wanvideo/Wan2_1_VAE_bf16.safetensors /ComfyUI/models/vae/ && \
    rm -rf /tmp/hfd_wanvideo

COPY . .
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
