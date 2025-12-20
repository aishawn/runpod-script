# Handler.py 执行流程图

## 一、整体执行流程

```
用户请求 (job)
    │
    ├─> 解析输入参数
    │   ├─> 图像输入 (path/url/base64)
    │   ├─> 结束图像 (可选)
    │   ├─> 提示词、尺寸、帧数等参数
    │   └─> LoRA 设置
    │
    ├─> 检测模型类型
    │   ├─> 检查 MEGA 模型
    │   ├─> 获取可用模型列表
    │   └─> 确定工作流类型
    │
    ├─> 加载工作流 JSON
    │   ├─> 优先使用 API 格式
    │   └─> 回退到 UI 格式
    │
    ├─> 格式转换 (如果是 UI 格式)
    │   ├─> 建立 SetNode 映射
    │   ├─> 建立 Links 映射
    │   ├─> 转换节点格式
    │   └─> 处理 widgets_values
    │
    ├─> 配置工作流
    │   ├─> 动态查找节点
    │   ├─> 设置输入参数
    │   └─> 更新模型路径
    │
    ├─> 自动填充缺失输入
    │   └─> 从 widgets_values 填充 inputs
    │
    ├─> 修正值类型错误
    │   ├─> 修正枚举值
    │   ├─> 修正路径格式
    │   └─> 修正设备设置
    │
    ├─> 连接 ComfyUI
    │   ├─> HTTP 连接检查
    │   └─> WebSocket 连接
    │
    ├─> 执行工作流
    │   ├─> 提交 prompt
    │   ├─> 监听执行状态
    │   ├─> 捕获错误
    │   └─> 获取生成的视频
    │
    └─> 返回结果
        └─> Base64 编码的视频
```

## 二、格式转换详细流程

### 2.1 convert_nodes_to_prompt_format()

```
UI 格式工作流
    │
    ├─> 步骤 1: 建立节点映射
    │   └─> all_nodes_map = {node_id: node}
    │
    ├─> 步骤 2: 解析 SetNode
    │   ├─> 遍历所有 SetNode
    │   ├─> 递归查找数据源
    │   └─> setnode_source_map = {name: [source_node, output_index]}
    │
    ├─> 步骤 3: 建立 Links 映射
    │   ├─> 遍历 links 数组
    │   ├─> 处理 GetNode 引用
    │   └─> links_map = {link_id: [source_node, output_index]}
    │
    ├─> 步骤 4: 转换节点
    │   ├─> 跳过逻辑节点 (SetNode, GetNode, Note 等)
    │   ├─> 转换 inputs:
    │   │   ├─> 有 link → [source_node, output_index]
    │   │   ├─> 有 widget → 从 widgets_values 提取
    │   │   └─> 有 value → 直接使用
    │   ├─> 设置 class_type
    │   └─> 添加到 prompt 字典
    │
    └─> 返回 API 格式 prompt
```

### 2.2 SetNode/GetNode 解析示例

```
原始工作流:
    SourceNode (id: 100)
        │
        ├─> SetNode (id: 200, name: "ref_embeds")
        │       │
        │       └─> GetNode (id: 300, name: "ref_embeds")
        │               │
        │               └─> TargetNode (id: 400)

转换后:
    setnode_source_map = {
        "ref_embeds": [100, 0]  // 指向 SourceNode 的输出 0
    }
    
    API 格式:
    {
        "100": {...},  // SourceNode
        "400": {
            "inputs": {
                "embeds": [100, 0]  // 直接引用 SourceNode
            }
        }
    }
```

## 三、工作流配置流程

### 3.1 configure_wan21_workflow()

```
输入: prompt, job_input, image_path, ...
    │
    ├─> 1. 查找输入图像节点
    │   ├─> find_node_by_class_type(prompt, "LoadImage")
    │   └─> set_node_value(image_node_id, "image", image_path)
    │
    ├─> 2. 处理参考视频 (可选)
    │   ├─> 查找视频加载节点
    │   └─> 设置视频路径
    │
    ├─> 3. 查找姿态检测节点
    │   ├─> find_node_by_class_type(prompt, "OnnxDetectionModelLoader")
    │   └─> 设置宽度和高度
    │
    ├─> 4. 查找模型加载节点
    │   ├─> find_node_by_class_type(prompt, "WanVideoModelLoader")
    │   ├─> find_wan21_model()  // 自动查找模型
    │   └─> 设置模型路径
    │
    ├─> 5. 查找文本编码节点
    │   ├─> 遍历所有节点
    │   ├─> 找到 WanVideoTextEncode 或 CLIPTextEncode
    │   └─> 设置 positive_prompt 和 negative_prompt
    │
    ├─> 6. 查找采样器节点
    │   ├─> 找到 WanVideoSampler
    │   └─> 设置 steps, seed, cfg
    │
    ├─> 7. 查找扩展嵌入节点
    │   ├─> 找到 WanVideoAddOneToAllExtendEmbeds
    │   └─> 设置 num_frames
    │
    └─> 8. 查找视频合成节点
        ├─> 找到 VHS_VideoCombine
        └─> 确保 save_output = True
```

## 四、自动填充缺失输入流程

### 4.1 fill_missing_inputs_from_widgets()

