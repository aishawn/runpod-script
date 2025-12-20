import runpod
from runpod.serverless.utils import rp_upload
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.parse
import binascii
import subprocess
import time

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_address = os.getenv('SERVER_ADDRESS', '127.0.0.1')
client_id = str(uuid.uuid4())

# ==================== 工具函数 ====================

def to_nearest_multiple_of_16(value):
    """将值调整为最接近的16的倍数，最小16"""
    try:
        numeric_value = float(value)
    except Exception:
        raise Exception(f"width/height值不是数字: {value}")
    adjusted = int(round(numeric_value / 16.0) * 16)
    return max(adjusted, 16)

def should_skip_node(node_type):
    """检查节点类型是否应该被跳过"""
    if not node_type:
        return False
    node_type_str = str(node_type)
    skip_types = ["Note", "GetNode", "SetNode", "PrimitiveNode"]
    return any(node_type_str == t or node_type_str.startswith(t) for t in skip_types)

# ==================== Widgets 映射配置 ====================

# 节点类型到 widgets_values 索引映射的配置
WIDGETS_MAPPING = {
    "WanVideoTextEncodeCached": {
        "model_name": 0, "precision": 1, "positive_prompt": 2, 
        "negative_prompt": 3, "quantization": 4, "use_disk_cache": 5, "device": 6
    },
    "WanVideoSamplerSettings": {
        "shift": 7, "force_offload": 8, "riflex_freq_index": 9
    },
    "WanVideoModelLoader": {
        "base_precision": 1, "quantization": 2, "load_device": 3
    },
    "WanVideoLoraSelect": {
        "lora": 0, "strength": 1
    },
    "WanVideoImageToVideoEncode": {
        "start_latent_strength": 3, "end_latent_strength": 4,
        "noise_aug_strength": 5, "force_offload": 6
    },
    "WanVideoAddSteadyDancerEmbeds": {
        "pose_strength_spatial": 0, "pose_strength_temporal": 1,
        "start_percent": 2, "end_percent": 3
    },
    "WanVideoBlockSwap": {
        "blocks_to_swap": 0, "offload_txt_emb": 1, "offload_img_emb": 2
    },
    "WanVideoTorchCompileSettings": {
        "backend": 0, "compile_transformer_blocks_only": 1, "mode": 2,
        "fullgraph": 3, "dynamo_cache_size_limit": 4, "dynamic": 5
    },
    "ImageConcatMulti": {
        "inputcount": 0, "direction": 1, "match_image_size": 2
    },
    "WanVideoDecode": {
        "enable_vae_tiling": 0, "tile_x": 1, "tile_y": 2,
        "tile_stride_x": 3, "tile_stride_y": 4
    },
    "WanVideoEncode": {
        "enable_vae_tiling": 0, "tile_x": 1, "tile_y": 2,
        "tile_stride_x": 3, "tile_stride_y": 4
    },
    "WanVideoContextOptions": {
        "context_schedule": 0, "context_frames": 1, "context_overlap": 2,
        "context_stride": 3, "freenoise": 4, "verbose": 5
    },
    "GetImageRangeFromBatch": {
        "start_index": 0, "num_frames": 1
    },
    "OnnxDetectionModelLoader": {
        "vitpose_model": (0, lambda v: v.replace("\\", "/")),
        "yolo_model": (1, lambda v: v.replace("\\", "/")),
        "onnx_device": 2
    },
    "WanVideoVAELoader": {
        "model_name": (0, lambda v: v.replace("\\", "/")),
        "load_precision": 1
    },
    "CLIPVisionLoader": {
        "clip_name": 0
    },
    "DrawViTPose": {
        "retarget_padding": 2, "hand_stick_width": 3,
        "body_stick_width": 4, "draw_head": 5
    },
    "ImageResizeKJv2": {
        "upscale_method": 2, "keep_proportion": 3, "pad_color": 4,
        "crop_position": 5, "divisible_by": 6
    },
    "WanVideoClipVisionEncode": {
        "strength_1": 0, "strength_2": 1, "crop": 2,
        "combine_embeds": 3, "force_offload": 4
    }
}

def supplement_node_inputs_from_widgets(node_id, node_data, widgets_values):
    """根据 widgets_values 补充节点的 inputs（简化版）"""
    if not isinstance(widgets_values, list) or len(widgets_values) == 0:
        return
    
    class_type = node_data.get("class_type") or node_data.get("type", "")
    inputs = node_data.get("inputs", {})
    mapping = WIDGETS_MAPPING.get(class_type)
    
    if not mapping:
        return
    
    for input_name, index_or_tuple in mapping.items():
        if input_name in inputs:
            continue
        
        if isinstance(index_or_tuple, tuple):
            index, transform = index_or_tuple
        else:
            index, transform = index_or_tuple, None
        
        if index < len(widgets_values) and widgets_values[index] is not None:
            value = widgets_values[index]
            if transform:
                value = transform(value)
            inputs[input_name] = value

# ==================== 输入处理 ====================

def process_input(input_data, temp_dir, output_filename, input_type):
    """处理输入数据并返回文件路径（绝对路径）"""
    if input_type == "path":
        logger.info(f"📁 路径输入: {input_data}")
        # 如果是绝对路径，直接返回；如果是相对路径，转换为绝对路径
        if os.path.isabs(input_data):
            return input_data
        else:
            # 相对路径，假设相对于 /ComfyUI/input/
            return os.path.abspath(os.path.join("/ComfyUI/input", input_data))
    elif input_type == "url":
        logger.info(f"🌐 URL输入: {input_data}")
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        return download_file_from_url(input_data, file_path)
    elif input_type == "base64":
        logger.info(f"🔢 Base64输入")
        return save_base64_to_file(input_data, temp_dir, output_filename)
    else:
        raise Exception(f"不支持的输入类型: {input_type}")

