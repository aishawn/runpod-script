#!/usr/bin/env python3
"""
验证 API 格式的 workflow 文件
"""
import json
import sys
import re

def validate_workflow(workflow_file):
    """验证 workflow 文件"""
    print(f"验证 workflow 文件: {workflow_file}")
    
    with open(workflow_file, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    # 获取所有节点ID
    node_ids = set(workflow.keys())
    print(f"✓ 总节点数: {len(node_ids)}")
    
    # 查找所有节点引用
    workflow_str = json.dumps(workflow)
    # 匹配格式: ["节点ID", 输出索引]
    refs = re.findall(r'\[\s*"(\d+)"\s*,\s*\d+\s*\]', workflow_str)
    referenced_nodes = set(refs)
    
    print(f"✓ 被引用的节点数: {len(referenced_nodes)}")
    
    # 检查缺失的节点
    missing_nodes = referenced_nodes - node_ids
    if missing_nodes:
        print(f"❌ 缺失的节点引用: {sorted(missing_nodes, key=int)}")
        return False
    else:
        print("✓ 所有节点引用都存在")
    
    # 检查是否有 class_type
    missing_class_type = []
    for node_id, node in workflow.items():
        if "class_type" not in node:
            missing_class_type.append(node_id)
    
    if missing_class_type:
        print(f"❌ 缺少 class_type 的节点: {sorted(missing_class_type, key=int)}")
        return False
    else:
        print("✓ 所有节点都有 class_type")
    
    # 检查 UUID 类型的节点（应该已经被转换）
    uuid_nodes = []
    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        if len(class_type) == 36 and class_type.count('-') == 4:
            uuid_nodes.append((node_id, class_type))
    
    if uuid_nodes:
        print(f"⚠️  仍有 UUID 类型的节点（可能未转换）:")
        for node_id, uuid_type in uuid_nodes:
            print(f"   节点 {node_id}: {uuid_type}")
        return False
    else:
        print("✓ 没有未转换的 UUID 节点")
    
    # 检查关键节点
    key_nodes = {
        "LoadImage": "图像加载节点",
        "WanVideoModelLoader": "模型加载节点",
        "WanVideoTextEncode": "文本编码节点",
        "WanVideoSampler": "采样器节点",
        "VHS_VideoCombine": "视频输出节点"
    }
    
    found_key_nodes = {}
    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        for key_type, desc in key_nodes.items():
            if key_type in class_type:
                if key_type not in found_key_nodes:
                    found_key_nodes[key_type] = []
                found_key_nodes[key_type].append(node_id)
    
    print("\n关键节点检查:")
    for key_type, desc in key_nodes.items():
        if key_type in found_key_nodes:
            print(f"  ✓ {desc} ({key_type}): 节点 {', '.join(found_key_nodes[key_type])}")
        else:
            print(f"  ⚠️  {desc} ({key_type}): 未找到")
    
    print("\n✅ Workflow 验证通过!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_workflow.py <workflow_file.json>")
        sys.exit(1)
    
    workflow_file = sys.argv[1]
    if not validate_workflow(workflow_file):
        sys.exit(1)

