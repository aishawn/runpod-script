# Wan21_OneToAllAnimation JSON 格式差异分析

## 概述

这两个文件代表 ComfyUI 工作流的两种不同格式：
- **Wan21_OneToAllAnimation_example_01_api.json** (2410行) - **API 格式**（用于 ComfyUI API 调用）
- **Wan21_OneToAllAnimation_example_01.json** (9315行) - **完整格式**（ComfyUI 编辑器保存的完整工作流）

## 主要差异

### 1. 文件结构

#### API 格式 (`_api.json`)
```json
{
  "11": { ... },  // 节点ID直接作为key
  "98": { ... },
  "106": { ... }
}
```
- **扁平结构**：节点ID作为根对象的键
- **无额外元数据**：只包含节点定义
- **42个节点**

#### 完整格式 (`.json`)
```json
{
  "id": "c6e410bc-5e2c-460b-ae81-c91b6094fbb1",
  "revision": 0,
  "last_node_id": 311,
  "last_link_id": 503,
  "nodes": [ ... ],  // 节点数组
  "links": [ ... ],  // 链接数组
  "config": {},
  "extra": { ... },
  "version": 0.4
}
```
- **嵌套结构**：节点在 `nodes` 数组中
- **包含元数据**：工作流ID、版本、配置等
- **包含链接信息**：独立的 `links` 数组
- **更多节点**：包含 GetNode/SetNode 等辅助节点

### 2. 节点输入/输出格式

#### API 格式 - 输入
```json
{
  "inputs": {
    "embeds": ["105", 0],  // 直接引用 [节点ID, 输出索引]
    "pose_images": ["195", 0]
  }
}
```

#### 完整格式 - 输入
```json
{
  "inputs": [
    {
      "name": "embeds",
      "type": "WANVIDIMAGE_EMBEDS",
      "link": 332  // 通过 link ID 引用
    },
    {
      "name": "pose_images",
      "type": "IMAGE",
      "link": 352
    }
  ]
}
```

**关键差异**：
- API格式：`inputs` 是对象，值直接是 `[节点ID, 输出索引]`
- 完整格式：`inputs` 是数组，每个输入有 `link` 属性指向链接ID

### 3. 链接系统

#### API 格式
- **隐式链接**：链接信息直接嵌入在节点的 `inputs` 中
- 通过 `[节点ID, 输出索引]` 直接引用

#### 完整格式
- **显式链接**：独立的 `links` 数组
```json
{
  "links": [
    {
      "id": 332,
      "origin_id": 105,
      "origin_slot": 0,
      "target_id": 98,
      "target_slot": 0,
      "type": "WANVIDIMAGE_EMBEDS"
    }
  ]
}
```

### 4. 节点数量差异

| 格式 | 节点数 | 说明 |
|------|--------|------|
| API格式 | 42个 | 只包含实际执行需要的节点 |
| 完整格式 | 更多 | 包含 GetNode/SetNode 等辅助节点和完整元数据 |

### 5. 字段差异

#### API 格式特有
- `class_type`: 节点类型（ComfyUI API 必需）

#### 完整格式特有
- `id`: 节点ID（在节点对象内）
- `localized_name`: 本地化名称
- `shape`: 输入形状信息
- `title`: 节点标题
- 工作流级别的 `id`, `revision`, `version`, `extra` 等

### 6. 使用场景

#### API 格式 (`_api.json`)
- ✅ **ComfyUI API 调用**：直接用于 `/prompt` 端点
- ✅ **程序化生成**：易于通过代码修改和生成
- ✅ **文件更小**：只包含必要信息
- ✅ **RunPod/API 服务**：适合服务器端使用

#### 完整格式 (`.json`)
- ✅ **ComfyUI 编辑器**：保存/加载工作流
- ✅ **可视化编辑**：包含完整的UI信息（位置、大小等）
- ✅ **版本控制**：包含工作流ID和版本信息
- ✅ **完整备份**：包含所有元数据和辅助节点

### 7. 转换关系

从代码中可以看到，存在转换函数将完整格式转换为API格式：

```python
def convert_workflow_nodes_to_prompt(workflow_data):
    """将 nodes 数组格式转换为节点 ID key 格式"""
    # 1. 建立 links 映射
    # 2. 转换 inputs 数组为 inputs 对象
    # 3. 将 link ID 转换为 [节点ID, 输出索引]
    # 4. 提取有效节点，跳过 GetNode/SetNode
```

### 8. 实际示例对比

#### 节点 98 (WanVideoAddOneToAllPoseEmbeds)

**API 格式**:
```json
{
  "98": {
    "type": "WanVideoAddOneToAllPoseEmbeds",
    "inputs": {
      "embeds": ["105", 0],
      "pose_images": ["195", 0],
      "pose_prefix_image": ["141", 1]
    },
    "class_type": "WanVideoAddOneToAllPoseEmbeds"
  }
}
```

**完整格式**:
```json
{
  "id": 98,
  "type": "WanVideoAddOneToAllPoseEmbeds",
  "inputs": [
    {
      "name": "embeds",
      "type": "WANVIDIMAGE_EMBEDS",
      "link": 332
    },
    {
      "name": "pose_images",
      "type": "IMAGE",
      "link": 352
    },
    {
      "name": "pose_prefix_image",
      "shape": 7,
      "type": "IMAGE",
      "link": 329
    }
  ]
}
```

## 总结

| 特性 | API 格式 | 完整格式 |
|------|---------|---------|
| **用途** | API调用 | 编辑器保存 |
| **结构** | 扁平（节点ID为key） | 嵌套（nodes数组） |
| **链接** | 隐式（直接引用） | 显式（links数组） |
| **输入格式** | 对象 `{name: [id, idx]}` | 数组 `[{name, link}]` |
| **元数据** | 最少 | 完整 |
| **文件大小** | 小（2410行） | 大（9315行） |
| **节点数** | 42个核心节点 | 更多（含辅助节点） |
| **可编辑性** | 程序化友好 | 可视化友好 |

## 建议

1. **API 调用**：使用 `_api.json` 格式
2. **工作流编辑**：使用完整 `.json` 格式
3. **自动化处理**：需要转换函数将完整格式转为API格式
4. **版本控制**：保存完整格式以保留所有信息