def download_file_from_url(url, output_path):
    """从URL下载文件"""
    try:
        result = subprocess.run(
            ['wget', '-O', output_path, '--no-verbose', url],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            logger.info(f"✅ 下载成功: {url} -> {output_path}")
            return output_path
        else:
            raise Exception(f"URL下载失败: {result.stderr}")
    except Exception as e:
        logger.error(f"❌ 下载错误: {e}")
        raise

def save_base64_to_file(base64_data, temp_dir, output_filename):
    """将Base64数据保存为文件"""
    try:
        decoded_data = base64.b64decode(base64_data)
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        with open(file_path, 'wb') as f:
            f.write(decoded_data)
        logger.info(f"✅ Base64已保存: {file_path}")
        return file_path
    except (binascii.Error, ValueError) as e:
        logger.error(f"❌ Base64解码失败: {e}")
        raise Exception(f"Base64解码失败: {e}")

# ==================== ComfyUI API 通信 ====================

def queue_prompt(prompt):
    """提交prompt到ComfyUI"""
    url = f"http://{server_address}:8188/prompt"
    data = json.dumps({"prompt": prompt, "client_id": client_id}).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    req.add_header('Content-Type', 'application/json')
    try:
        response = urllib.request.urlopen(req)
        return json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"HTTP错误 {e.code}: {error_body}")
        raise Exception(f"ComfyUI API错误 ({e.code}): {error_body}")

def get_image(filename, subfolder, folder_type):
    """从ComfyUI获取图像"""
    url = f"http://{server_address}:8188/view"
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen(f"{url}?{url_values}") as response:
        return response.read()

def get_history(prompt_id):
    """获取执行历史"""
    url = f"http://{server_address}:8188/history/{prompt_id}"
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())

def get_videos(ws, prompt):
    """获取生成的视频"""
    prompt_id = queue_prompt(prompt)['prompt_id']
    output_videos = {}
    error_info = None
    
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break
            elif message['type'] == 'execution_error':
                error_data = message.get('data', {})
                error_info = error_data.get('error', 'Unknown execution error')
                node_id = error_data.get('node_id', '')
                
                if 'OutOfMemoryError' in str(error_info) or 'OOM' in str(error_info):
                    logger.error(f"❌ GPU内存不足 (OOM) - 节点: {node_id}")
                    logger.error("建议: 1) 减小分辨率 2) 减少帧数 3) 缩短提示词")
                else:
                    logger.error(f"执行错误 - 节点: {node_id}, 错误: {error_info}")

    history = get_history(prompt_id)[prompt_id]
    
    if 'error' in history:
        error_info = history['error']
        if isinstance(error_info, dict):
            error_info = error_info.get('message', str(error_info))
        
        error_str = str(error_info)
        if 'OutOfMemoryError' in error_str or 'OOM' in error_str or 'allocation' in error_str.lower():
            logger.error(f"❌ GPU内存不足 (OOM): {error_info}")
            raise Exception(f"GPU内存不足: {error_info}. 请尝试减小分辨率、帧数或提示词长度。")
        else:
            raise Exception(f"ComfyUI执行错误: {error_info}")
    
    if 'outputs' not in history:
        raise Exception("执行历史中未找到输出")
    
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        videos_output = []
        video_list = node_output.get('gifs') or node_output.get('videos')
        
        if video_list:
            for video in video_list:
                if 'fullpath' in video:
                    with open(video['fullpath'], 'rb') as f:
                        video_data = base64.b64encode(f.read()).decode('utf-8')
                    videos_output.append(video_data)
                elif 'filename' in video:
                    try:
                        video_bytes = get_image(
                            video['filename'],
                            video.get('subfolder', ''),
                            video.get('type', 'output')
                        )
                        video_data = base64.b64encode(video_bytes).decode('utf-8')
                        videos_output.append(video_data)
                    except Exception as e:
                        logger.warning(f"无法读取视频文件 {video['filename']}: {e}")
        output_videos[node_id] = videos_output

    return output_videos

# ==================== Workflow 处理 ====================

def load_workflow(workflow_path):
    """加载并验证工作流JSON文件"""
    if not os.path.exists(workflow_path):
        raise FileNotFoundError(f"工作流文件不存在: {workflow_path}")
    
    file_size = os.path.getsize(workflow_path)
    logger.info(f"加载工作流: {workflow_path} (大小: {file_size} 字节)")
    
    if file_size == 0:
        raise ValueError(f"工作流文件为空: {workflow_path}")
    
    try:
        with open(workflow_path, 'r', encoding='utf-8') as file:
            content = file.read().strip()
            if not content.startswith(('{', '[')):
                raise ValueError(f"工作流文件不是有效的JSON格式: {workflow_path}")
            return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误 (行 {e.lineno}): {str(e)}")
        raise ValueError(f"工作流文件JSON格式错误: {workflow_path} - {str(e)}")
    except Exception as e:
        logger.error(f"加载工作流文件时发生错误: {workflow_path} - {str(e)}")
        raise