```
遍历所有节点
    │
    ├─> 检查节点类型
    │
    ├─> WanVideoScheduler
    │   ├─> widgets_values: [scheduler, steps, start_step, end_step, shift]
    │   └─> 填充到 inputs: {"scheduler": ..., "steps": ..., ...}
    │
    ├─> WanVideoAddOneToAllExtendEmbeds
    │   ├─> widgets_values: [num_frames, window_size, if_not_enough_frames]
    │   └─> 填充到 inputs，修正枚举值 (0 → "pad_with_last")
    │
    ├─> ImageBatchExtendWithOverlap
    │   ├─> widgets_values: [overlap, overlap_mode, overlap_side]
    │   └─> 修正枚举值 ("source" → "linear_blend")
    │
    ├─> WanVideoLoraSelect
    │   ├─> widgets_values: [lora, strength]
    │   └─> 规范化路径 (去除前缀)
    │
    └─> 其他节点类型...
        └─> 根据节点类型填充相应的 inputs
```

## 五、WebSocket 通信流程

### 5.1 get_videos()

```
提交 prompt
    │
    ├─> queue_prompt(prompt)
    │   └─> 返回 prompt_id
    │
    ├─> WebSocket 监听循环
    │   │
    │   ├─> 接收消息
    │   │
    │   ├─> executing 消息
    │   │   ├─> 记录节点执行状态
    │   │   └─> 如果 node_id == None，执行完成
    │   │
    │   ├─> execution_error 消息
    │   │   ├─> 记录错误信息
    │   │   ├─> 检查 OOM 错误
    │   │   └─> 记录到 node_errors
    │   │
    │   └─> progress 消息
    │       └─> 记录节点进度
    │
    ├─> 获取执行历史
    │   └─> get_history(prompt_id)
    │
    ├─> 检查错误
    │   └─> 如果有错误，抛出异常
    │
    └─> 提取视频
        ├─> 遍历 outputs
        ├─> 查找 videos 或 gifs
        └─> Base64 编码返回
```

## 六、错误处理流程

```
执行过程中
    │
    ├─> 格式转换错误
    │   ├─> 捕获异常
    │   └─> 记录详细错误信息
    │
    ├─> 节点查找失败
    │   ├─> 动态查找失败
    │   └─> 回退到硬编码节点 ID
    │
    ├─> 模型路径错误
    │   ├─> 自动搜索多个路径
    │   └─> 创建符号链接或复制文件
    │
    ├─> ComfyUI 连接失败
    │   ├─> 重试机制 (最多 180 次)
    │   └─> 超时后抛出异常
    │
    ├─> WebSocket 连接失败
    │   ├─> 重试机制 (最多 36 次)
    │   └─> 超时后抛出异常
    │
    ├─> 执行错误
    │   ├─> 捕获 execution_error 消息
    │   ├─> 检查 OOM 错误
    │   └─> 提供建议 (减小分辨率等)
    │
    └─> 无视频输出
        ├─> 检查所有输出节点
        └─> 返回详细错误信息
```

## 七、关键设计决策

### 7.1 为什么需要格式转换？

```
UI 格式 (可视化编辑)
    │
    ├─> 包含元数据 (位置、大小、颜色)
    ├─> 使用 links 数组描述连接
    ├─> 使用 SetNode/GetNode 逻辑节点
    └─> widgets_values 存储参数
    │
    └─> [格式转换] ──> API 格式 (执行)
        │
        ├─> 只包含必要信息
        ├─> 直接使用节点引用
        ├─> 解析 SetNode/GetNode
        └─> inputs 中存储参数
```

### 7.2 动态查找 vs 硬编码

```
硬编码方式:
    prompt["106"]["inputs"]["image"] = image_path
    ❌ 工作流更新时节点 ID 可能变化
    ❌ 不支持多种工作流变体

动态查找方式:
    image_node_id = find_node_by_class_type(prompt, "LoadImage")
    set_node_value(prompt, image_node_id, "image", image_path)
    ✅ 自动适应工作流变化
    ✅ 支持多种工作流
```

### 7.3 容错机制

```
主要操作
    │
    ├─> 动态查找
    │   └─> 失败 → 回退到硬编码
    │
    ├─> 模型路径
    │   └─> 搜索多个路径 → 创建链接
    │
    ├─> 值验证
    │   └─> 修正错误值 → 使用默认值
    │
    └─> 连接重试
        └─> 多次重试 → 超时异常
```

## 八、数据流示例

### 8.1 完整数据流

```
用户输入:
{
    "image_url": "https://example.com/image.jpg",
    "prompt": "running man",
    "width": 512,
    "height": 832,
    "length": 81
}
    │
    ├─> process_input() → image_path = "/tmp/task_xxx/input_image.jpg"
    │
    ├─> load_workflow() → workflow_data (UI 格式)
    │
    ├─> convert_nodes_to_prompt_format() → prompt (API 格式)
    │   {
    │       "106": {"class_type": "LoadImage", "inputs": {}},
    │       "22": {"class_type": "WanVideoModelLoader", "inputs": {}},
    │       ...
    │   }
    │
    ├─> configure_wan21_workflow() → 修改 prompt
    │   {
    │       "106": {"class_type": "LoadImage", "inputs": {"image": "/tmp/..."}},
    │       "22": {"class_type": "WanVideoModelLoader", "inputs": {"model": "..."}},
    │       ...
    │   }
    │
    ├─> fill_missing_inputs_from_widgets() → 填充缺失值
    │
    ├─> queue_prompt(prompt) → prompt_id
    │
    ├─> WebSocket 监听 → 执行状态
    │
    └─> get_history(prompt_id) → 提取视频 → Base64 编码 → 返回
```

