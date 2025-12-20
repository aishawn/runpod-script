# Handler.py 修复总结

## 问题描述

错误信息：
```
Return type mismatch between linked nodes: images, received_type(WANVIDIMAGE_EMBEDS) mismatch input_type(IMAGE)
```

发生在 `VHS_VideoCombine` 节点（节点 292 和 306），这些节点的 `images` 输入期望 `IMAGE` 类型，但实际接收到的是 `WANVIDIMAGE_EMBEDS` 类型。

## 根本原因

1. **UUID 子图节点未正确转换**
   - 节点 297 和 311 是子图节点（type 是 UUID：`cd88a71a-291e-45fd-9414-2c1f20b86257` 和 `70a9c226-a6dc-4e8e-9cb9-f16fd821a543`）
   - 这些子图内部包含 `WanVideoAddOneToAllExtendEmbeds` 节点
   - 在 `convert_nodes_to_prompt_format` 函数中，UUID 被直接设置为 `class_type`
   - ComfyUI API 无法识别 UUID 类型的节点，导致类型验证失败

2. **输出索引可能不正确**
   - 即使节点类型正确，如果输出索引不正确，也可能导致类型不匹配
   - 需要确保 `VHS_VideoCombine` 的 `images` 输入指向正确的输出索引（extended_images，IMAGE 类型）

## 修复方案

### 1. 添加 UUID 子图节点处理逻辑

在 `convert_nodes_to_prompt_format` 函数中添加了处理 UUID 子图节点的逻辑：

```python
# 处理 UUID 类型的节点（通常是子图节点）
if len(str(node_type)) == 36 and str(node_type).count('-') == 4:  # UUID 格式
    # 从 workflow 的 definitions/subgraphs 中查找实际的节点类型
    # 或者根据节点标题推断（如 "Extend" 对应 "WanVideoAddOneToAllExtendEmbeds"）
```

**处理流程**：
1. 检查节点 type 是否为 UUID 格式（36 个字符，4 个连字符）
2. 从 `workflow_data["definitions"]["subgraphs"]` 中查找子图定义
3. 在子图内部节点中查找 `WanVideoAddOneToAllExtendEmbeds` 节点
4. 如果找不到，根据节点标题推断（如 "Extend" → "WanVideoAddOneToAllExtendEmbeds"）
5. 将 UUID 替换为实际的节点类型

### 2. 增强 VHS_VideoCombine 类型检查

在修正值类型错误部分，增强了 `VHS_VideoCombine` 的类型检查：

```python
# 处理子图节点（UUID 类型）或 WanVideoAddOneToAllExtendEmbeds
is_extend_node = ("WanVideoAddOneToAllExtendEmbeds" in source_class or 
                 "WanVideoAddOneToAllExtendEmbeds" in str(source_type) or
                 "extend" in source_node.get("title", "").lower())

if is_extend_node:
    # 从原始工作流数据中获取输出定义
    # 查找 extended_images 输出（IMAGE 类型）
    # 确保使用正确的输出索引
```

**处理流程**：
1. 识别源节点是否为扩展节点（通过 class_type、type 或 title）
2. 从原始工作流数据（UI 格式）中获取节点的输出定义
3. 查找 `extended_images` 输出（IMAGE 类型）
4. 如果找到，确保 `VHS_VideoCombine` 的 `images` 输入使用正确的输出索引
5. 如果找不到名称匹配的，查找第一个 IMAGE 类型的输出

### 3. 添加安全检查

添加了检查，确保只在 UI 格式工作流中进行类型检查：

```python
if "nodes" in workflow_data:
    # 只在 UI 格式工作流中检查
```

## 修复效果

修复后：
1. ✅ UUID 子图节点会被正确识别为 `WanVideoAddOneToAllExtendEmbeds`
2. ✅ `VHS_VideoCombine` 的 `images` 输入会指向正确的输出索引（IMAGE 类型）
3. ✅ 类型验证通过，ComfyUI API 可以正确执行工作流

## 测试建议

1. **测试 UUID 子图节点转换**
   - 验证节点 297 和 311 的 `class_type` 是否正确设置为 `WanVideoAddOneToAllExtendEmbeds`
   - 检查日志中是否有 "将子图 UUID ... 替换为 ..." 的信息

2. **测试 VHS_VideoCombine 类型检查**
   - 验证节点 292 和 306 的 `images` 输入是否正确指向 IMAGE 类型的输出
   - 检查日志中是否有 "修正 images 输入来自节点 ... 的输出索引 ... -> ..." 的信息

3. **测试完整工作流执行**
   - 运行完整的工作流，验证不再出现类型不匹配错误
   - 确认视频能够正常生成

## 相关代码位置

- **UUID 子图节点处理**：`handler.py` 第 516-560 行
- **VHS_VideoCombine 类型检查**：`handler.py` 第 1452-1504 行

## 注意事项

1. 如果工作流已经是 API 格式（没有 "nodes" 字段），类型检查会被跳过
2. 如果无法识别子图节点类型，会保持原 UUID（可能会失败，但不会破坏结构）
3. 如果找不到 IMAGE 类型的输出，会记录警告但不会自动修复