def convert_workflow_nodes_to_prompt(workflow_data):
    """将 nodes 数组格式转换为节点 ID key 格式（支持 SetNode/GetNode 解析）"""
    if "nodes" not in workflow_data:
        return workflow_data
    
    prompt = {}
    valid_node_ids = set()
    all_nodes_map = {}
    
    # 收集所有节点
    for node in workflow_data["nodes"]:
        node_id = str(node["id"]).lstrip('#')
        all_nodes_map[node_id] = node
        if not should_skip_node(node.get("type", "")):
            valid_node_ids.add(node_id)
    
    # 建立 SetNode 映射（解析 SetNode 到源节点的关系）
    setnode_source_map = {}
    def resolve_setnode_source(setnode_node_id, visited=None):
        """递归解析 SetNode 的源节点"""
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
                            source_node_id = str(link[1]).lstrip('#')
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
    
    # 建立 SetNode 名称到源节点的映射
    for node_id, node in all_nodes_map.items():
        if node.get("type") == "SetNode":
            widgets = node.get("widgets_values", [])
            if widgets and isinstance(widgets, list):
                setnode_name = widgets[0]
                resolved_source = resolve_setnode_source(node_id)
                if resolved_source:
                    setnode_source_map[setnode_name] = resolved_source
    
    # 建立 links 映射（支持 SetNode/GetNode 解析）
    links_map = {}
    if "links" in workflow_data:
        for link in workflow_data["links"]:
            if len(link) >= 6:
                link_id = link[0]
                source_node_id = str(link[1]).lstrip('#')
                source_output_index = link[2]
                target_node_id = str(link[3]).lstrip('#')
                
                source_node = all_nodes_map.get(source_node_id)
                
                # 处理 SetNode 输出链接：解析到 SetNode 的源节点
                if source_node and source_node.get("type") == "SetNode":
                    resolved_source = resolve_setnode_source(source_node_id)
                    if resolved_source:
                        source_node_id, source_output_index = resolved_source
                        logger.debug(f"Link {link_id}: SetNode 解析到源节点 {source_node_id}[{source_output_index}]")
                
                # 处理 GetNode 输入链接：解析到对应的 SetNode 源节点
                if source_node and source_node.get("type") == "GetNode":
                    widgets = source_node.get("widgets_values", [])
                    if widgets and isinstance(widgets, list):
                        getnode_name = widgets[0]
                        if getnode_name in setnode_source_map:
                            resolved_source = setnode_source_map[getnode_name]
                            if resolved_source:
                                source_node_id, source_output_index = resolved_source
                                logger.debug(f"Link {link_id}: GetNode {getnode_name} 解析到源节点 {source_node_id}[{source_output_index}]")
                
                # 只添加有效的链接（源节点和目标节点都在有效节点列表中）
                if source_node_id in valid_node_ids and target_node_id in valid_node_ids:
                    links_map[link_id] = [source_node_id, source_output_index]
                elif source_node_id not in valid_node_ids:
                    logger.debug(f"Link {link_id}: 源节点 {source_node_id} 不在有效节点列表中，跳过")
                elif target_node_id not in valid_node_ids:
                    logger.debug(f"Link {link_id}: 目标节点 {target_node_id} 不在有效节点列表中，跳过")
    
    # 转换节点
    for node in workflow_data["nodes"]:
        node_id = str(node["id"]).lstrip('#')
        if should_skip_node(node.get("type", "")):
            continue
        
        converted_node = {}
        widgets_values = node.get("widgets_values", [])
        widgets_values_is_dict = isinstance(widgets_values, dict)
        
        # 转换 inputs
        converted_inputs = {}
        inputs = node.get("inputs", [])
        
        if isinstance(inputs, list):
            widget_index = 0
            for input_item in inputs:
                if not isinstance(input_item, dict) or "name" not in input_item:
                    continue
                
                input_name = input_item["name"]
                has_widget = "widget" in input_item
                has_link = "link" in input_item and input_item["link"] is not None
                
                if has_link:
                    link_id = input_item["link"]
                    if link_id in links_map:
                        converted_inputs[input_name] = links_map[link_id]
                    elif has_widget:
                        # 使用 widget 值作为备用
                        widget_value = None
                        if widgets_values_is_dict:
                            widget_value = widgets_values.get(input_name)
                        elif widget_index < len(widgets_values):
                            widget_value = widgets_values[widget_index]
                        
                        if widget_value is not None:
                            converted_inputs[input_name] = widget_value
                    
                    if not widgets_values_is_dict and has_widget:
                        widget_index += 1
                else:
                    if "value" in input_item:
                        converted_inputs[input_name] = input_item["value"]
                    elif has_widget:
                        widget_value = None
                        if widgets_values_is_dict:
                            widget_value = widgets_values.get(input_name)
                        elif widget_index < len(widgets_values):
                            widget_value = widgets_values[widget_index]
                            widget_index += 1
                        
                        if widget_value is not None:
                            converted_inputs[input_name] = widget_value
        elif isinstance(inputs, dict):
            converted_inputs = inputs.copy()
        
        # 处理字典格式的 widgets_values
        if widgets_values_is_dict:
            for widget_name, widget_value in widgets_values.items():
                if widget_name not in ["videopreview"] and widget_name not in converted_inputs:
                    if widget_value is not None:
                        converted_inputs[widget_name] = widget_value
        
        converted_node["inputs"] = converted_inputs
        
        # 复制其他字段
        for key, value in node.items():
            if key not in ["id", "inputs"]:
                converted_node[key] = value
        
        # 设置 class_type
        if "type" in converted_node:
            converted_node["class_type"] = converted_node["type"]
        elif "class_type" not in converted_node:
            logger.warning(f"节点 {node_id} 缺少 type 和 class_type 字段")
        
        # 补充缺失的 inputs
        if not widgets_values_is_dict and isinstance(widgets_values, list) and len(widgets_values) > 0:
            supplement_node_inputs_from_widgets(node_id, converted_node, widgets_values)
        
        prompt[node_id] = converted_node
    
    # 验证并清理无效引用
    nodes_to_remove = []
    for node_id, node_data in prompt.items():
        if should_skip_node(node_data.get("type") or node_data.get("class_type", "")):
            nodes_to_remove.append(node_id)
            continue
        
        inputs = node_data.get("inputs", {})
        inputs_to_remove = []
        for input_name, input_value in inputs.items():
            if isinstance(input_value, list) and len(input_value) >= 2:
                referenced_node_id = str(input_value[0]).lstrip('#')
                if referenced_node_id not in valid_node_ids:
                    inputs_to_remove.append(input_name)
        
        for input_name in inputs_to_remove:
            del inputs[input_name]
    
    for node_id in nodes_to_remove:
        del prompt[node_id]
    
    logger.info(f"已转换工作流，共 {len(prompt)} 个有效节点")
    return prompt

