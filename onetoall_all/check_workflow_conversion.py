#!/usr/bin/env python3
"""
检查 workflow 转换是否正确
对比原始 workflow 和 API workflow，确保关键节点都正确转换
"""

import json
import sys

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def check_node_conversion(original, api):
    """检查节点转换是否正确"""
    issues = []
    
    # 收集原始 workflow 中的关键节点
    original_nodes = {}
    if "nodes" in original:
        for node in original["nodes"]:
            node_id = str(node.get("id", ""))
            node_type = node.get("type", "")
            original_nodes[node_id] = {
                "type": node_type,
                "widgets_values": node.get("widgets_values", []),
                "inputs": node.get("inputs", [])
            }
    
    # 检查 API workflow 中的关键节点
    api_nodes = {}
    for node_id, node in api.items():
        api_nodes[node_id] = {
            "class_type": node.get("class_type", ""),
            "type": node.get("type", ""),
            "inputs": node.get("inputs", {}),
            "widgets_values": node.get("widgets_values", [])
        }
    
    # 检查关键节点
    critical_nodes = {
        "11": "LoadWanVideoT5TextEncoder",
        "16": "WanVideoTextEncode",
        "22": "WanVideoModelLoader",
        "38": "WanVideoVAELoader",
        "128": "OnnxDetectionModelLoader",
        "141": "PoseDetectionOneToAllAnimation",
        "137": "VHS_VideoCombine",
        "139": "VHS_VideoCombine",
        "160": "VHS_VideoCombine",
        "250": "VHS_VideoCombine",
        "292": "VHS_VideoCombine",
        "306": "VHS_VideoCombine",
        "231": "WanVideoScheduler",
        "27": "WanVideoSampler",
        "163": "WanVideoSampler",
        "28": "WanVideoDecode",
        "182": "WanVideoDecode",
    }
    
    print("=" * 80)
    print("关键节点检查")
    print("=" * 80)
    
    for node_id, expected_type in critical_nodes.items():
        if node_id not in api_nodes:
            issues.append(f"❌ 节点 {node_id} ({expected_type}) 在 API workflow 中不存在")
            continue
        
        node = api_nodes[node_id]
        actual_type = node.get("class_type", "") or node.get("type", "")
        
        if expected_type not in actual_type:
            issues.append(f"⚠️  节点 {node_id}: 期望类型 {expected_type}, 实际类型 {actual_type}")
        else:
            print(f"✓ 节点 {node_id}: {expected_type}")
            
            # 检查必需输入
            inputs = node.get("inputs", {})
            widgets = node.get("widgets_values", [])
            
            if expected_type == "LoadWanVideoT5TextEncoder":
                if "model_name" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 model_name")
                if "precision" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 precision")
            
            elif expected_type == "WanVideoTextEncode":
                if "positive_prompt" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 positive_prompt")
                if "negative_prompt" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 negative_prompt")
            
            elif expected_type == "WanVideoModelLoader":
                if "model" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 model")
                else:
                    model_path = inputs["model"]
                    if model_path.startswith("/ComfyUI/"):
                        issues.append(f"⚠️  节点 {node_id}: 模型路径是完整路径，应该是相对路径: {model_path}")
                if "quantization" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 quantization")
                if "load_device" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 load_device")
                if "base_precision" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 base_precision")
            
            elif expected_type == "WanVideoVAELoader":
                if "model_name" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 model_name")
            
            elif expected_type == "OnnxDetectionModelLoader":
                if "vitpose_model" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 vitpose_model")
                if "yolo_model" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 yolo_model")
                if "onnx_device" not in inputs:
                    issues.append(f"❌ 节点 {node_id}: 缺少 onnx_device")
            
            elif expected_type == "PoseDetectionOneToAllAnimation":
                if "align_to" not in inputs:
                    issues.append(f"⚠️  节点 {node_id}: 缺少 align_to (将使用默认值)")
                if "draw_face_points" not in inputs:
                    issues.append(f"⚠️  节点 {node_id}: 缺少 draw_face_points (将使用默认值)")
                if "draw_head" not in inputs:
                    issues.append(f"⚠️  节点 {node_id}: 缺少 draw_head (将使用默认值)")
            
            elif expected_type == "VHS_VideoCombine":
                required = ["filename_prefix", "loop_count", "frame_rate", "pingpong", "format"]
                for req in required:
                    if req not in inputs:
                        issues.append(f"❌ 节点 {node_id}: 缺少 {req}")
                if "save_output" not in inputs:
                    issues.append(f"⚠️  节点 {node_id}: 缺少 save_output (将在 handler.py 中设置)")
                elif inputs.get("save_output") == False:
                    issues.append(f"⚠️  节点 {node_id}: save_output 为 False (将在 handler.py 中设置为 True)")
            
            elif expected_type == "WanVideoScheduler":
                required = ["scheduler", "steps", "start_step", "end_step", "shift"]
                for req in required:
                    if req not in inputs:
                        issues.append(f"❌ 节点 {node_id}: 缺少 {req}")
            
            elif expected_type == "WanVideoSampler":
                required = ["steps", "seed", "cfg"]
                for req in required:
                    if req not in inputs:
                        issues.append(f"⚠️  节点 {node_id}: 缺少 {req} (将在 handler.py 中设置)")
                if "shift" not in inputs:
                    issues.append(f"⚠️  节点 {node_id}: 缺少 shift (将使用默认值)")
                if "riflex_freq_index" not in inputs:
                    issues.append(f"⚠️  节点 {node_id}: 缺少 riflex_freq_index (将使用默认值)")
                if "force_offload" not in inputs:
                    issues.append(f"⚠️  节点 {node_id}: 缺少 force_offload (将使用默认值)")
            
            elif expected_type == "WanVideoDecode":
                required = ["tile_x", "tile_y", "tile_stride_x", "tile_stride_y", "enable_vae_tiling"]
                for req in required:
                    if req not in inputs:
                        issues.append(f"❌ 节点 {node_id}: 缺少 {req}")
    
    # 检查 UUID 类型的节点
    print("\n" + "=" * 80)
    print("UUID 节点检查")
    print("=" * 80)
    uuid_nodes = []
    for node_id, node in api.items():
        node_type = node.get("type", "")
        if len(node_type) == 36 and node_type.count('-') == 4:
            uuid_nodes.append((node_id, node_type))
    
    if uuid_nodes:
        for node_id, uuid_type in uuid_nodes:
            issues.append(f"❌ 节点 {node_id}: 仍然是 UUID 类型 {uuid_type}，未转换")
            print(f"❌ 节点 {node_id}: {uuid_type}")
    else:
        print("✓ 没有未转换的 UUID 节点")
    
    # 检查类型不匹配问题
    print("\n" + "=" * 80)
    print("类型不匹配检查")
    print("=" * 80)
    
    # 检查 VHS_VideoCombine 节点的 images 输入类型
    for node_id, node in api.items():
        if "VHS_VideoCombine" in node.get("class_type", ""):
            inputs = node.get("inputs", {})
            if "images" in inputs:
                image_source = inputs["images"]
                if isinstance(image_source, list) and len(image_source) >= 1:
                    source_node_id = str(image_source[0])
                    if source_node_id in api_nodes:
                        source_node = api_nodes[source_node_id]
                        source_type = source_node.get("class_type", "") or source_node.get("type", "")
                        # 检查源节点输出类型
                        if "WANVIDIMAGE_EMBEDS" in source_type or "WanVideoAddOneToAllExtendEmbeds" in source_type:
                            issues.append(f"⚠️  节点 {node_id} (VHS_VideoCombine): images 输入来自 {source_node_id} ({source_type})，类型是 WANVIDIMAGE_EMBEDS，但 VHS_VideoCombine 期望 IMAGE 类型")
    
    return issues

def main():
    original_file = "Wan21_OneToAllAnimation_example_01.json"
    api_file = "Wan21_OneToAllAnimation_example_01_api.json"
    
    print(f"读取原始 workflow: {original_file}")
    original = load_json(original_file)
    
    print(f"读取 API workflow: {api_file}")
    api = load_json(api_file)
    
    print(f"\n原始 workflow 节点数: {len(original.get('nodes', []))}")
    print(f"API workflow 节点数: {len(api)}")
    
    issues = check_node_conversion(original, api)
    
    print("\n" + "=" * 80)
    print("问题总结")
    print("=" * 80)
    
    if issues:
        for issue in issues:
            print(issue)
        print(f"\n共发现 {len(issues)} 个问题")
        return 1
    else:
        print("✓ 没有发现问题")
        return 0

if __name__ == "__main__":
    sys.exit(main())

