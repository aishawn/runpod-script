#!/usr/bin/env python3
"""
将 ComfyUI workflow (nodes 数组格式) 转换为 API 格式 (节点ID key格式)
"""
import json
import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_getnode_class_name():
    """获取GetNode节点的实际class_type名称"""
    # 默认返回，实际使用时需要查询 ComfyUI API
    return "GetNode|comfyui-logic"


def convert_nodes_to_prompt_format(workflow_data, logic_node_values=None, getnode_class_name="GetNode|comfyui-logic"):
    """将nodes数组格式转换为节点ID key格式"""
    if logic_node_values is None:
        logic_node_values = {}
    
    prompt = {}
    all_nodes_map = {str(node["id"]): node for node in workflow_data.get("nodes", [])}
    
    # 建立SetNode映射
    setnode_source_map = {}
    def resolve_setnode_source(setnode_node_id, visited=None):
        if visited is None:
            visited = set()
        if setnode_node_id in visited:
            return None
        visited.add(setnode_node_id)
        
        setnode_node = all_nodes_map.get(setnode_node_id)
        if not setnode_node or setnode_node.get("type") != "SetNode":
            return None
        
        if "inputs" in setnode_node and isinstance(setnode_node["inputs"], list):
            for input_item in setnode_node["inputs"]:
                if isinstance(input_item, dict) and input_item.get("link"):
                    link_id = input_item["link"]
                    for link in workflow_data.get("links", []):
                        if len(link) >= 6 and link[0] == link_id:
                            source_node_id = str(link[1])
                            source_output_index = link[2]
                            source_node = all_nodes_map.get(source_node_id)
                            if source_node:
                                if source_node.get("type") == "SetNode":
                                    result = resolve_setnode_source(source_node_id, visited)
                                    if result:
                                        return result
                                elif source_node.get("type") == "GetNode":
                                    widgets = source_node.get("widgets_values", [])
                                    if widgets and isinstance(widgets, list):
                                        getnode_name = widgets[0]
                                        for sn_id, sn_node in all_nodes_map.items():
                                            if sn_node.get("type") == "SetNode":
                                                sn_widgets = sn_node.get("widgets_values", [])
                                                if sn_widgets and sn_widgets[0] == getnode_name:
                                                    result = resolve_setnode_source(sn_id, visited)
                                                    if result:
                                                        return result
                                else:
                                    return [source_node_id, source_output_index]
        return None
    
    for node_id, node in all_nodes_map.items():
        if node.get("type") == "SetNode":
            widgets = node.get("widgets_values", [])
            if widgets and isinstance(widgets, list):
                setnode_name = widgets[0]
                resolved_source = resolve_setnode_source(node_id)
                if resolved_source:
                    setnode_source_map[setnode_name] = resolved_source
    
    # 建立links映射
    links_map = {}
    if "links" in workflow_data:
        for link in workflow_data["links"]:
            if len(link) >= 6:
                link_id = link[0]
                source_node_id = str(link[1])
                source_output_index = link[2]
                
                # 处理 SetNode 输出链接：解析到 SetNode 的源节点
                source_node = all_nodes_map.get(source_node_id)
                if source_node and source_node.get("type") == "SetNode":
                    resolved_source = resolve_setnode_source(source_node_id)
                    if resolved_source:
                        source_node_id, source_output_index = resolved_source
                
                # 处理 GetNode 输入链接：解析到对应的 SetNode 源节点
                if source_node and source_node.get("type") == "GetNode":
                    widgets = source_node.get("widgets_values", [])
                    if widgets and isinstance(widgets, list):
                        getnode_name = widgets[0]
                        if getnode_name in setnode_source_map:
                            source_node_id, source_output_index = setnode_source_map[getnode_name]
                
                links_map[link_id] = [source_node_id, source_output_index]
    
    # 转换节点
    skip_types = {"Note", "MarkdownNote", "SetNode", "Reroute", "PrimitiveNode",
                  "FloatConstant", "IntConstant", "INTConstant", "StringConstant", "BooleanConstant"}
    
    for node in workflow_data.get("nodes", []):
        node_id = str(node["id"])
        node_type = node.get("type", "")
        
        if node_id in logic_node_values or node_type in skip_types or "GetNode" in str(node_type):
            continue
        
        converted_node = {}
        for key, value in node.items():
            if key == "id":
                continue
            elif key == "inputs":
                converted_inputs = {}
                widgets_values = node.get("widgets_values", [])
                widgets_values_is_dict = isinstance(widgets_values, dict)
                if not widgets_values_is_dict and not isinstance(widgets_values, list):
                    widgets_values = []
                
                widget_index = 0
                if isinstance(value, list):
                    for input_item in value:
                        if isinstance(input_item, dict) and "name" in input_item:
                            input_name = input_item["name"]
                            has_widget = "widget" in input_item
                            has_link = input_item.get("link")
                            
                            if has_link:
                                link_id = input_item["link"]
                                if link_id in links_map:
                                    source_node_id, source_output_index = links_map[link_id]
                                    if source_node_id in logic_node_values:
                                        converted_inputs[input_name] = logic_node_values[source_node_id]
                                    else:
                                        source_node = all_nodes_map.get(str(source_node_id))
                                        if source_node:
                                            st = source_node.get("type", "")
                                            if st in ["PrimitiveNode", "FloatConstant", "IntConstant", "INTConstant", "StringConstant", "BooleanConstant"]:
                                                const_widgets = source_node.get("widgets_values", [])
                                                if const_widgets and isinstance(const_widgets, list):
                                                    converted_inputs[input_name] = const_widgets[0]
                                            else:
                                                converted_inputs[input_name] = [source_node_id, source_output_index]
                                        else:
                                            converted_inputs[input_name] = [source_node_id, source_output_index]
                                if not widgets_values_is_dict and has_widget and widget_index < len(widgets_values):
                                    widget_index += 1
                            else:
                                if "value" in input_item:
                                    converted_inputs[input_name] = input_item["value"]
                                elif has_widget:
                                    if widgets_values_is_dict:
                                        widget_value = widgets_values.get(input_name)
                                    elif widget_index < len(widgets_values):
                                        widget_value = widgets_values[widget_index]
                                        widget_index += 1
                                    else:
                                        widget_value = None
                                    if widget_value is not None:
                                        converted_inputs[input_name] = widget_value
                elif isinstance(value, dict):
                    converted_inputs = value.copy()
                
                # 对于有 widgets_values 的节点，尝试推断输入参数（即使 inputs 不为空也要补充）
                # 这主要针对 LoadWanVideoT5TextEncoder, WanVideoModelLoader 等节点
                if widgets_values and not widgets_values_is_dict and isinstance(widgets_values, list) and len(widgets_values) > 0:
                    node_type = node.get("type", "")
                    # 常见节点的 widgets_values 到 inputs 映射
                    if "LoadWanVideoT5TextEncoder" in node_type:
                        if len(widgets_values) >= 1 and "model_name" not in converted_inputs:
                            converted_inputs["model_name"] = widgets_values[0]
                        if len(widgets_values) >= 2 and "precision" not in converted_inputs:
                            converted_inputs["precision"] = widgets_values[1]
                        if len(widgets_values) >= 3 and "offload_device" not in converted_inputs:
                            converted_inputs["offload_device"] = widgets_values[2]
                        if len(widgets_values) >= 4 and "offload_mode" not in converted_inputs:
                            converted_inputs["offload_mode"] = widgets_values[3]
                    elif "WanVideoModelLoader" in node_type:
                        if len(widgets_values) >= 1 and "model" not in converted_inputs:
                            # 模型路径需要处理，去掉完整路径前缀
                            model_path = widgets_values[0]
                            if model_path.startswith("/ComfyUI/models/diffusion_models/"):
                                model_path = model_path.replace("/ComfyUI/models/diffusion_models/", "")
                            elif model_path.startswith("/ComfyUI/models/checkpoints/"):
                                model_path = model_path.replace("/ComfyUI/models/checkpoints/", "")
                            # 处理 Windows 路径分隔符
                            model_path = model_path.replace("\\", "/")
                            converted_inputs["model"] = model_path
                        if len(widgets_values) >= 2 and "base_precision" not in converted_inputs:
                            converted_inputs["base_precision"] = widgets_values[1]
                        if len(widgets_values) >= 3 and "load_device" not in converted_inputs:
                            converted_inputs["load_device"] = widgets_values[2]
                        if len(widgets_values) >= 4 and "offload_device" not in converted_inputs:
                            converted_inputs["offload_device"] = widgets_values[3]
                        if len(widgets_values) >= 5 and "quantization" not in converted_inputs:
                            converted_inputs["quantization"] = widgets_values[4]
                        if len(widgets_values) >= 6 and "attention_slicing" not in converted_inputs:
                            converted_inputs["attention_slicing"] = widgets_values[5]
                    elif "WanVideoVAELoader" in node_type:
                        if len(widgets_values) >= 1 and "model_name" not in converted_inputs:
                            converted_inputs["model_name"] = widgets_values[0]
                    elif "WanVideoTextEncode" in node_type:
                        if len(widgets_values) >= 1 and "positive_prompt" not in converted_inputs:
                            converted_inputs["positive_prompt"] = widgets_values[0]
                        if len(widgets_values) >= 2 and "negative_prompt" not in converted_inputs:
                            converted_inputs["negative_prompt"] = widgets_values[1]
                    elif "OnnxDetectionModelLoader" in node_type:
                        if len(widgets_values) >= 1 and "vitpose_model" not in converted_inputs:
                            converted_inputs["vitpose_model"] = widgets_values[0]
                        if len(widgets_values) >= 2 and "yolo_model" not in converted_inputs:
                            converted_inputs["yolo_model"] = widgets_values[1]
                        if len(widgets_values) >= 3 and "onnx_device" not in converted_inputs:
                            converted_inputs["onnx_device"] = widgets_values[2]
                    elif "WanVideoScheduler" in node_type:
                        # widgets: [scheduler, steps, start_step, end_step, shift]
                        if len(widgets_values) >= 1 and "scheduler" not in converted_inputs:
                            converted_inputs["scheduler"] = widgets_values[0]
                        if len(widgets_values) >= 2 and "steps" not in converted_inputs:
                            converted_inputs["steps"] = widgets_values[1]
                        if len(widgets_values) >= 3 and "start_step" not in converted_inputs:
                            converted_inputs["start_step"] = widgets_values[2]
                        if len(widgets_values) >= 4 and "end_step" not in converted_inputs:
                            converted_inputs["end_step"] = widgets_values[3]
                        if len(widgets_values) >= 5 and "shift" not in converted_inputs:
                            converted_inputs["shift"] = widgets_values[4]
                    elif "WanVideoSampler" in node_type:
                        if len(widgets_values) >= 1 and "steps" not in converted_inputs:
                            converted_inputs["steps"] = widgets_values[0]
                        if len(widgets_values) >= 2 and "seed" not in converted_inputs:
                            converted_inputs["seed"] = widgets_values[1]
                        if len(widgets_values) >= 3 and "cfg" not in converted_inputs:
                            converted_inputs["cfg"] = widgets_values[2]
                        if len(widgets_values) >= 7 and "sampler_name" not in converted_inputs:
                            converted_inputs["sampler_name"] = widgets_values[6]
                        if len(widgets_values) >= 8 and "shift" not in converted_inputs:
                            converted_inputs["shift"] = widgets_values[7]
                        if len(widgets_values) >= 9 and "riflex_freq_index" not in converted_inputs:
                            converted_inputs["riflex_freq_index"] = widgets_values[8]
                        if len(widgets_values) >= 10 and "force_offload" not in converted_inputs:
                            converted_inputs["force_offload"] = widgets_values[9]
                    elif "WanVideoDecode" in node_type:
                        # widgets: [enable_vae_tiling, tile_x, tile_y, tile_stride_x, tile_stride_y, ...]
                        if len(widgets_values) >= 1 and "enable_vae_tiling" not in converted_inputs:
                            converted_inputs["enable_vae_tiling"] = widgets_values[0]
                        if len(widgets_values) >= 2 and "tile_x" not in converted_inputs:
                            converted_inputs["tile_x"] = widgets_values[1]
                        if len(widgets_values) >= 3 and "tile_y" not in converted_inputs:
                            converted_inputs["tile_y"] = widgets_values[2]
                        if len(widgets_values) >= 4 and "tile_stride_x" not in converted_inputs:
                            converted_inputs["tile_stride_x"] = widgets_values[3]
                        if len(widgets_values) >= 5 and "tile_stride_y" not in converted_inputs:
                            converted_inputs["tile_stride_y"] = widgets_values[4]
                    elif "WanVideoEncode" in node_type:
                        # widgets: [enable_vae_tiling, tile_x, tile_y, tile_stride_x, tile_stride_y, ...]
                        if len(widgets_values) >= 1 and "enable_vae_tiling" not in converted_inputs:
                            converted_inputs["enable_vae_tiling"] = widgets_values[0]
                        if len(widgets_values) >= 2 and "tile_x" not in converted_inputs:
                            converted_inputs["tile_x"] = widgets_values[1]
                        if len(widgets_values) >= 3 and "tile_y" not in converted_inputs:
                            converted_inputs["tile_y"] = widgets_values[2]
                        if len(widgets_values) >= 4 and "tile_stride_x" not in converted_inputs:
                            converted_inputs["tile_stride_x"] = widgets_values[3]
                        if len(widgets_values) >= 5 and "tile_stride_y" not in converted_inputs:
                            converted_inputs["tile_stride_y"] = widgets_values[4]
                
                # 处理字典格式的 widgets_values（如 VHS_VideoCombine）
                # 将 widgets_values 中的值添加到 inputs（如果 inputs 中还没有）
                if widgets_values_is_dict:
                    for widget_name, widget_value in widgets_values.items():
                        # 跳过特殊字段
                        if widget_name not in ["videopreview"] and widget_name not in converted_inputs:
                            if widget_value is not None:
                                converted_inputs[widget_name] = widget_value
                
                converted_node["inputs"] = converted_inputs
            else:
                converted_node[key] = value
        
        # 设置class_type，同时更新type字段
        if "type" in converted_node:
            node_type = converted_node["type"]
            final_class_type = None
            
            # 处理 UUID 类型的节点（通常是子图节点）
            # 尝试从 workflow 的 definitions/subgraphs 中查找实际的节点类型
            if len(node_type) == 36 and node_type.count('-') == 4:  # UUID 格式
                # 查找子图定义
                subgraph_type = None
                if "definitions" in workflow_data and "subgraphs" in workflow_data["definitions"]:
                    for subgraph in workflow_data["definitions"]["subgraphs"]:
                        if subgraph.get("id") == node_type:
                            # 检查子图内部节点，查找主要的节点类型
                            if "state" in subgraph and "nodes" in subgraph["state"]:
                                for sub_node in subgraph["state"]["nodes"]:
                                    sub_node_type = sub_node.get("type", "")
                                    # 优先查找 WanVideoAddOneToAllExtendEmbeds
                                    if "WanVideoAddOneToAllExtendEmbeds" in str(sub_node_type):
                                        subgraph_type = "WanVideoAddOneToAllExtendEmbeds"
                                        break
                                    # 或者查找其他常见的扩展节点
                                    elif "Extend" in str(sub_node_type) and subgraph_type is None:
                                        subgraph_type = sub_node_type
                            break
                
                if subgraph_type:
                    final_class_type = subgraph_type
                    print(f"节点 {node_id}: 将子图 UUID {node_type} 替换为 {subgraph_type}")
                else:
                    # 如果找不到，根据节点标题推断
                    node_title = converted_node.get("title", "").lower()
                    if "extend" in node_title:
                        final_class_type = "WanVideoAddOneToAllExtendEmbeds"
                        print(f"节点 {node_id}: 根据标题 '{node_title}' 推断为 WanVideoAddOneToAllExtendEmbeds")
                    else:
                        # 保持原样（可能会失败，但至少不会破坏结构）
                        final_class_type = node_type
                        print(f"警告: 节点 {node_id}: 无法解析子图 UUID {node_type}，保持原样")
            elif "GetNode" in str(node_type):
                final_class_type = getnode_class_name if "|" not in str(node_type) else node_type
            elif "|" in node_type:
                final_class_type = node_type
            else:
                final_class_type = node_type
            
            # 同时更新 type 和 class_type
            if final_class_type:
                converted_node["class_type"] = final_class_type
                # 如果是 UUID 被替换，也更新 type 字段
                if len(node_type) == 36 and node_type.count('-') == 4 and final_class_type != node_type:
                    converted_node["type"] = final_class_type
        
        if "inputs" not in converted_node:
            converted_node["inputs"] = {}
        
        prompt[node_id] = converted_node
    
    return prompt


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_workflow_to_api.py <input_workflow.json> [output_workflow.json]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".json", "_api.json")
    
    print(f"Reading workflow from: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        workflow_data = json.load(f)
    
    print("Converting workflow format...")
    # 转换格式
    if "nodes" in workflow_data:
        prompt = convert_nodes_to_prompt_format(workflow_data, {}, get_getnode_class_name())
        
        # 创建 API 格式的 workflow
        api_workflow = prompt
        
        print(f"Converted {len(prompt)} nodes")
        print(f"Writing API format workflow to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(api_workflow, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Successfully converted workflow to API format")
        print(f"  Input nodes: {len(workflow_data.get('nodes', []))}")
        print(f"  Output nodes: {len(prompt)}")
    else:
        print("Workflow is already in API format (no 'nodes' array found)")
        # 如果已经是 API 格式，直接复制
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(workflow_data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()