# ==================== 自动填充缺失输入 ====================

def fill_missing_inputs_from_widgets(node_id, node):
    """从 widgets_values 填充缺失的 inputs"""
    class_type = node.get("class_type", "")
    if "inputs" not in node:
        node["inputs"] = {}
    
    # 处理字典格式的 widgets_values（如 VHS_VideoCombine）
    if "widgets_values" in node and isinstance(node["widgets_values"], dict):
        widgets = node["widgets_values"]
        for key, value in widgets.items():
            if key not in ["videopreview"] and key not in node["inputs"]:
                node["inputs"][key] = value
        return
    
    # 处理列表格式的 widgets_values
    if "widgets_values" not in node:
        return
    
    widgets = node["widgets_values"]
    if not isinstance(widgets, list) or len(widgets) == 0:
        return
    
    # 根据节点类型填充缺失的输入（只处理 SteadyDancer 需要的节点类型）
    if "WanVideoSamplerSettings" in class_type:
        # widgets: [steps, shift, riflex_freq_index, seed, sampler_name, cfg, scheduler, ...]
        if len(widgets) >= 1 and "steps" not in node["inputs"]:
            node["inputs"]["steps"] = widgets[0]
        if len(widgets) >= 2 and "shift" not in node["inputs"]:
            shift_value = widgets[1] if isinstance(widgets[1], (int, float)) else 0.0
            if shift_value < 0:
                shift_value = 0.0
            node["inputs"]["shift"] = shift_value
        if len(widgets) >= 3 and "riflex_freq_index" not in node["inputs"]:
            node["inputs"]["riflex_freq_index"] = widgets[2] if isinstance(widgets[2], (int, float)) else 0
        if len(widgets) >= 4 and "seed" not in node["inputs"]:
            node["inputs"]["seed"] = widgets[3]
        if len(widgets) >= 5 and "sampler_name" not in node["inputs"]:
            node["inputs"]["sampler_name"] = widgets[4]
        if len(widgets) >= 6 and "cfg" not in node["inputs"]:
            node["inputs"]["cfg"] = widgets[5]
        if len(widgets) >= 7 and "scheduler" not in node["inputs"]:
            node["inputs"]["scheduler"] = widgets[6]
        if len(widgets) >= 8 and "force_offload" not in node["inputs"]:
            node["inputs"]["force_offload"] = widgets[7] if isinstance(widgets[7], bool) else False
    
    elif "WanVideoAddSteadyDancerEmbeds" in class_type:
        # widgets: [pose_strength_spatial, pose_strength_temporal, start_percent, end_percent]
        if len(widgets) >= 1 and "pose_strength_spatial" not in node["inputs"]:
            node["inputs"]["pose_strength_spatial"] = widgets[0]
        if len(widgets) >= 2 and "pose_strength_temporal" not in node["inputs"]:
            node["inputs"]["pose_strength_temporal"] = widgets[1]
        if len(widgets) >= 3 and "start_percent" not in node["inputs"]:
            node["inputs"]["start_percent"] = widgets[2]
        if len(widgets) >= 4 and "end_percent" not in node["inputs"]:
            node["inputs"]["end_percent"] = widgets[3]
    
    elif "WanVideoImageToVideoEncode" in class_type:
        # widgets: [height, width, num_frames, start_latent_strength, end_latent_strength, noise_aug_strength, force_offload]
        if len(widgets) >= 1 and "height" not in node["inputs"]:
            node["inputs"]["height"] = widgets[0]
        if len(widgets) >= 2 and "width" not in node["inputs"]:
            node["inputs"]["width"] = widgets[1]
        if len(widgets) >= 3 and "num_frames" not in node["inputs"]:
            node["inputs"]["num_frames"] = widgets[2]
        if len(widgets) >= 4 and "start_latent_strength" not in node["inputs"]:
            node["inputs"]["start_latent_strength"] = widgets[3]
        if len(widgets) >= 5 and "end_latent_strength" not in node["inputs"]:
            node["inputs"]["end_latent_strength"] = widgets[4]
        if len(widgets) >= 6 and "noise_aug_strength" not in node["inputs"]:
            node["inputs"]["noise_aug_strength"] = widgets[5]
        if len(widgets) >= 7 and "force_offload" not in node["inputs"]:
            node["inputs"]["force_offload"] = widgets[6] if isinstance(widgets[6], bool) else False
    
    elif "WanVideoDecode" in class_type or "WanVideoEncode" in class_type:
        # widgets: [enable_vae_tiling, tile_x, tile_y, tile_stride_x, tile_stride_y, ...]
        if len(widgets) >= 1 and "enable_vae_tiling" not in node["inputs"]:
            node["inputs"]["enable_vae_tiling"] = widgets[0] if isinstance(widgets[0], bool) else False
        if len(widgets) >= 2 and "tile_x" not in node["inputs"]:
            node["inputs"]["tile_x"] = widgets[1]
        if len(widgets) >= 3 and "tile_y" not in node["inputs"]:
            node["inputs"]["tile_y"] = widgets[2]
        if len(widgets) >= 4 and "tile_stride_x" not in node["inputs"]:
            node["inputs"]["tile_stride_x"] = widgets[3]
        if len(widgets) >= 5 and "tile_stride_y" not in node["inputs"]:
            node["inputs"]["tile_stride_y"] = widgets[4]
    
    elif "WanVideoLoraSelect" in class_type:
        # widgets: [lora, strength, ...]
        if len(widgets) >= 1 and "lora" not in node["inputs"]:
            lora_path = widgets[0]
            if isinstance(lora_path, str) and lora_path:
                lora_path = lora_path.replace("\\", "/")
                if lora_path.startswith("ComfyUI/models/loras/"):
                    lora_path = lora_path.replace("ComfyUI/models/loras/", "")
                elif lora_path.startswith("/ComfyUI/models/loras/"):
                    lora_path = lora_path.replace("/ComfyUI/models/loras/", "")
                if "/" in lora_path and not lora_path.startswith("WanVideo/"):
                    lora_path = "WanVideo/" + lora_path
            node["inputs"]["lora"] = lora_path
        if len(widgets) >= 2 and "strength" not in node["inputs"]:
            node["inputs"]["strength"] = widgets[1]
    
    elif "WanVideoBlockSwap" in class_type:
        # widgets: [blocks_to_swap, offload_txt_emb, offload_img_emb, ...]
        if len(widgets) >= 1 and "blocks_to_swap" not in node["inputs"]:
            node["inputs"]["blocks_to_swap"] = widgets[0]
        if len(widgets) >= 2 and "offload_txt_emb" not in node["inputs"]:
            node["inputs"]["offload_txt_emb"] = widgets[1]
        if len(widgets) >= 3 and "offload_img_emb" not in node["inputs"]:
            node["inputs"]["offload_img_emb"] = widgets[2]
    
    elif "WanVideoContextOptions" in class_type:
        # widgets: [context_schedule, context_frames, context_overlap, context_stride, freenoise, verbose]
        if len(widgets) >= 1 and "context_schedule" not in node["inputs"]:
            node["inputs"]["context_schedule"] = widgets[0]
        if len(widgets) >= 2 and "context_frames" not in node["inputs"]:
            node["inputs"]["context_frames"] = widgets[1]
        if len(widgets) >= 3 and "context_overlap" not in node["inputs"]:
            node["inputs"]["context_overlap"] = widgets[2]
        if len(widgets) >= 4 and "context_stride" not in node["inputs"]:
            node["inputs"]["context_stride"] = widgets[3]
        if len(widgets) >= 5 and "freenoise" not in node["inputs"]:
            node["inputs"]["freenoise"] = widgets[4] if isinstance(widgets[4], bool) else True
        if len(widgets) >= 6 and "verbose" not in node["inputs"]:
            node["inputs"]["verbose"] = widgets[5] if isinstance(widgets[5], bool) else False
    
    elif "WanVideoClipVisionEncode" in class_type:
        # widgets: [strength_1, strength_2, crop, combine_embeds, force_offload, ...]
        if len(widgets) >= 1 and "strength_1" not in node["inputs"]:
            node["inputs"]["strength_1"] = widgets[0]
        if len(widgets) >= 2 and "strength_2" not in node["inputs"]:
            node["inputs"]["strength_2"] = widgets[1]
        if len(widgets) >= 3 and "crop" not in node["inputs"]:
            node["inputs"]["crop"] = widgets[2]
        if len(widgets) >= 4 and "combine_embeds" not in node["inputs"]:
            node["inputs"]["combine_embeds"] = widgets[3]
        if len(widgets) >= 5 and "force_offload" not in node["inputs"]:
            node["inputs"]["force_offload"] = widgets[4] if isinstance(widgets[4], bool) else True

