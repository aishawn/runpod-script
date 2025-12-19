# 路径验证表 - Wan21-OneToAllAnimation 模型

## 1. Hugging Face 仓库路径

| 项目 | 路径 | 状态 |
|------|------|------|
| 仓库名称 | `Kijai/WanVideo_comfy_fp8_scaled` | ✅ 正确 |
| 文件路径 | `OneToAllAnimation/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors` | ✅ 正确 |
| 验证来源 | `Wan21_OneToAllAnimation_example_01.json:4643` | ✅ 已确认 |

## 2. Dockerfile 下载和移动路径

| 步骤 | 路径 | 状态 |
|------|------|------|
| 下载临时目录 | `/tmp/hfd_wan21_otoa/OneToAllAnimation/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors` | ✅ 正确 |
| 最终目标目录 | `/ComfyUI/models/diffusion_models/WanVideo/OneToAll/` | ✅ 正确 |
| 最终文件路径 | `/ComfyUI/models/diffusion_models/WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors` | ✅ 正确 |

## 3. handler.py 中的路径引用

| 项目 | 路径 | 状态 |
|------|------|------|
| 相对路径（用于 ComfyUI） | `WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors` | ✅ 正确 |
| ComfyUI 查找目录 | `models/diffusion_models` (根据 extra_model_paths.yaml) | ✅ 正确 |
| 完整路径（验证） | `/ComfyUI/models/diffusion_models/WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors` | ✅ 与 Dockerfile 一致 |

## 4. 工作流文件中的路径

| 项目 | 路径 | 状态 |
|------|------|------|
| 节点22 widgets_values | `WanVideo\\OneToAll\\Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors` | ⚠️ Windows 路径分隔符 |
| handler.py 覆盖 | ✅ handler.py 会覆盖为 Unix 路径 | ✅ 已处理 |

## 5. 路径一致性验证

### 路径链验证：
```
Hugging Face 仓库
  ↓
Kijai/WanVideo_comfy_fp8_scaled/OneToAllAnimation/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors
  ↓ (hfd.sh 下载)
/tmp/hfd_wan21_otoa/OneToAllAnimation/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors
  ↓ (mv 移动)
/ComfyUI/models/diffusion_models/WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors
  ↓ (ComfyUI 查找)
models/diffusion_models/WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors
  ↓ (handler.py 引用)
WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors
```

## ✅ 结论

所有路径配置正确，路径链完整且一致。









