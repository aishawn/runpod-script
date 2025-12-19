#!/usr/bin/env python3
"""
最终检查核对
"""
import json
import os

print("=" * 60)
print("最终检查核对")
print("=" * 60)

# 1. 检查 API workflow 文件
print("\n1. 检查 API workflow 文件...")
api_file = "Wan21_OneToAllAnimation_example_01_api.json"
if os.path.exists(api_file):
    with open(api_file, 'r', encoding='utf-8') as f:
        api_data = json.load(f)
    print(f"   ✓ 文件存在: {api_file}")
    print(f"   ✓ 节点数量: {len(api_data)}")
    print(f"   ✓ 格式: API格式 (无nodes数组)" if "nodes" not in api_data or not isinstance(api_data.get("nodes"), list) else "   ✗ 格式: 仍为nodes数组格式")
    
    # 检查关键节点
    key_nodes = {
        "106": "LoadImage",
        "22": "WanVideoModelLoader", 
        "16": "WanVideoTextEncode",
        "27": "WanVideoSampler",
        "263": "WanVideoAddOneToAllExtendEmbeds"
    }
    print("\n   关键节点检查:")
    for node_id, expected_type in key_nodes.items():
        if node_id in api_data:
            actual_type = api_data[node_id].get("class_type", "")
            if expected_type in actual_type:
                print(f"   ✓ 节点 {node_id}: {actual_type}")
            else:
                print(f"   ✗ 节点 {node_id}: 期望 {expected_type}, 实际 {actual_type}")
        else:
            print(f"   ✗ 节点 {node_id}: 不存在")
else:
    print(f"   ✗ 文件不存在: {api_file}")

# 2. 检查 handler.py 配置
print("\n2. 检查 handler.py 配置...")
handler_file = "handler.py"
if os.path.exists(handler_file):
    with open(handler_file, 'r', encoding='utf-8') as f:
        handler_content = f.read()
    
    checks = [
        ("优先使用 API 格式", "Wan21_OneToAllAnimation_example_01_api.json" in handler_content),
        ("VHS_VideoCombine 配置", "VHS_VideoCombine" in handler_content and "save_output" in handler_content),
        ("API 格式检测", '"nodes" in workflow_data' in handler_content),
        ("Wan21 workflow 配置", "configure_wan21_workflow" in handler_content)
    ]
    
    for desc, result in checks:
        print(f"   {'✓' if result else '✗'} {desc}")
else:
    print(f"   ✗ 文件不存在: {handler_file}")

# 3. 检查转换脚本
print("\n3. 检查转换脚本...")
convert_file = "convert_workflow_to_api.py"
if os.path.exists(convert_file):
    with open(convert_file, 'r', encoding='utf-8') as f:
        convert_content = f.read()
    
    checks = [
        ("UUID 节点处理", "len(node_type) == 36" in convert_content),
        ("SetNode 处理", "SetNode" in convert_content and "resolve_setnode_source" in convert_content),
        ("子图节点转换", "WanVideoAddOneToAllExtendEmbeds" in convert_content)
    ]
    
    for desc, result in checks:
        print(f"   {'✓' if result else '✗'} {desc}")
else:
    print(f"   ✗ 文件不存在: {convert_file}")

# 4. 检查验证脚本
print("\n4. 检查验证脚本...")
validate_file = "validate_workflow.py"
if os.path.exists(validate_file):
    print(f"   ✓ 验证脚本存在: {validate_file}")
else:
    print(f"   ✗ 验证脚本不存在: {validate_file}")

print("\n" + "=" * 60)
print("检查完成!")
print("=" * 60)