# ==================== 节点配置 ====================

def configure_node(prompt, node_id, updates):
    """通用节点配置函数"""
    if node_id not in prompt:
        return
    
    if "inputs" not in prompt[node_id]:
        prompt[node_id]["inputs"] = {}
    
    # 更新 widgets_values（列表格式）
    if "widgets_list" in updates and "widgets_values" in prompt[node_id]:
        widgets = prompt[node_id]["widgets_values"]
        if isinstance(widgets, list):
            for key, (index, value) in updates["widgets_list"].items():
                while len(widgets) <= index:
                    widgets.append(None)
                widgets[index] = value
    
    # 更新 widgets_values（字典格式）
    if "widgets_dict" in updates and "widgets_values" in prompt[node_id]:
        widgets = prompt[node_id]["widgets_values"]
        if isinstance(widgets, dict):
            for key, value in updates["widgets_dict"].items():
                widgets[key] = value
    
    # 更新 inputs
    for key, value in updates.get("inputs", {}).items():
        prompt[node_id]["inputs"][key] = value

def configure_steadydancer_nodes(prompt, job_input, task_id, image_path, adjusted_width, adjusted_height, length, 
                                 positive_prompt, negative_prompt, steps, seed, cfg, scheduler, sampler_name):
    """配置 SteadyDancer 工作流的所有节点"""
    logger.info("配置 SteadyDancer 工作流节点")
    
    # 节点76: LoadImage
    if "76" in prompt:
        # 使用绝对路径（ComfyUI 期望相对于 /ComfyUI/input/ 的路径或绝对路径）
        # image_path 已经是绝对路径，但需要转换为相对于 /ComfyUI/input/ 的路径
        if image_path and image_path.startswith("/ComfyUI/input/"):
            image_relative_path = image_path.replace("/ComfyUI/input/", "")
        else:
            image_relative_path = f"{task_id}/input_image.jpg"
        configure_node(prompt, "76", {
            "widgets_list": {"image": (0, image_relative_path)},
            "inputs": {"image": image_relative_path}
        })
        logger.info(f"节点76 (参考图像): {image_relative_path}")
    
    # 节点75: VHS_LoadVideo (可选)
    reference_video_path = None
    for key in ["reference_video_path", "reference_video_url", "reference_video_base64", "video_base64"]:
        if key in job_input:
            task_input_dir = os.path.join("/ComfyUI/input", task_id)
            reference_video_path = process_input(
                job_input[key], task_input_dir, "reference_video.mp4",
                "path" if "path" in key else ("url" if "url" in key else "base64")
            )
            break
    
    if reference_video_path and "75" in prompt:
        # 使用绝对路径（ComfyUI 期望相对于 /ComfyUI/input/ 的路径或绝对路径）
        if reference_video_path.startswith("/ComfyUI/input/"):
            video_relative_path = reference_video_path.replace("/ComfyUI/input/", "")
        else:
            video_relative_path = f"{task_id}/reference_video.mp4"
        configure_node(prompt, "75", {
            "widgets_dict": {"video": video_relative_path},
            "inputs": {"video": video_relative_path}
        })
        logger.info(f"节点75 (参考视频): {video_relative_path}")
    elif "75" in prompt:
        # 移除节点75的依赖
        for nid, ndata in list(prompt.items()):
            if "inputs" in ndata:
                for input_name, input_value in list(ndata["inputs"].items()):
                    if isinstance(input_value, list) and len(input_value) >= 1 and str(input_value[0]) == "75":
                        del ndata["inputs"][input_name]
        if "75" in prompt:
            del prompt["75"]
        logger.info("已移除节点75 (未提供参考视频)")
    
    # 节点22: WanVideoModelLoader
    if "22" in prompt:
        steadydancer_model = "WanVideo/SteadyDancer/Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors"
        configure_node(prompt, "22", {
            "widgets_list": {"model": (0, steadydancer_model)},
            "inputs": {"model": steadydancer_model}
        })
        logger.info(f"节点22 (SteadyDancer模型): {steadydancer_model}")
    
    # 节点90: OnnxDetectionModelLoader
    if "90" in prompt:
        configure_node(prompt, "90", {
            "widgets_list": {
                "vitpose_model": (0, "vitpose_h_wholebody_model.onnx"),
                "yolo_model": (1, "yolov10m.onnx")
            },
            "inputs": {
                "vitpose_model": "vitpose_h_wholebody_model.onnx",
                "yolo_model": "yolov10m.onnx",
                "onnx_device": "CUDAExecutionProvider"
            }
        })
        logger.info(f"节点90 (姿态检测模型): 已配置")
    
    # 节点92: WanVideoTextEncodeCached
    if "92" in prompt:
        configure_node(prompt, "92", {
            "widgets_list": {
                "model_name": (0, "umt5-xxl-enc-bf16.safetensors"),
                "positive_prompt": (2, positive_prompt),
                "negative_prompt": (3, negative_prompt)
            },
            "inputs": {
                "text": positive_prompt,
                "negative_text": negative_prompt
            }
        })
        logger.info(f"节点92 (文本编码): {positive_prompt[:50]}...")
    
    # 节点69: WanVideoLoraSelect
    if "69" in prompt:
        lora_path = "WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
        strength = 1.0
        if "widgets_values" in prompt["69"] and len(prompt["69"]["widgets_values"]) > 1:
            strength = prompt["69"]["widgets_values"][1]
        configure_node(prompt, "69", {
            "widgets_list": {"lora": (0, lora_path)},
            "inputs": {"lora": lora_path, "strength": strength}
        })
        logger.info(f"节点69 (LoRA): {lora_path}")
    
    # 节点63: WanVideoImageToVideoEncode
    if "63" in prompt:
        configure_node(prompt, "63", {
            "widgets_list": {
                "height": (0, adjusted_height),
                "width": (1, adjusted_width),
                "num_frames": (2, length)
            },
            "inputs": {
                "width": adjusted_width,
                "height": adjusted_height,
                "num_frames": length
            }
        })
        logger.info(f"节点63 (图像到视频编码): {adjusted_width}x{adjusted_height}, {length}帧")
    
    # 节点119: WanVideoSamplerSettings
    if "119" in prompt:
        widgets = prompt["119"].get("widgets_values", [])
        while len(widgets) < 7:
            widgets.append(None)
        widgets[0] = steps
        widgets[3] = seed
        widgets[4] = sampler_name
        widgets[6] = scheduler
        configure_node(prompt, "119", {
            "inputs": {
                "steps": steps,
                "seed": seed,
                "cfg": cfg,
                "scheduler": scheduler
            }
        })
        logger.info(f"节点119 (采样器设置): steps={steps}, seed={seed}, cfg={cfg}, scheduler={scheduler}")
    
    # 节点83: VHS_VideoCombine (输出)
    if "83" in prompt:
        configure_node(prompt, "83", {
            "widgets_dict": {
                "frame_rate": job_input.get("frame_rate", 24),
                "filename_prefix": job_input.get("filename_prefix", "WanVideoWrapper_SteadyDancer"),
                "format": "video/h264-mp4",
                "save_output": True,
                "loop_count": 0,
                "pingpong": False
            },
            "inputs": {
                "frame_rate": job_input.get("frame_rate", 24),
                "filename_prefix": job_input.get("filename_prefix", "WanVideoWrapper_SteadyDancer"),
                "format": "video/h264-mp4",
                "save_output": True,
                "loop_count": 0,
                "pingpong": False
            }
        })
        logger.info(f"节点83 (视频输出): 已配置")
    
    # 节点117: VHS_VideoCombine (中间输出)
    if "117" in prompt:
        configure_node(prompt, "117", {
            "widgets_dict": {
                "save_output": False,
                "loop_count": 0,
                "pingpong": False,
                "format": "video/h264-mp4",
                "frame_rate": 24
            },
            "inputs": {
                "save_output": False,
                "loop_count": 0,
                "pingpong": False,
                "format": "video/h264-mp4",
                "frame_rate": 24
            }
        })
        logger.info(f"节点117 (视频输出): 已配置")
    
    # 补充其他节点
    if "38" in prompt:
        configure_node(prompt, "38", {
            "inputs": {"model_name": "Wan2_1_VAE_bf16.safetensors"}
        })
    
    if "59" in prompt and "widgets_values" in prompt["59"]:
        widgets = prompt["59"]["widgets_values"]
        if isinstance(widgets, list) and len(widgets) > 0:
            configure_node(prompt, "59", {
                "inputs": {"clip_name": widgets[0]}
            })
    
    logger.info("SteadyDancer 工作流节点配置完成")

