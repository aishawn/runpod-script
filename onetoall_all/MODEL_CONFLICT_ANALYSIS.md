# 模型冲突分析：SteadyDancer vs OneToAll

## 模型对比表

| 模型类型 | SteadyDancer | OneToAll | 冲突情况 |
|---------|-------------|----------|---------|
| **T5 文本编码器** | `umt5-xxl-enc-bf16.safetensors`<br/>`/ComfyUI/models/text_encoders/` | `umt5-xxl-enc-bf16.safetensors`<br/>`/ComfyUI/models/text_encoders/` | ✅ **无冲突**（相同文件） |
| **VAE** | `Wan2_1_VAE_bf16.safetensors`<br/>`/ComfyUI/models/vae/` | `Wan2_1_VAE_bf16.safetensors`<br/>`/ComfyUI/models/vae/` | ✅ **无冲突**（相同文件） |
| **主模型** | `Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors`<br/>`/ComfyUI/models/diffusion_models/WanVideo/SteadyDancer/` | `Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors`<br/>`/ComfyUI/models/diffusion_models/WanVideo/OneToAll/` | ✅ **无冲突**（不同路径） |
| **LoRA** | `lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors`<br/>`/ComfyUI/models/loras/WanVideo/Lightx2v/` | `lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16.safetensors`<br/>`/ComfyUI/models/loras/WanVideo/Lightx2v/` | ⚠️ **潜在冲突**（相同目录，不同文件） |
| **YOLO** | `yolov10m.onnx`<br/>`/ComfyUI/models/detection/` | `yolov10m.onnx`<br/>`/ComfyUI/models/onnx/` | ⚠️ **目录不同**（相同文件，不同位置） |
| **ViTPose** | `vitpose_h_wholebody_model.onnx`<br/>`/ComfyUI/models/detection/`<br/>（从 `vitpose-h-wholebody.onnx` 重命名） | `vitpose-l-wholebody.onnx`<br/>`/ComfyUI/models/onnx/` | ⚠️ **可能冲突**（不同文件名，但可能是同一模型的不同版本） |

## 详细分析

### 1. ✅ 无冲突的模型

- **T5 文本编码器**：两个环境使用相同的文件，可以共享
- **VAE**：两个环境使用相同的文件，可以共享
- **主模型**：虽然文件名不同，但存储在不同的子目录中，不会冲突

### 2. ⚠️ 潜在冲突的模型

#### LoRA 模型冲突

**SteadyDancer**:
- 文件：`lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors`
- 路径：`/ComfyUI/models/loras/WanVideo/Lightx2v/`

**OneToAll**:
- 文件：`lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16.safetensors`
- 路径：`/ComfyUI/models/loras/WanVideo/Lightx2v/`

**问题**：
- 两个文件存储在**相同的目录**中
- 文件名不同，但都是 `Lightx2v` 系列的 LoRA
- 如果两个环境共享同一个 ComfyUI 实例，两个文件可以共存（因为文件名不同）

**影响**：
- ✅ 如果使用不同的容器/环境：无影响
- ⚠️ 如果共享同一个 ComfyUI 实例：需要确保两个文件都存在

#### YOLO 模型位置冲突

**SteadyDancer**:
- 文件：`yolov10m.onnx`
- 路径：`/ComfyUI/models/detection/`

**OneToAll**:
- 文件：`yolov10m.onnx`
- 路径：`/ComfyUI/models/onnx/`

**问题**：
- 相同的文件存储在不同的目录中
- SteadyDancer 创建了从 `detection/` 到 `onnx/` 的符号链接
- OneToAll 创建了从 `onnx/` 到 `detection/` 的符号链接

**影响**：
- ✅ 如果两个环境都正确创建了符号链接，应该可以工作
- ⚠️ 但如果只运行一个环境的安装脚本，可能缺少符号链接

#### ViTPose 模型冲突

**SteadyDancer**:
- 文件：`vitpose_h_wholebody_model.onnx`（H 版本，重命名）
- 路径：`/ComfyUI/models/detection/`
- 来源：`vitpose-h-wholebody.onnx`

**OneToAll**:
- 文件：`vitpose-l-wholebody.onnx`（L 版本）
- 路径：`/ComfyUI/models/onnx/`

**问题**：
- **不同的模型版本**：`vitpose-h` (H = Heavy/Large) vs `vitpose-l` (L = Light)
- 不同的文件名和存储位置
- 工作流可能期望不同的模型

**影响**：
- ⚠️ **这是真正的冲突**：两个工作流需要不同的 ViTPose 模型
- 如果 OneToAll 工作流期望 `vitpose-l-wholebody.onnx`，但只有 `vitpose_h_wholebody_model.onnx`，可能会失败
- 反之亦然

## 解决方案

### 方案 1：确保两个模型都存在（推荐）

修改 `env_install.sh`，确保同时下载两个 ViTPose 模型：

```bash
# ViTPose L (OneToAll 需要)
if [ ! -f "$WORKDIR/ComfyUI/models/onnx/vitpose-l-wholebody.onnx" ]; then
    hfd.sh JunkyByte/easy_ViTPose \
          --include "onnx/wholebody/vitpose-l-wholebody.onnx" \
          ...
fi

# ViTPose H (SteadyDancer 需要，如果将来需要支持)
if [ ! -f "$WORKDIR/ComfyUI/models/detection/vitpose_h_wholebody_model.onnx" ]; then
    hfd.sh JunkyByte/easy_ViTPose \
          --include "onnx/wholebody/vitpose-h-wholebody.onnx" \
          ...
    mv .../vitpose-h-wholebody.onnx "$WORKDIR/ComfyUI/models/detection/vitpose_h_wholebody_model.onnx"
fi
```

### 方案 2：统一模型位置

确保所有 ONNX 模型都存储在 `detection/` 目录，并创建到 `onnx/` 的符号链接（或反之）。

### 方案 3：使用不同的容器/环境

如果可能，为每个工作流使用独立的容器，避免模型冲突。

## 当前问题

从错误日志看，节点 80 (WanVideoSetLoRAs) 仍然报错：
```
Set LoRA node does not use low_mem_load and can't merge LoRAs, disable 'merge_loras' in the LoRA select node.
```

这说明 `merge_loras` 参数仍然没有被正确设置。让我检查一下代码是否正确执行了修复逻辑。

## 建议

1. **立即修复**：确保 `merge_loras` 参数被正确设置（代码已修复，但需要验证）
2. **长期优化**：统一模型存储位置，避免目录混乱
3. **文档化**：明确记录每个工作流需要的模型和版本