# ==================== 连接管理 ====================

def wait_for_http_connection(max_attempts=180):
    """等待HTTP连接"""
    http_url = f"http://{server_address}:8188/"
    logger.info(f"检查HTTP连接: {http_url}")
    
    for attempt in range(max_attempts):
        try:
            urllib.request.urlopen(http_url, timeout=5)
            logger.info(f"HTTP连接成功 (尝试 {attempt+1})")
            return
        except Exception as e:
            if attempt == max_attempts - 1:
                raise Exception("无法连接到ComfyUI服务器")
            time.sleep(1)

def connect_websocket(max_attempts=36):
    """连接WebSocket"""
    ws_url = f"ws://{server_address}:8188/ws?clientId={client_id}"
    logger.info(f"连接WebSocket: {ws_url}")
    
    ws = websocket.WebSocket()
    for attempt in range(max_attempts):
        try:
            ws.connect(ws_url)
            logger.info(f"WebSocket连接成功 (尝试 {attempt+1})")
            return ws
        except Exception as e:
            if attempt == max_attempts - 1:
                raise Exception("WebSocket连接超时 (3分钟)")
            time.sleep(5)

# ==================== 主处理函数 ====================

def handler(job):
    """处理 SteadyDancer 视频生成任务"""
    job_input = job.get("input", {})
    
    # 记录输入（排除base64数据）
    log_input = {k: v for k, v in job_input.items() 
                 if k not in ["image_base64", "end_image_base64", "video_base64", "reference_video_base64"]}
    for key in ["image_base64", "end_image_base64", "video_base64", "reference_video_base64"]:
        if key in job_input:
            log_input[key] = f"<base64 data, length: {len(job_input[key])}>"
    logger.info(f"收到任务输入: {log_input}")
    
    task_id = f"task_{uuid.uuid4()}"
    comfyui_input_dir = "/ComfyUI/input"
    task_input_dir = os.path.join(comfyui_input_dir, task_id)
    os.makedirs(task_input_dir, exist_ok=True)
    
    # 处理图像输入
    image_path = None
    for key in ["image_path", "image_url", "image_base64"]:
        if key in job_input:
            image_path = process_input(
                job_input[key], task_input_dir, "input_image.jpg",
                "path" if "path" in key else ("url" if "url" in key else "base64")
            )
            break
    
    if not image_path:
        image_path = "/example_image.png"
        logger.info("使用默认图像: /example_image.png")
    
    # 加载工作流
    workflow_file = "/wanvideo_SteadyDancer_example_01.json"
    workflow_data = load_workflow(workflow_file)
    
    # 转换工作流格式
    prompt = convert_workflow_nodes_to_prompt(workflow_data)
    
    # 获取参数
    length = job_input.get("length", 81)
    steps = job_input.get("steps", 4)
    seed = job_input.get("seed", 42)
    cfg = job_input.get("cfg", 1.0)
    scheduler = job_input.get("scheduler", "dpm++_sde")
    sampler_name = job_input.get("sampler", "fixed")
    
    # 处理提示词
    prompt_input = job_input.get("prompt", "running man, grab the gun")
    if isinstance(prompt_input, list):
        positive_prompt = "\n".join(str(p) for p in prompt_input if p)
    else:
        positive_prompt = str(prompt_input)
    
    prompt_lines = [line.strip() for line in positive_prompt.split("\n") if line.strip()]
    prompt_count = len(prompt_lines)
    if prompt_count > 1:
        total_frames = length * prompt_count
        total_seconds = total_frames / 16.0
        logger.info(f"📹 多提示词模式: {prompt_count}个提示词，总长度约{total_seconds:.1f}秒")
    
    negative_prompt = job_input.get("negative_prompt", "")
    
    # 调整分辨率
    original_width = job_input.get("width", 480)
    original_height = job_input.get("height", 832)
    adjusted_width = to_nearest_multiple_of_16(original_width)
    adjusted_height = to_nearest_multiple_of_16(original_height)
    if adjusted_width != original_width or adjusted_height != original_height:
        logger.info(f"分辨率调整: {original_width}x{original_height} -> {adjusted_width}x{adjusted_height}")
    
    # 配置节点
    configure_steadydancer_nodes(
        prompt, job_input, task_id, image_path,
        adjusted_width, adjusted_height, length,
        positive_prompt, negative_prompt,
        steps, seed, cfg, scheduler, sampler_name
    )
    
    # 自动填充缺失的必需输入（在所有配置之后）
    logger.info("自动填充缺失的必需输入...")
    for node_id, node in prompt.items():
        fill_missing_inputs_from_widgets(node_id, node)
    
    # 修正所有节点的值类型错误
    logger.info("修正值类型错误...")
    for node_id, node in prompt.items():
        class_type = node.get("class_type", "")
        if "inputs" not in node:
            continue
        
        # WanVideoModelLoader: 修正 quantization、base_precision 和 load_device
        if "WanVideoModelLoader" in class_type:
            # 从 widgets_values 填充缺失的必需输入
            if "widgets_values" in node and isinstance(node["widgets_values"], list):
                widgets = node["widgets_values"]
                if len(widgets) >= 2 and "base_precision" not in node["inputs"]:
                    node["inputs"]["base_precision"] = widgets[1]
                if len(widgets) >= 3:
                    quant = widgets[2]
                    if quant not in ["disabled", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e4m3fn_scaled", "fp8_e4m3fn_scaled_fast", "fp8_e5m2", "fp8_e5m2_fast", "fp8_e5m2_scaled", "fp8_e5m2_scaled_fast"]:
                        quant = "disabled"
                    node["inputs"]["quantization"] = quant
                if len(widgets) >= 4:
                    load_dev = widgets[3]
                    if load_dev == "offload_device":
                        load_dev = "main_device"
                        logger.warning(f"节点 {node_id}: 将 load_device 从 'offload_device' 改为 'main_device' 以避免 CUDA 错误")
                    if load_dev not in ["main_device", "offload_device"]:
                        load_dev = "main_device"
                    node["inputs"]["load_device"] = load_dev
            
            # 验证并修正 quantization
            if "quantization" in node["inputs"]:
                quant = node["inputs"]["quantization"]
                if quant not in ["disabled", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e4m3fn_scaled", "fp8_e4m3fn_scaled_fast", "fp8_e5m2", "fp8_e5m2_fast", "fp8_e5m2_scaled", "fp8_e5m2_scaled_fast"]:
                    node["inputs"]["quantization"] = "disabled"
            else:
                node["inputs"]["quantization"] = "disabled"
            
            # 确保 base_precision 存在
            if "base_precision" not in node["inputs"]:
                node["inputs"]["base_precision"] = "float16"
        
        # WanVideoTextEncodeCached: 修正 offload_device
        if "WanVideoTextEncodeCached" in class_type:
            if "widgets_values" in node and isinstance(node["widgets_values"], list):
                widgets = node["widgets_values"]
                if len(widgets) >= 6:
                    offload_dev = widgets[6]
                    if offload_dev == "offload_device":
                        offload_dev = "main_device"
                        logger.warning(f"节点 {node_id}: 将 offload_device 从 'offload_device' 改为 'main_device'")
                    if offload_dev not in ["main_device", "offload_device", "cpu"]:
                        offload_dev = "main_device"
                    node["inputs"]["offload_device"] = offload_dev
        
        # WanVideoDecode/WanVideoEncode: 修正 tile 参数
        if "WanVideoDecode" in class_type or "WanVideoEncode" in class_type:
            tile_x = node["inputs"].get("tile_x", 0)
            tile_y = node["inputs"].get("tile_y", 0)
            tile_stride_x = node["inputs"].get("tile_stride_x", 0)
            tile_stride_y = node["inputs"].get("tile_stride_y", 0)
            
            if tile_x > 0 and tile_stride_x >= tile_x:
                node["inputs"]["tile_stride_x"] = max(32, tile_x - 32)
                logger.warning(f"节点 {node_id}: 修正 tile_stride_x 必须小于 tile_x")
            if tile_y > 0 and tile_stride_y >= tile_y:
                node["inputs"]["tile_stride_y"] = max(32, tile_y - 32)
                logger.warning(f"节点 {node_id}: 修正 tile_stride_y 必须小于 tile_y")
    
    # 连接并执行
    wait_for_http_connection()
    ws = connect_websocket()
    
    try:
        videos = get_videos(ws, prompt)
        ws.close()
        
        for node_id in videos:
            if videos[node_id]:
                return {"video": videos[node_id][0]}
        
        return {"error": "未找到视频"}
    except Exception as e:
        ws.close()
        error_message = str(e)
        logger.error(f"视频生成失败: {error_message}")
        return {"error": error_message}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

