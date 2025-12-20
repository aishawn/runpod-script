import runpod
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.parse
import urllib.error
import binascii
import subprocess
import shutil
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_address = os.getenv('SERVER_ADDRESS', '127.0.0.1')
client_id = str(uuid.uuid4())


def to_nearest_multiple_of_16(value):
    """将值调整为最接近的16的倍数，最小16"""
    try:
        adjusted = int(round(float(value) / 16.0) * 16)
        return max(16, adjusted)
    except Exception:
        raise Exception(f"width/height值不是数字: {value}")


def process_input(input_data, temp_dir, output_filename, input_type):
    """处理输入数据并返回文件路径"""
    if input_type == "path":
        return input_data
    elif input_type == "url":
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        return download_file_from_url(input_data, file_path)
    elif input_type == "base64":
        return save_base64_to_file(input_data, temp_dir, output_filename)
    else:
        raise Exception(f"不支持的输入类型: {input_type}")


def download_file_from_url(url, output_path):
    """从URL下载文件"""
    result = subprocess.run(['wget', '-O', output_path, '--no-verbose', url],
                          capture_output=True, text=True)
    if result.returncode == 0:
        return output_path
    raise Exception(f"URL下载失败: {result.stderr}")


def save_base64_to_file(base64_data, temp_dir, output_filename):
    """将Base64数据保存为文件"""
    decoded_data = base64.b64decode(base64_data)
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
    with open(file_path, 'wb') as f:
        f.write(decoded_data)
    return file_path


def queue_prompt(prompt, is_mega_model=False):
    """提交prompt到ComfyUI"""
    url = f"http://{server_address}:8188/prompt"
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    req.add_header('Content-Type', 'application/json')
    try:
        response = urllib.request.urlopen(req)
        return json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"HTTP Error {e.code}: {error_body}")
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


def get_videos(ws, prompt, is_mega_model=False):
    """获取生成的视频，增强错误处理和节点状态跟踪"""
    prompt_id = queue_prompt(prompt, is_mega_model)['prompt_id']
    error_info = None
    node_errors = {}
    node_status = {}
    executed_nodes = set()
    execution_order = []  # 记录节点执行顺序
    
    logger.info(f"开始执行工作流，prompt_id: {prompt_id}")
    
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                node_id = data.get('node')
                if node_id:
                    node_status[node_id] = 'executing'
                    executed_nodes.add(node_id)
                    # 记录执行顺序
                    if node_id not in execution_order:
                        execution_order.append(node_id)
                    logger.debug(f"节点 {node_id} 正在执行...")
                elif data['node'] is None and data['prompt_id'] == prompt_id:
                    logger.info("所有节点执行完成")
                    break
            elif message['type'] == 'execution_error':
                error_data = message.get('data', {})
                node_id = error_data.get('node_id', 'unknown')
                error_info = error_data.get('error', 'Unknown execution error')
                exception_message = error_data.get('exception_message', '')
                
                node_errors[node_id] = {
                    'error': error_info,
                    'type': error_data.get('type', ''),
                    'exception_message': exception_message,
                    'full_data': error_data
                }
                
                error_str = str(error_info)
                logger.error("=" * 60)
                logger.error(f"❌ 执行错误 - 节点: {node_id}")
                if 'OutOfMemoryError' in error_str or 'OOM' in error_str:
                    logger.error(f"GPU内存不足(OOM): {error_info}")
                    logger.error("建议: 减小分辨率、帧数或提示词长度")
                else:
                    logger.error(f"错误类型: {error_data.get('type', 'unknown')}")
                    logger.error(f"错误信息: {error_info}")
                    if exception_message:
                        logger.error(f"异常详情: {exception_message[:200]}...")  # 限制长度
            elif message['type'] == 'progress':
                data = message.get('data', {})
                node_id = data.get('node')
                if node_id:
                    node_status[node_id] = 'progress'
                    logger.debug(f"节点 {node_id} 进度: {data.get('value', 0)}/{data.get('max', 100)}")

    history = get_history(prompt_id)[prompt_id]
    
    # 检查未执行的节点
    if node_errors:
        logger.warning(f"发现 {len(node_errors)} 个节点执行错误")
        for node_id, error_data in node_errors.items():
            logger.warning(f"  节点 {node_id}: {error_data.get('error', 'Unknown error')}")
    
    if 'error' in history:
        error_info = history['error']
        if isinstance(error_info, dict):
            error_info = error_info.get('message', str(error_info))
        error_str = str(error_info)
        if 'OutOfMemoryError' in error_str or 'OOM' in error_str or 'allocation' in error_str.lower():
            raise Exception(f"GPU内存不足(OOM): {error_info}. 请减小分辨率、帧数或提示词长度。")
        raise Exception(f"ComfyUI执行错误: {error_info}")
    
    if 'outputs' not in history:
        raise Exception("执行历史中未找到输出")
    
    # 详细日志：记录所有输出节点
    all_output_nodes = list(history['outputs'].keys())
    logger.info(f"📊 执行历史中的输出节点 ({len(all_output_nodes)} 个): {all_output_nodes}")
    
    output_videos = {}
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        videos_output = []
        
        # 检查节点类型和输出字段
        output_keys = list(node_output.keys())
        node_class = prompt.get(node_id, {}).get("class_type", "unknown") if node_id in prompt else "unknown"
        
        # 对于 VHS_VideoCombine 节点，记录详细信息
        if "VHS_VideoCombine" in node_class:
            logger.info(f"🔍 处理 VHS_VideoCombine 节点 {node_id}: 输出字段 = {output_keys}")
            save_output = prompt.get(node_id, {}).get("inputs", {}).get("save_output", False) if node_id in prompt else False
            logger.info(f"   节点 {node_id}: save_output = {save_output}")
        
        video_list = node_output.get('gifs') or node_output.get('videos')
        
        if video_list:
            logger.info(f"✅ 节点 {node_id} ({node_class}): 找到视频输出，数量: {len(video_list)}")
            for video in video_list:
                if 'fullpath' in video:
                    video_path = video['fullpath']
                    if os.path.exists(video_path):
                        with open(video_path, 'rb') as f:
                            video_data = base64.b64encode(f.read()).decode('utf-8')
                        videos_output.append(video_data)
                        logger.info(f"   节点 {node_id}: 成功读取视频文件 {video_path}")
                    else:
                        logger.warning(f"   节点 {node_id}: 视频文件不存在: {video_path}")
                elif 'filename' in video:
                    try:
                        video_bytes = get_image(video['filename'], 
                                              video.get('subfolder', ''),
                                              video.get('type', 'output'))
                        video_data = base64.b64encode(video_bytes).decode('utf-8')
                        videos_output.append(video_data)
                        logger.info(f"   节点 {node_id}: 成功读取视频文件 {video['filename']} (type: {video.get('type', 'output')})")
                    except Exception as e:
                        logger.warning(f"   节点 {node_id}: 无法读取视频文件 {video['filename']}: {e}")
        else:
            # 对于 VHS_VideoCombine 节点，如果没有视频输出，记录详细信息
            if "VHS_VideoCombine" in node_class:
                logger.warning(f"⚠️ 节点 {node_id} (VHS_VideoCombine): 没有视频输出")
                logger.warning(f"   输出字段: {output_keys}")
                logger.warning(f"   节点配置: save_output = {prompt.get(node_id, {}).get('inputs', {}).get('save_output', False) if node_id in prompt else 'N/A'}")
        
        output_videos[node_id] = videos_output

    # 记录所有有视频输出的节点
    video_output_nodes = [node_id for node_id in output_videos if output_videos[node_id]]
    logger.info(f"📹 有视频输出的节点 ({len(video_output_nodes)} 个): {video_output_nodes}")
    for node_id in video_output_nodes:
        logger.info(f"   节点 {node_id}: {len(output_videos[node_id])} 个视频")

    # 返回输出视频和执行顺序
    return output_videos, execution_order


def get_getnode_class_name():
    """获取GetNode节点的实际class_type名称"""
    try:
        url = f"http://{server_address}:8188/object_info"
        with urllib.request.urlopen(url, timeout=5) as response:
            object_info = json.loads(response.read())
            for name in ["GetNode|comfyui-logic", "GetNode", "GetNode|theUpsider"]:
                if name in object_info:
                    return name
            return "GetNode"
    except Exception:
        return "GetNode"


def get_available_models():
    """获取可用模型列表"""
    try:
        url = f"http://{server_address}:8188/object_info"
        with urllib.request.urlopen(url, timeout=5) as response:
            object_info = json.loads(response.read())
            models = []
            
            # WanVideoModelLoader
            if "WanVideoModelLoader" in object_info:
                loader_info = object_info["WanVideoModelLoader"]
                wan_models = (loader_info.get("model") or
                            loader_info.get("input", {}).get("required", {}).get("model") or [])
                if isinstance(wan_models, list) and wan_models:
                    if isinstance(wan_models[0], list):
                        wan_models = wan_models[0]
                    models.extend([m for m in wan_models if isinstance(m, str)])
            
            # CheckpointLoaderSimple
            if "CheckpointLoaderSimple" in object_info:
                loader_info = object_info["CheckpointLoaderSimple"]
                checkpoint_models = (loader_info.get("ckpt_name") or
                                   loader_info.get("input", {}).get("required", {}).get("ckpt_name") or [])
                if isinstance(checkpoint_models, list) and checkpoint_models:
                    if isinstance(checkpoint_models[0], list):
                        checkpoint_models = checkpoint_models[0]
                    models.extend([m for m in checkpoint_models if isinstance(m, str)])
            
            return list(set(models))
    except Exception as e:
        logger.warning(f"获取模型列表失败: {e}")
        return []


def update_model_in_prompt(prompt, node_id, available_models):
    """更新prompt中的模型名称"""
    if node_id not in prompt:
        return False
    node = prompt[node_id]
    if "inputs" not in node or "model" not in node["inputs"]:
        return False
    
    current_model = node["inputs"]["model"]
    if current_model in available_models:
        return False
    
    i2v_models = [m for m in available_models if "I2V" in m.upper() or "i2v" in m.lower()]
    new_model = i2v_models[0] if i2v_models else (available_models[0] if available_models else None)
    if new_model:
        node["inputs"]["model"] = new_model
        return True
    return False


def load_workflow(workflow_path):
    """加载并验证工作流JSON文件"""
    if not os.path.exists(workflow_path):
        raise FileNotFoundError(f"工作流文件不存在: {workflow_path}")
    
    file_size = os.path.getsize(workflow_path)
    if file_size == 0:
        raise ValueError(f"工作流文件为空: {workflow_path}")
    
    with open(workflow_path, 'r', encoding='utf-8') as file:
        content = file.read().strip()
        if not content.startswith(('{', '[')):
            raise ValueError(f"工作流文件不是有效的JSON格式: {workflow_path}")
        return json.loads(content)


def find_wan21_model():
    """自动查找可用的Wan21模型"""
    model_paths = [
        "/ComfyUI/models/checkpoints/WanVideo/OneToAll/",
        "/ComfyUI/models/diffusion_models/WanVideo/OneToAll/",
        "/workspace/models/WanVideo/OneToAll/",
        "/ComfyUI/models/checkpoints/",
        "/ComfyUI/models/diffusion_models/",
    ]
    
    # 默认模型名称模式
    model_patterns = [
        "Wan21-OneToAllAnimation",
        "Wan21",
        "OneToAll"
    ]
    
    for base_path in model_paths:
        if not os.path.exists(base_path):
            continue
            
        # 查找匹配的模型文件
        try:
            files = os.listdir(base_path)
            for file in files:
                if file.endswith('.safetensors'):
                    for pattern in model_patterns:
                        if pattern in file:
                            full_path = os.path.join(base_path, file)
                            logger.info(f"找到Wan21模型: {full_path}")
                            return full_path
        except Exception as e:
            logger.debug(f"搜索路径 {base_path} 时出错: {e}")
            continue
    
    # 如果没找到，返回默认路径
    default_model = "WanVideo/OneToAll/Wan21-OneToAllAnimation_fp8_e4m3fn_scaled_KJ.safetensors"
    logger.warning(f"未找到Wan21模型，使用默认: {default_model}")
    return default_model


def ensure_model_in_checkpoints(model_name):
    """确保模型文件在checkpoints目录中"""
    model_name = os.path.basename(model_name)
    target_path = "/ComfyUI/models/checkpoints/" + model_name
    target_dir = "/ComfyUI/models/checkpoints"
    
    if os.path.exists(target_path):
        if os.path.islink(target_path) and os.path.exists(os.readlink(target_path)):
            return True
        elif os.path.isfile(target_path):
            return True
        else:
            os.remove(target_path)
    
    os.makedirs(target_dir, exist_ok=True)
    
    # 扩展搜索路径
    search_paths = [
        "/ComfyUI/models/diffusion_models/" + model_name,
        "/workspace/models/" + model_name,
        "/ComfyUI/models/checkpoints/" + model_name,
        "/ComfyUI/models/diffusion_models/WanVideo/OneToAll/" + model_name,
        "/workspace/models/WanVideo/OneToAll/" + model_name,
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
                os.symlink(path, target_path)
                time.sleep(0.5)
                if os.path.exists(target_path):
                    logger.info(f"成功创建模型链接: {target_path} -> {path}")
                    return True
            except Exception as e:
                logger.debug(f"创建符号链接失败: {e}")
                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    shutil.copy2(path, target_path)
                    logger.info(f"成功复制模型文件: {target_path}")
                    return True
                except Exception as e2:
                    logger.debug(f"复制文件失败: {e2}")
                    pass
    return False


def convert_nodes_to_prompt_format(workflow_data, logic_node_values, getnode_class_name):
    """将nodes数组格式转换为节点ID key格式"""
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
                
                source_node = all_nodes_map.get(source_node_id)
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
                converted_node["inputs"] = converted_inputs
            else:
                converted_node[key] = value
        
        # 设置class_type
        if "type" in converted_node:
            node_type = converted_node["type"]
            final_class_type = None
            
            # 处理 UUID 类型的节点（通常是子图节点）
            # 尝试从 workflow 的 definitions/subgraphs 中查找实际的节点类型
            if len(str(node_type)) == 36 and str(node_type).count('-') == 4:  # UUID 格式
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
                    logger.info(f"节点 {node_id}: 将子图 UUID {node_type} 替换为 {subgraph_type}")
                else:
                    # 如果找不到，根据节点标题推断
                    node_title = converted_node.get("title", "").lower()
                    if "extend" in node_title:
                        final_class_type = "WanVideoAddOneToAllExtendEmbeds"
                        logger.info(f"节点 {node_id}: 根据标题 '{node_title}' 推断为 WanVideoAddOneToAllExtendEmbeds")
                    else:
                        # 保持原样（可能会失败，但至少不会破坏结构）
                        final_class_type = node_type
                        logger.warning(f"节点 {node_id}: 无法解析子图 UUID {node_type}，保持原样")
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
                if len(str(node_type)) == 36 and str(node_type).count('-') == 4 and final_class_type != node_type:
                    converted_node["type"] = final_class_type
        
        if "inputs" not in converted_node:
            converted_node["inputs"] = {}
        
        prompt[node_id] = converted_node
    
    return prompt


def find_node_by_class_type(prompt, class_type_pattern, attribute=None, attribute_value=None):
    """根据class_type模式查找节点，支持可选的属性过滤"""
    candidates = []
    for node_id, node in prompt.items():
        class_type = node.get("class_type", "")
        if class_type_pattern in class_type:
            if attribute is None:
                candidates.append(node_id)
            elif attribute in node.get("inputs", {}):
                if attribute_value is None or node["inputs"][attribute] == attribute_value:
                    candidates.append(node_id)
            elif attribute in node.get("widgets_values", {}):
                if attribute_value is None or node["widgets_values"][attribute] == attribute_value:
                    candidates.append(node_id)
    
    if candidates:
        # 优先返回第一个匹配的节点
        return candidates[0]
    return None


def find_node_by_type_and_input(prompt, node_type_pattern, input_name=None):
    """根据节点类型和输入名称查找节点"""
    for node_id, node in prompt.items():
        class_type = node.get("class_type", "")
        if node_type_pattern in class_type:
            if input_name is None or input_name in node.get("inputs", {}):
                return node_id
    return None


def set_node_value(prompt, node_id, key, value, use_widgets=False):
    """设置节点值的辅助函数"""
    if node_id not in prompt:
        logger.warning(f"节点 {node_id} 不存在于prompt中")
        return False
    if "inputs" not in prompt[node_id]:
        prompt[node_id]["inputs"] = {}
    prompt[node_id]["inputs"][key] = value
    if use_widgets and "widgets_values" in prompt[node_id]:
        widgets = prompt[node_id]["widgets_values"]
        if isinstance(widgets, list) and len(widgets) > 0:
            widgets[0] = value
    return True


def configure_mega_workflow(prompt, job_input, image_path, positive_prompt, negative_prompt, 
                           adjusted_width, adjusted_height, length, steps, seed, cfg, 
                           sampler_name, scheduler, available_models):
    """配置MEGA工作流"""
    # 节点597: 起始图像
    set_node_value(prompt, "597", "image", image_path, True)
    
    # 节点591: 多提示词
    if "591" in prompt:
        if "widgets_values" in prompt["591"]:
            widgets = prompt["591"]["widgets_values"]
            widgets[0] = positive_prompt
            if len(widgets) < 2:
                widgets.append("")
            if len(widgets) < 3:
                widgets.append("")
        if "inputs" not in prompt["591"]:
            prompt["591"]["inputs"] = {}
        prompt["591"]["inputs"]["Multi_prompts"] = positive_prompt
    
    # 节点574: 模型
    if "574" in prompt:
        model_name = (prompt["574"].get("widgets_values", [None])[0] or 
                     (available_models[0] if available_models else 
                      "wan2.2-rapid-mega-aio-nsfw-v12.1.safetensors"))
        
        checkpoint_models = []
        try:
            url = f"http://{server_address}:8188/object_info"
            with urllib.request.urlopen(url, timeout=5) as response:
                object_info = json.loads(response.read())
                if "CheckpointLoaderSimple" in object_info:
                    loader_info = object_info["CheckpointLoaderSimple"]
                    checkpoint_models = (loader_info.get("input", {}).get("required", {}).get("ckpt_name") or [])
                    if isinstance(checkpoint_models, list) and checkpoint_models:
                        if isinstance(checkpoint_models[0], list):
                            checkpoint_models = checkpoint_models[0]
                        checkpoint_models = [m for m in checkpoint_models if isinstance(m, str)]
        except Exception:
            pass
        
        final_model = (model_name if model_name in checkpoint_models else 
                      (checkpoint_models[0] if checkpoint_models else model_name))
        if "inputs" not in prompt["574"]:
            prompt["574"]["inputs"] = {}
        prompt["574"]["inputs"]["ckpt_name"] = final_model
    
    # 节点595: 文件名前缀
    filename_prefix = job_input.get("filename_prefix", "rapid-mega-out/vid")
    set_node_value(prompt, "595", "value", filename_prefix, True)
    
    # 节点567: 负面提示词
    set_node_value(prompt, "567", "text", negative_prompt, True)
    
    # 节点576: VACE num_frames
    if "576" in prompt:
        empty_frame_level = 1.0
        if "widgets_values" in prompt["576"]:
            widgets = prompt["576"]["widgets_values"]
            widgets[0] = length
            if len(widgets) < 2:
                widgets.append(1.0)
            empty_frame_level = widgets[1] if len(widgets) > 1 else 1.0
        if "inputs" not in prompt["576"]:
            prompt["576"]["inputs"] = {}
        prompt["576"]["inputs"]["num_frames"] = length
        prompt["576"]["inputs"]["empty_frame_level"] = empty_frame_level
    
    # 节点572: WanVaceToVideo
    if "572" in prompt:
        batch_size = 1
        if "widgets_values" in prompt["572"]:
            widgets = prompt["572"]["widgets_values"]
            widgets[0] = adjusted_width
            widgets[1] = adjusted_height
            widgets[2] = length
            widgets[3] = 1
            if len(widgets) < 5:
                widgets.append(1)
            batch_size = widgets[4] if len(widgets) > 4 else 1
        if "inputs" not in prompt["572"]:
            prompt["572"]["inputs"] = {}
        prompt["572"]["inputs"].update({
            "width": adjusted_width,
            "height": adjusted_height,
            "length": length,
            "batch_size": batch_size,
            "strength": 1
        })
    
    # 节点562: ModelSamplingSD3
    shift_value = job_input.get("shift", 7.02)
    set_node_value(prompt, "562", "shift", shift_value, True)
    
    # 节点563: KSampler
    if "563" in prompt:
        if "widgets_values" in prompt["563"]:
            widgets = prompt["563"]["widgets_values"]
            widgets[0] = seed
            widgets[2] = steps
            widgets[3] = cfg
            while len(widgets) < 7:
                widgets.append(None)
            if not widgets[4] or widgets[4] == "randomize":
                widgets[4] = sampler_name
            if not widgets[5]:
                widgets[5] = scheduler
        if "inputs" not in prompt["563"]:
            prompt["563"]["inputs"] = {}
        widgets = prompt["563"].get("widgets_values", [seed, "randomize", steps, cfg, sampler_name, scheduler, 1])
        prompt["563"]["inputs"].update({
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": widgets[4] if len(widgets) > 4 and widgets[4] else sampler_name,
            "scheduler": widgets[5] if len(widgets) > 5 and widgets[5] else scheduler,
            "denoise": widgets[6] if len(widgets) > 6 else 1.0
        })
    
    # 节点584: VHS_VideoCombine
    if "584" in prompt:
        if "inputs" not in prompt["584"]:
            prompt["584"]["inputs"] = {}
        if "widgets_values" in prompt["584"]:
            widgets = prompt["584"]["widgets_values"]
            if isinstance(widgets, dict):
                for key, value in widgets.items():
                    if key != "videopreview":
                        prompt["584"]["inputs"][key] = value
            else:
                prompt["584"]["inputs"].update({
                    "frame_rate": 16,
                    "loop_count": 0,
                    "filename_prefix": filename_prefix,
                    "format": "video/h264-mp4",
                    "save_output": True,
                    "pingpong": False
                })
        else:
            prompt["584"]["inputs"].update({
                "frame_rate": 16,
                "loop_count": 0,
                "filename_prefix": filename_prefix,
                "format": "video/h264-mp4",
                "save_output": True,
                "pingpong": False
            })


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
    
    # 根据节点类型填充缺失的输入
    if "WanVideoScheduler" in class_type:
        # widgets: [scheduler, steps, start_step, end_step, shift]
        if len(widgets) >= 1 and "scheduler" not in node["inputs"]:
            node["inputs"]["scheduler"] = widgets[0]
        if len(widgets) >= 2 and "steps" not in node["inputs"]:
            node["inputs"]["steps"] = widgets[1]
        if len(widgets) >= 3 and "start_step" not in node["inputs"]:
            node["inputs"]["start_step"] = widgets[2]
        if len(widgets) >= 4 and "end_step" not in node["inputs"]:
            node["inputs"]["end_step"] = widgets[3]
        if len(widgets) >= 5 and "shift" not in node["inputs"]:
            shift_value = widgets[4]
            # 确保 shift 值 >= 0
            if isinstance(shift_value, (int, float)) and shift_value < 0:
                shift_value = 0.0
            node["inputs"]["shift"] = shift_value
        # 验证并修正 shift 值
        if "shift" in node["inputs"]:
            shift_value = node["inputs"]["shift"]
            if isinstance(shift_value, (int, float)) and shift_value < 0:
                node["inputs"]["shift"] = 0.0
    elif "WanVideoAddOneToAllExtendEmbeds" in class_type:
        # widgets: [num_frames, window_size, if_not_enough_frames]
        if len(widgets) >= 1 and "num_frames" not in node["inputs"]:
            node["inputs"]["num_frames"] = widgets[0]
        if len(widgets) >= 2 and "window_size" not in node["inputs"]:
            node["inputs"]["window_size"] = widgets[1]
        if len(widgets) >= 3 and "if_not_enough_frames" not in node["inputs"]:
            if_not_enough = widgets[2]
            # 修正值：0 -> 'pad_with_last', 1 -> 'error'
            if if_not_enough == 0:
                if_not_enough = "pad_with_last"
            elif if_not_enough == 1:
                if_not_enough = "error"
            node["inputs"]["if_not_enough_frames"] = if_not_enough
        # 验证并修正 if_not_enough_frames 值
        if "if_not_enough_frames" in node["inputs"]:
            if_not_enough = node["inputs"]["if_not_enough_frames"]
            if if_not_enough == 0:
                node["inputs"]["if_not_enough_frames"] = "pad_with_last"
            elif if_not_enough == 1:
                node["inputs"]["if_not_enough_frames"] = "error"
    elif "WanVideoAddOneToAllPoseEmbeds" in class_type or "WanVideoAddOneToAllReferenceEmbeds" in class_type:
        # widgets: [strength, start_percent, end_percent]
        if len(widgets) >= 1 and "strength" not in node["inputs"]:
            node["inputs"]["strength"] = widgets[0]
        if len(widgets) >= 2 and "start_percent" not in node["inputs"]:
            node["inputs"]["start_percent"] = widgets[1]
        if len(widgets) >= 3 and "end_percent" not in node["inputs"]:
            node["inputs"]["end_percent"] = widgets[2]
    elif "ImageBatchExtendWithOverlap" in class_type:
        # widgets: [overlap, overlap_mode, overlap_side]
        if len(widgets) >= 1 and "overlap" not in node["inputs"]:
            node["inputs"]["overlap"] = widgets[0]
        if len(widgets) >= 2 and "overlap_mode" not in node["inputs"]:
            overlap_mode = widgets[1]
            # 修正值：'source' -> 'linear_blend' (正确的枚举值)
            if overlap_mode == "source":
                overlap_mode = "linear_blend"
            node["inputs"]["overlap_mode"] = overlap_mode
        if len(widgets) >= 3 and "overlap_side" not in node["inputs"]:
            overlap_side = widgets[2]
            # 修正值：'linear_blend' -> 'source' (正确的枚举值)
            if overlap_side == "linear_blend":
                overlap_side = "source"
            node["inputs"]["overlap_side"] = overlap_side
        # 验证并修正值
        if "overlap_mode" in node["inputs"] and node["inputs"]["overlap_mode"] == "source":
            node["inputs"]["overlap_mode"] = "linear_blend"
        if "overlap_side" in node["inputs"] and node["inputs"]["overlap_side"] == "linear_blend":
            node["inputs"]["overlap_side"] = "source"
    elif "GetImageRangeFromBatch" in class_type:
        # widgets: [start_index, end_index]
        if len(widgets) >= 1 and "start_index" not in node["inputs"]:
            node["inputs"]["start_index"] = widgets[0]
        if len(widgets) >= 2 and "end_index" not in node["inputs"]:
            node["inputs"]["end_index"] = widgets[1]
    elif "WanVideoLoraSelect" in class_type:
        # widgets: [lora, strength]
        if len(widgets) >= 1 and "lora" not in node["inputs"]:
            lora_path = widgets[0]
            # 规范化路径：去除反斜杠，保留 WanVideo/ 前缀（如果需要）
            if isinstance(lora_path, str) and lora_path:
                lora_path = lora_path.replace("\\", "/")
                # 去除 ComfyUI/models/loras/ 前缀
                if lora_path.startswith("ComfyUI/models/loras/"):
                    lora_path = lora_path.replace("ComfyUI/models/loras/", "")
                elif lora_path.startswith("/ComfyUI/models/loras/"):
                    lora_path = lora_path.replace("/ComfyUI/models/loras/", "")
                # 如果路径不包含 WanVideo/ 前缀，且包含子目录（如 Lightx2v/），添加前缀
                if "/" in lora_path and not lora_path.startswith("WanVideo/"):
                    lora_path = "WanVideo/" + lora_path
            node["inputs"]["lora"] = lora_path
        if len(widgets) >= 2 and "strength" not in node["inputs"]:
            node["inputs"]["strength"] = widgets[1]
        # 验证并修正 lora 路径
        if "lora" in node["inputs"] and isinstance(node["inputs"]["lora"], str) and node["inputs"]["lora"]:
            lora_path = node["inputs"]["lora"]
            lora_path = lora_path.replace("\\", "/")
            if lora_path.startswith("ComfyUI/models/loras/"):
                lora_path = lora_path.replace("ComfyUI/models/loras/", "")
            elif lora_path.startswith("/ComfyUI/models/loras/"):
                lora_path = lora_path.replace("/ComfyUI/models/loras/", "")
            # 如果路径包含子目录但不包含 WanVideo/ 前缀，添加前缀
            if "/" in lora_path and not lora_path.startswith("WanVideo/"):
                lora_path = "WanVideo/" + lora_path
            node["inputs"]["lora"] = lora_path
    elif "WanVideoBlockSwap" in class_type:
        # widgets: [blocks_to_swap, offload_txt_emb, offload_img_emb]
        if len(widgets) >= 1 and "blocks_to_swap" not in node["inputs"]:
            node["inputs"]["blocks_to_swap"] = widgets[0]
        if len(widgets) >= 2 and "offload_txt_emb" not in node["inputs"]:
            node["inputs"]["offload_txt_emb"] = widgets[1]
        if len(widgets) >= 3 and "offload_img_emb" not in node["inputs"]:
            node["inputs"]["offload_img_emb"] = widgets[2]
    elif "WanVideoTorchCompileSettings" in class_type:
        # widgets: [backend, mode, fullgraph, dynamic, ...]
        if len(widgets) >= 1 and "backend" not in node["inputs"]:
            node["inputs"]["backend"] = widgets[0]
        if len(widgets) >= 2 and "mode" not in node["inputs"]:
            mode_value = widgets[1]
            # 修正值：False -> 'default'
            if mode_value is False or mode_value == "False":
                mode_value = "default"
            node["inputs"]["mode"] = mode_value
        if len(widgets) >= 3 and "fullgraph" not in node["inputs"]:
            node["inputs"]["fullgraph"] = widgets[2]
        if len(widgets) >= 4 and "dynamic" not in node["inputs"]:
            node["inputs"]["dynamic"] = widgets[3]
        if len(widgets) >= 5 and "dynamo_cache_size_limit" not in node["inputs"]:
            node["inputs"]["dynamo_cache_size_limit"] = widgets[4]
        if len(widgets) >= 6 and "compile_transformer_blocks_only" not in node["inputs"]:
            node["inputs"]["compile_transformer_blocks_only"] = widgets[5]
        # 验证并修正 mode 值
        if "mode" in node["inputs"]:
            mode_value = node["inputs"]["mode"]
            if mode_value is False or mode_value == "False":
                node["inputs"]["mode"] = "default"
    elif "PoseDetectionOneToAllAnimation" in class_type:
        # 默认值
        if "align_to" not in node["inputs"]:
            node["inputs"]["align_to"] = "ref"
        else:
            # 修正值：'head' -> 'ref'
            if node["inputs"]["align_to"] == "head":
                node["inputs"]["align_to"] = "ref"
        if "draw_face_points" not in node["inputs"]:
            node["inputs"]["draw_face_points"] = "full"
        else:
            # 修正值：False -> 'full', True -> 'full'
            draw_face = node["inputs"]["draw_face_points"]
            if draw_face is False or draw_face == "False":
                node["inputs"]["draw_face_points"] = "full"
            elif draw_face is True or draw_face == "True":
                node["inputs"]["draw_face_points"] = "full"
        if "draw_head" not in node["inputs"]:
            node["inputs"]["draw_head"] = "full"
        else:
            # 修正值：False -> 'full', True -> 'full'
            draw_head = node["inputs"]["draw_head"]
            if draw_head is False or draw_head == "False":
                node["inputs"]["draw_head"] = "full"
            elif draw_head is True or draw_head == "True":
                node["inputs"]["draw_head"] = "full"
    elif "ImageResizeKJv2" in class_type:
        # 默认值
        if "crop_position" not in node["inputs"]:
            node["inputs"]["crop_position"] = "center"
        if "upscale_method" not in node["inputs"]:
            node["inputs"]["upscale_method"] = "lanczos"
        if "keep_proportion" not in node["inputs"]:
            node["inputs"]["keep_proportion"] = "stretch"
        else:
            # 修正值：True -> 'stretch', False -> 'stretch'
            keep_prop = node["inputs"]["keep_proportion"]
            if keep_prop is True or keep_prop == "True":
                node["inputs"]["keep_proportion"] = "stretch"
            elif keep_prop is False or keep_prop == "False":
                node["inputs"]["keep_proportion"] = "stretch"
        if "pad_color" not in node["inputs"]:
            node["inputs"]["pad_color"] = 0
        if "divisible_by" not in node["inputs"]:
            node["inputs"]["divisible_by"] = 1
    elif "VHS_LoadVideo" in class_type:
        # 默认值
        if "force_rate" not in node["inputs"]:
            node["inputs"]["force_rate"] = 0
        if "custom_width" not in node["inputs"]:
            node["inputs"]["custom_width"] = 0
        if "custom_height" not in node["inputs"]:
            node["inputs"]["custom_height"] = 0
        if "frame_load_cap" not in node["inputs"]:
            node["inputs"]["frame_load_cap"] = 0
        if "select_every_nth" not in node["inputs"]:
            node["inputs"]["select_every_nth"] = 1
        if "skip_first_frames" not in node["inputs"]:
            node["inputs"]["skip_first_frames"] = 0
    elif "WanVideoDecode" in class_type:
        # 默认值
        if "tile_x" not in node["inputs"]:
            node["inputs"]["tile_x"] = 0
        if "tile_y" not in node["inputs"]:
            node["inputs"]["tile_y"] = 0
        if "tile_stride_x" not in node["inputs"]:
            node["inputs"]["tile_stride_x"] = 0
        if "tile_stride_y" not in node["inputs"]:
            node["inputs"]["tile_stride_y"] = 0
        if "enable_vae_tiling" not in node["inputs"]:
            node["inputs"]["enable_vae_tiling"] = False
        
        # 修复 tile 验证：如果 tile 为 0，禁用 tiling；否则确保 tile > tile_stride
        tile_x = node["inputs"].get("tile_x", 0)
        tile_y = node["inputs"].get("tile_y", 0)
        tile_stride_x = node["inputs"].get("tile_stride_x", 0)
        tile_stride_y = node["inputs"].get("tile_stride_y", 0)
        
        # 如果 tile 为 0，确保 tile_stride 也为 0（禁用 tiling）
        if tile_x == 0:
            node["inputs"]["tile_stride_x"] = 0
        elif tile_x > 0:
            # 如果 tile > 0，确保满足最小值要求（64）
            if tile_x < 64:
                node["inputs"]["tile_x"] = 64
                tile_x = 64
            # 确保 tile_stride 满足最小值要求（32）且小于 tile
            if tile_stride_x < 32:
                node["inputs"]["tile_stride_x"] = 32
                tile_stride_x = 32
            if tile_stride_x >= tile_x:
                node["inputs"]["tile_stride_x"] = max(32, tile_x - 32)
                logger.warning(f"节点 {node_id} (WanVideoDecode): 修正 tile_stride_x 必须小于 tile_x")
        
        if tile_y == 0:
            node["inputs"]["tile_stride_y"] = 0
        elif tile_y > 0:
            # 如果 tile > 0，确保满足最小值要求（64）
            if tile_y < 64:
                node["inputs"]["tile_y"] = 64
                tile_y = 64
            # 确保 tile_stride 满足最小值要求（32）且小于 tile
            if tile_stride_y < 32:
                node["inputs"]["tile_stride_y"] = 32
                tile_stride_y = 32
            if tile_stride_y >= tile_y:
                node["inputs"]["tile_stride_y"] = max(32, tile_y - 32)
                logger.warning(f"节点 {node_id} (WanVideoDecode): 修正 tile_stride_y 必须小于 tile_y")
        
        # 从 widgets_values 中提取缺失的必需输入
        if "widgets_values" in node and isinstance(node["widgets_values"], list):
            widgets = node["widgets_values"]
            # widgets_values 格式可能包含: [enable_vae_tiling, tile_x, tile_y, tile_stride_x, tile_stride_y, ...]
            # 某些版本的 WanVideoDecode 可能需要额外的参数
            # 检查是否有更多参数（如 force_offload, riflex_freq_index, shift）
            if len(widgets) >= 6 and "force_offload" not in node["inputs"]:
                node["inputs"]["force_offload"] = widgets[5] if isinstance(widgets[5], bool) else False
            if len(widgets) >= 7 and "riflex_freq_index" not in node["inputs"]:
                node["inputs"]["riflex_freq_index"] = widgets[6] if isinstance(widgets[6], (int, float)) else 0
            if len(widgets) >= 8 and "shift" not in node["inputs"]:
                node["inputs"]["shift"] = widgets[7] if isinstance(widgets[7], (int, float)) else 0.0
        
        # 如果仍然缺少必需输入，设置默认值
        if "force_offload" not in node["inputs"]:
            node["inputs"]["force_offload"] = False
        if "riflex_freq_index" not in node["inputs"]:
            node["inputs"]["riflex_freq_index"] = 0
        if "shift" not in node["inputs"]:
            node["inputs"]["shift"] = 0.0
    elif "WanVideoEncode" in class_type:
        # 默认值（使用默认值而不是 0，因为 0 会导致验证错误）
        if "tile_x" not in node["inputs"]:
            node["inputs"]["tile_x"] = 272  # 默认值
        if "tile_y" not in node["inputs"]:
            node["inputs"]["tile_y"] = 272  # 默认值
        if "tile_stride_x" not in node["inputs"]:
            node["inputs"]["tile_stride_x"] = 144  # 默认值
        if "tile_stride_y" not in node["inputs"]:
            node["inputs"]["tile_stride_y"] = 128  # 默认值
        if "enable_vae_tiling" not in node["inputs"]:
            node["inputs"]["enable_vae_tiling"] = False
        
        # 修复 tile 验证：确保 tile > tile_stride
        tile_x = node["inputs"].get("tile_x", 272)
        tile_y = node["inputs"].get("tile_y", 272)
        tile_stride_x = node["inputs"].get("tile_stride_x", 144)
        tile_stride_y = node["inputs"].get("tile_stride_y", 128)
        
        # 如果 tile 为 0，设置为默认值（因为节点要求 tile >= 64）
        if tile_x == 0:
            node["inputs"]["tile_x"] = 272
            node["inputs"]["tile_stride_x"] = 144
            tile_x = 272
            tile_stride_x = 144
            node["inputs"]["enable_vae_tiling"] = False
            logger.info(f"节点 {node_id} (WanVideoEncode): tile_x 为 0，设置为默认值 272（tiling 已禁用）")
        elif tile_x > 0:
            # 如果 tile > 0，确保满足最小值要求（64）
            if tile_x < 64:
                node["inputs"]["tile_x"] = 64
                tile_x = 64
            # 确保 tile_stride 满足最小值要求（32）且小于 tile
            if tile_stride_x < 32:
                node["inputs"]["tile_stride_x"] = 32
                tile_stride_x = 32
            if tile_stride_x >= tile_x:
                node["inputs"]["tile_stride_x"] = max(32, tile_x - 32)
                logger.warning(f"节点 {node_id} (WanVideoEncode): 修正 tile_stride_x 必须小于 tile_x")
        
        if tile_y == 0:
            node["inputs"]["tile_y"] = 272
            node["inputs"]["tile_stride_y"] = 128
            tile_y = 272
            tile_stride_y = 128
            node["inputs"]["enable_vae_tiling"] = False
            logger.info(f"节点 {node_id} (WanVideoEncode): tile_y 为 0，设置为默认值 272（tiling 已禁用）")
        elif tile_y > 0:
            # 如果 tile > 0，确保满足最小值要求（64）
            if tile_y < 64:
                node["inputs"]["tile_y"] = 64
                tile_y = 64
            # 确保 tile_stride 满足最小值要求（32）且小于 tile
            if tile_stride_y < 32:
                node["inputs"]["tile_stride_y"] = 32
                tile_stride_y = 32
            if tile_stride_y >= tile_y:
                node["inputs"]["tile_stride_y"] = max(32, tile_y - 32)
                logger.warning(f"节点 {node_id} (WanVideoEncode): 修正 tile_stride_y 必须小于 tile_y")
    elif "WanVideoSampler" in class_type:
        # widgets: [steps, seed, cfg, ...]
        # 某些版本的 WanVideoSampler 可能需要额外的参数
        if len(widgets) >= 1 and "steps" not in node["inputs"]:
            node["inputs"]["steps"] = widgets[0]
        if len(widgets) >= 2 and "seed" not in node["inputs"]:
            node["inputs"]["seed"] = widgets[1]
        if len(widgets) >= 3 and "cfg" not in node["inputs"]:
            node["inputs"]["cfg"] = widgets[2]
        # 检查是否有更多参数（如 shift, riflex_freq_index, force_offload）
        if len(widgets) >= 4 and "shift" not in node["inputs"]:
            shift_value = widgets[3] if isinstance(widgets[3], (int, float)) else 0.0
            if shift_value < 0:
                shift_value = 0.0
            node["inputs"]["shift"] = shift_value
        if len(widgets) >= 5 and "riflex_freq_index" not in node["inputs"]:
            node["inputs"]["riflex_freq_index"] = widgets[4] if isinstance(widgets[4], (int, float)) else 0
        if len(widgets) >= 6 and "force_offload" not in node["inputs"]:
            node["inputs"]["force_offload"] = widgets[5] if isinstance(widgets[5], bool) else False
        
        # 如果仍然缺少必需输入，设置默认值
        if "shift" not in node["inputs"]:
            node["inputs"]["shift"] = 0.0
        if "riflex_freq_index" not in node["inputs"]:
            node["inputs"]["riflex_freq_index"] = 0
        if "force_offload" not in node["inputs"]:
            node["inputs"]["force_offload"] = False
    elif "GetImageSizeAndCount" in class_type:
        # 这个节点需要 image 输入，但如果没有，可以跳过（不会影响执行）
        pass


def configure_wan21_workflow(prompt, job_input, image_path, positive_prompt, negative_prompt,
                             adjusted_width, adjusted_height, length, steps, seed, cfg, task_id):
    """配置Wan21工作流，使用动态节点查找"""
    # 动态查找输入图像节点
    image_node_id = find_node_by_class_type(prompt, "LoadImage")
    if image_node_id:
        if not set_node_value(prompt, image_node_id, "image", image_path, True):
            logger.warning(f"无法设置图像节点 {image_node_id} 的值")
    else:
        # 回退到硬编码的节点ID
        logger.warning("未找到LoadImage节点，使用硬编码节点ID 106")
        set_node_value(prompt, "106", "image", image_path, True)
    
    # 参考视频
    reference_video_path = None
    for key in ["reference_video_path", "reference_video_url", "reference_video_base64"]:
        if key in job_input:
            input_type = "path" if "path" in key else ("url" if "url" in key else "base64")
            try:
                reference_video_path = process_input(job_input[key], task_id, "reference_video.mp4", input_type)
                logger.info(f"成功加载参考视频: {reference_video_path}")
                break
            except Exception as e:
                logger.warning(f"加载参考视频失败: {e}")
    
    if reference_video_path:
        # 查找参考视频节点（LoadVideo或类似节点）
        video_node_id = find_node_by_class_type(prompt, "LoadVideo") or \
                       find_node_by_class_type(prompt, "VideoLoad") or \
                       find_node_by_type_and_input(prompt, "Video", "video")
        
        if not video_node_id:
            # 回退到硬编码的节点ID
            video_node_id = "2100"
            logger.warning("未找到视频加载节点，使用硬编码节点ID 2100")
        
        if video_node_id in prompt:
            node = prompt[video_node_id]
            # 支持多种widgets_values格式
            if "widgets_values" in node:
                widgets = node["widgets_values"]
                if isinstance(widgets, dict):
                    widgets["video"] = reference_video_path
                elif isinstance(widgets, list) and len(widgets) > 0:
                    widgets[0] = reference_video_path
            if "inputs" not in node:
                node["inputs"] = {}
            node["inputs"]["video"] = reference_video_path
            logger.info(f"已设置参考视频到节点 {video_node_id}")
    
    # 动态查找姿态检测节点
    pose_node_id = find_node_by_class_type(prompt, "OnnxDetectionModelLoader") or \
                   find_node_by_class_type(prompt, "PoseDetection")
    if pose_node_id:
        node = prompt[pose_node_id]
        if "widgets_values" in node:
            widgets = node["widgets_values"]
            if isinstance(widgets, list) and len(widgets) >= 2:
                widgets[0] = adjusted_height
                widgets[1] = adjusted_width
        if "inputs" not in node:
            node["inputs"] = {}
        node["inputs"]["width"] = adjusted_width
        node["inputs"]["height"] = adjusted_height
        logger.info(f"已设置姿态检测节点 {pose_node_id} 的尺寸: {adjusted_width}x{adjusted_height}")
    else:
        # 回退到硬编码的节点ID
        logger.warning("未找到姿态检测节点，使用硬编码节点ID 141")
        if "141" in prompt:
            if "widgets_values" in prompt["141"]:
                widgets = prompt["141"]["widgets_values"]
                if len(widgets) >= 2:
                    widgets[0] = adjusted_height
                    widgets[1] = adjusted_width
            if "inputs" not in prompt["141"]:
                prompt["141"]["inputs"] = {}
            prompt["141"]["inputs"]["width"] = adjusted_width
            prompt["141"]["inputs"]["height"] = adjusted_height
    
    # 动态查找模型加载节点
    model_node_id = find_node_by_class_type(prompt, "WanVideoModelLoader")
    if model_node_id:
        # 自动查找可用的Wan21模型
        wan21_model = find_wan21_model()
        # 转换为相对路径（去掉完整路径前缀）
        if wan21_model.startswith("/ComfyUI/models/diffusion_models/"):
            wan21_model = wan21_model.replace("/ComfyUI/models/diffusion_models/", "")
        elif wan21_model.startswith("/ComfyUI/models/checkpoints/"):
            wan21_model = wan21_model.replace("/ComfyUI/models/checkpoints/", "")
        # 处理 Windows 路径分隔符
        wan21_model = wan21_model.replace("\\", "/")
        
        if set_node_value(prompt, model_node_id, "model", wan21_model, True):
            logger.info(f"已设置模型节点 {model_node_id} 的模型: {wan21_model}")
        else:
            logger.warning(f"无法设置模型节点 {model_node_id} 的值")
    else:
        # 回退到硬编码的节点ID
        logger.warning("未找到WanVideoModelLoader节点，使用硬编码节点ID 22")
        wan21_model = find_wan21_model()
        # 转换为相对路径
        if wan21_model.startswith("/ComfyUI/models/diffusion_models/"):
            wan21_model = wan21_model.replace("/ComfyUI/models/diffusion_models/", "")
        elif wan21_model.startswith("/ComfyUI/models/checkpoints/"):
            wan21_model = wan21_model.replace("/ComfyUI/models/checkpoints/", "")
        wan21_model = wan21_model.replace("\\", "/")
        set_node_value(prompt, "22", "model", wan21_model, True)
    
    # 文本编码节点
    for node_id, node in prompt.items():
        node_type = node.get("class_type", "")
        if "WanVideoTextEncode" in node_type:
            if "inputs" not in node:
                node["inputs"] = {}
            node["inputs"]["positive_prompt"] = positive_prompt
            node["inputs"]["negative_prompt"] = negative_prompt
            # 同时更新 widgets_values（如果存在）
            if "widgets_values" in node and len(node["widgets_values"]) > 0:
                widgets = node["widgets_values"]
                widgets[0] = positive_prompt
                if negative_prompt and len(widgets) > 1:
                    widgets[1] = negative_prompt
        elif "CLIPTextEncode" in node_type:
            if "inputs" in node and "text" in node["inputs"]:
                current_text = node["inputs"].get("text", "")
                is_negative = any(word in current_text.lower() for word in 
                                 ["bad", "worst", "low quality", "blurry", "static"])
                node["inputs"]["text"] = negative_prompt if is_negative else positive_prompt
    
    # 采样器节点
    for node_id, node in prompt.items():
        if "WanVideoSampler" in node.get("class_type", ""):
            if "widgets_values" in node:
                widgets = node["widgets_values"]
                if len(widgets) > 0:
                    widgets[0] = steps
                if len(widgets) > 1:
                    widgets[1] = seed
                if len(widgets) > 2:
                    widgets[2] = cfg
            if "inputs" not in node:
                node["inputs"] = {}
            node["inputs"].update({"steps": steps, "seed": seed, "cfg": cfg})
    
    # 扩展嵌入节点
    for node_id, node in prompt.items():
        if "WanVideoAddOneToAllExtendEmbeds" in node.get("class_type", ""):
            if "widgets_values" in node and len(node["widgets_values"]) > 0:
                node["widgets_values"][0] = length
            if "inputs" not in node:
                node["inputs"] = {}
            node["inputs"]["num_frames"] = length
    
    # 确保 VHS_VideoCombine 节点正确配置（保存输出）
    vhs_nodes_found = []
    for node_id, node in prompt.items():
        if "VHS_VideoCombine" in node.get("class_type", ""):
            vhs_nodes_found.append(node_id)
            if "inputs" not in node:
                node["inputs"] = {}
            # 确保 save_output 设置为 True
            if "widgets_values" in node:
                widgets = node["widgets_values"]
                if isinstance(widgets, dict):
                    widgets["save_output"] = True
            node["inputs"]["save_output"] = True
            
            # 记录节点配置信息
            images_input = node["inputs"].get("images", "N/A")
            logger.debug(f"VHS_VideoCombine 节点 {node_id}: images输入 = {images_input}, save_output = {node['inputs'].get('save_output', False)}")
            # 从 widgets_values 补充缺失的必需输入
            if "widgets_values" in node and isinstance(node["widgets_values"], dict):
                widgets = node["widgets_values"]
                for key in ["filename_prefix", "loop_count", "frame_rate", "pingpong", "format"]:
                    if key not in node["inputs"] and key in widgets:
                        node["inputs"][key] = widgets[key]
            # 如果仍然缺少必需输入，使用默认值
            if "filename_prefix" not in node["inputs"]:
                node["inputs"]["filename_prefix"] = f"onetotall_output_{node_id}"
            if "loop_count" not in node["inputs"]:
                node["inputs"]["loop_count"] = 0
            if "frame_rate" not in node["inputs"]:
                node["inputs"]["frame_rate"] = 16
            if "pingpong" not in node["inputs"]:
                node["inputs"]["pingpong"] = False
            if "format" not in node["inputs"]:
                node["inputs"]["format"] = "video/h264-mp4"
            logger.info(f"已配置 VHS_VideoCombine 节点 {node_id} 的 save_output=True")
    
    if vhs_nodes_found:
        logger.info(f"发现 {len(vhs_nodes_found)} 个 VHS_VideoCombine 节点: {vhs_nodes_found}")
        # 检查所有 VHS_VideoCombine 节点的输入连接
        for node_id in vhs_nodes_found:
            if node_id in prompt:
                node = prompt[node_id]
                images_input = node.get("inputs", {}).get("images", None)
                if images_input:
                    if isinstance(images_input, list) and len(images_input) > 0:
                        source_node_id = str(images_input[0])
                        if source_node_id in prompt:
                            logger.debug(f"节点 {node_id}: images输入连接到节点 {source_node_id} ✓")
                        else:
                            logger.warning(f"节点 {node_id}: images输入连接到不存在的节点 {source_node_id} ✗")
                    else:
                        logger.warning(f"节点 {node_id}: images输入格式无效: {images_input}")
                else:
                    logger.warning(f"节点 {node_id}: 缺少 images 输入 ✗")


def configure_standard_workflow(prompt, image_path, end_image_path_local, positive_prompt,
                                adjusted_width, adjusted_height, length, steps, seed, cfg, job_input):
    """配置标准工作流"""
    prompt["244"]["inputs"]["image"] = image_path
    prompt["541"]["inputs"]["num_frames"] = length
    if image_path and "541" in prompt:
        prompt["541"]["inputs"]["fun_or_fl2v_model"] = True
    prompt["135"]["inputs"]["positive_prompt"] = positive_prompt
    prompt["220"]["inputs"]["seed"] = seed
    prompt["540"]["inputs"]["seed"] = seed
    prompt["540"]["inputs"]["cfg"] = cfg
    prompt["235"]["inputs"]["value"] = adjusted_width
    prompt["236"]["inputs"]["value"] = adjusted_height
    
    # context_overlap
    user_overlap = job_input.get("context_overlap")
    if user_overlap is not None:
        context_overlap = min(user_overlap, length - 1) if length > 1 else 0
    else:
        context_overlap = max(0, int(length * 0.3)) if length < 50 else min(48, max(0, int(length * 0.6)))
    
    if "498" in prompt:
        prompt["498"]["inputs"]["context_overlap"] = context_overlap
    
    # steps
    if "569" in prompt:
        prompt["569"]["inputs"]["value"] = steps
    if "575" in prompt:
        prompt["575"]["inputs"]["value"] = 4 if steps >= 4 else steps
    
    if end_image_path_local and "617" in prompt:
        prompt["617"]["inputs"]["image"] = end_image_path_local


def handler(job):
    """处理视频生成任务"""
    job_input = job.get("input", {})
    task_id = f"task_{uuid.uuid4()}"
    
    # 处理图像输入
    image_path = None
    for key, input_type in [("image_path", "path"), ("image_url", "url"), ("image_base64", "base64")]:
        if key in job_input:
            image_path = process_input(job_input[key], task_id, "input_image.jpg", input_type)
            break
    if not image_path:
        image_path = "/example_image.png"
    
    # 处理结束图像
    end_image_path_local = None
    for key, input_type in [("end_image_path", "path"), ("end_image_url", "url"), ("end_image_base64", "base64")]:
        if key in job_input:
            end_image_path_local = process_input(job_input[key], task_id, "end_image.jpg", input_type)
            break
    
    # LoRA设置
    lora_pairs = job_input.get("lora_pairs", [])[:4]
    
    # 检测MEGA模型
    mega_model_name = "wan2.2-rapid-mega-aio-nsfw-v12.1.safetensors"
    if os.path.exists(f"/ComfyUI/models/diffusion_models/{mega_model_name}"):
        ensure_model_in_checkpoints(mega_model_name)
        time.sleep(2)
    
    available_models = get_available_models()
    getnode_class_name = get_getnode_class_name()
    
    is_mega_model = False
    for model_name in available_models:
        if any(keyword in model_name.lower() for keyword in ["mega", "aio", "all-in-one", "allinone"]):
            is_mega_model = True
            mega_model_name = model_name
            ensure_model_in_checkpoints(model_name)
            break
    
    # 选择工作流（优先使用 API 格式）
    use_wan21_workflow = job_input.get("use_wan21_workflow", False) or os.path.exists("/Wan21_OneToAllAnimation_example_01.json")
    if use_wan21_workflow:
        # 优先使用 API 格式的 workflow
        if os.path.exists("/Wan21_OneToAllAnimation_example_01_api.json"):
            workflow_file = "/Wan21_OneToAllAnimation_example_01_api.json"
        else:
            workflow_file = "/Wan21_OneToAllAnimation_example_01.json"
    elif is_mega_model:
        workflow_file = "/RapidAIO Mega (V2.5).json"
    else:
        workflow_file = "/new_Wan22_flf2v_api.json" if end_image_path_local else "/new_Wan22_api.json"
    
    workflow_data = load_workflow(workflow_file)
    
    # 参数
    length = job_input.get("length", 81)
    steps = job_input.get("steps", 4)
    seed = job_input.get("seed", 42)
    cfg = job_input.get("cfg", 1.0)
    sampler_name = job_input.get("sampler", "euler_a")
    scheduler = job_input.get("scheduler", "beta")
    
    prompt_input = job_input.get("prompt", "running man, grab the gun")
    if isinstance(prompt_input, list):
        positive_prompt = "\n".join(str(p) for p in prompt_input if p)
    else:
        positive_prompt = str(prompt_input)
    
    prompt_lines = [line.strip() for line in positive_prompt.split("\n") if line.strip()]
    prompt_count = len(prompt_lines)
    if prompt_count > 1:
        total_frames = length * prompt_count
        logger.info(f"多提示词模式: {prompt_count}个提示词，总长度约{total_frames/16:.1f}秒")
    
    negative_prompt = job_input.get("negative_prompt", "")
    adjusted_width = to_nearest_multiple_of_16(job_input.get("width", 480))
    adjusted_height = to_nearest_multiple_of_16(job_input.get("height", 832))
    
    # 转换工作流格式
    if "nodes" in workflow_data:
        logic_node_values = {}
        if is_mega_model:
            logic_node_values = {
                "592": int(length / 16.0),
                "593": job_input.get("megapixel", 0.5),
                "585": job_input.get("overlapping_frames", 1)
            }
        prompt = convert_nodes_to_prompt_format(workflow_data, logic_node_values, getnode_class_name)
    else:
        prompt = workflow_data
    
    # 更新模型
    if not is_mega_model and available_models:
        update_model_in_prompt(prompt, "122", available_models)
        update_model_in_prompt(prompt, "549", available_models)
    elif is_mega_model and available_models:
        if "574" in prompt and "widgets_values" in prompt["574"]:
            current_model = prompt["574"]["widgets_values"][0] if prompt["574"]["widgets_values"] else ""
            mega_models = [m for m in available_models if any(kw in m.lower() for kw in ["mega", "aio", "all-in-one", "allinone"])]
            new_model = mega_models[0] if mega_models else (available_models[0] if available_models else current_model)
            if current_model != new_model:
                prompt["574"]["widgets_values"][0] = new_model
    
    # 配置工作流
    try:
        if is_mega_model:
            logger.info("使用MEGA工作流配置")
            configure_mega_workflow(prompt, job_input, image_path, positive_prompt, negative_prompt,
                                   adjusted_width, adjusted_height, length, steps, seed, cfg,
                                   sampler_name, scheduler, available_models)
        elif use_wan21_workflow:
            logger.info("使用Wan21工作流配置")
            configure_wan21_workflow(prompt, job_input, image_path, positive_prompt, negative_prompt,
                                    adjusted_width, adjusted_height, length, steps, seed, cfg, task_id)
        else:
            logger.info("使用标准Wan22工作流配置")
            configure_standard_workflow(prompt, image_path, end_image_path_local, positive_prompt,
                                       adjusted_width, adjusted_height, length, steps, seed, cfg, job_input)
        logger.info("工作流配置完成")
    except Exception as e:
        logger.error(f"工作流配置失败: {e}")
        raise
    
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
        
        # LoadWanVideoT5TextEncoder: 修正 offload_device 设置并填充缺失的必需输入
        if "LoadWanVideoT5TextEncoder" in class_type:
            # 从 widgets_values 中提取所有必需参数并设置到 inputs
            if "widgets_values" in node and isinstance(node["widgets_values"], list):
                widgets = node["widgets_values"]
                # widgets_values 格式: [model_name, precision/dtype, offload_device, offload_mode]
                if len(widgets) >= 1 and "model_name" not in node["inputs"]:
                    node["inputs"]["model_name"] = widgets[0]
                if len(widgets) >= 2 and "precision" not in node["inputs"]:
                    # precision 可能是 dtype 的别名
                    precision_value = widgets[1]
                    node["inputs"]["precision"] = precision_value
                if len(widgets) >= 3:
                    offload_dev = widgets[2]
                    # 如果 offload_device 设置为 "offload_device" 可能导致 CUDA 错误，改为 "main_device"
                    # 这可以避免在模型前向传播时出现设备转换错误
                    if offload_dev == "offload_device":
                        offload_dev = "main_device"
                        logger.warning(f"节点 {node_id}: 将 offload_device 从 'offload_device' 改为 'main_device' 以避免 CUDA 错误")
                    # 确保 offload_device 是有效的值
                    if offload_dev not in ["main_device", "offload_device", "cpu"]:
                        offload_dev = "main_device"
                    node["inputs"]["offload_device"] = offload_dev
                if len(widgets) >= 4 and "offload_mode" not in node["inputs"]:
                    node["inputs"]["offload_mode"] = widgets[3] if len(widgets) > 3 else "disabled"
            
            # 确保所有必需输入都存在
            if "model_name" not in node["inputs"]:
                logger.warning(f"节点 {node_id} (LoadWanVideoT5TextEncoder): 缺少 model_name，尝试使用默认值")
                # 尝试查找可用的 T5 模型
                try:
                    url = f"http://{server_address}:8188/object_info"
                    with urllib.request.urlopen(url, timeout=5) as response:
                        object_info = json.loads(response.read())
                        if "LoadWanVideoT5TextEncoder" in object_info:
                            t5_info = object_info["LoadWanVideoT5TextEncoder"]
                            t5_models = (t5_info.get("input", {}).get("required", {}).get("model_name") or [])
                            if isinstance(t5_models, list) and t5_models:
                                if isinstance(t5_models[0], list):
                                    t5_models = t5_models[0]
                                if t5_models:
                                    node["inputs"]["model_name"] = t5_models[0]
                                    logger.info(f"节点 {node_id}: 使用默认 T5 模型 {t5_models[0]}")
                except Exception as e:
                    logger.warning(f"无法获取 T5 模型列表: {e}")
            
            if "precision" not in node["inputs"]:
                node["inputs"]["precision"] = "float16"  # 默认值
        
        # WanVideoModelLoader: 修正 quantization、base_precision 和 load_device
        if "WanVideoModelLoader" in class_type:
            # 从 widgets_values 填充缺失的必需输入
            if "widgets_values" in node and isinstance(node["widgets_values"], list):
                widgets = node["widgets_values"]
                # widgets_values 格式: [model_name, dtype/base_precision, quantization, load_device, attention_type, compile_mode]
                if len(widgets) >= 2 and "base_precision" not in node["inputs"]:
                    node["inputs"]["base_precision"] = widgets[1]
                if len(widgets) >= 3:
                    quant = widgets[2]
                    if quant not in ["disabled", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e4m3fn_scaled", "fp8_e4m3fn_scaled_fast", "fp8_e5m2", "fp8_e5m2_fast", "fp8_e5m2_scaled", "fp8_e5m2_scaled_fast"]:
                        quant = "disabled"
                    node["inputs"]["quantization"] = quant
                if len(widgets) >= 4:
                    load_dev = widgets[3]
                    # 如果 load_device 设置为 "offload_device" 可能导致 CUDA 错误，改为 "main_device"
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
                # 如果没有 quantization，设置默认值
                node["inputs"]["quantization"] = "disabled"
            
            # 确保 base_precision 存在
            if "base_precision" not in node["inputs"]:
                node["inputs"]["base_precision"] = "float16"  # 默认值
            
            # 处理 load_device：从 inputs 中获取（如果已设置）
            if "load_device" in node["inputs"]:
                load_dev = node["inputs"]["load_device"]
                if load_dev == "offload_device":
                    load_dev = "main_device"
                    logger.warning(f"节点 {node_id}: 将 load_device 从 'offload_device' 改为 'main_device' 以避免 CUDA 错误")
                if load_dev not in ["main_device", "offload_device"]:
                    node["inputs"]["load_device"] = "main_device"
            else:
                node["inputs"]["load_device"] = "main_device"  # 默认值
        
        # WanVideoVAELoader: 规范化 model_name 路径并确保存在
        if "WanVideoVAELoader" in class_type:
            # 从 widgets_values 填充缺失的 model_name
            if "widgets_values" in node and isinstance(node["widgets_values"], list):
                widgets = node["widgets_values"]
                if len(widgets) >= 1 and "model_name" not in node["inputs"]:
                    node["inputs"]["model_name"] = widgets[0]
            
            if "model_name" in node["inputs"]:
                model_name = node["inputs"]["model_name"]
                if isinstance(model_name, str):
                    model_name = model_name.replace("\\", "/")
                    # 去除路径前缀，只保留文件名
                    if "/" in model_name:
                        model_name = model_name.split("/")[-1]
                    node["inputs"]["model_name"] = model_name
            elif "widgets_values" not in node or not node.get("widgets_values"):
                # 如果没有 model_name 且没有 widgets_values，设置默认值
                logger.warning(f"节点 {node_id} (WanVideoVAELoader): 缺少 model_name，尝试使用默认值")
                # 尝试查找可用的 VAE 模型
                try:
                    url = f"http://{server_address}:8188/object_info"
                    with urllib.request.urlopen(url, timeout=5) as response:
                        object_info = json.loads(response.read())
                        if "WanVideoVAELoader" in object_info:
                            vae_info = object_info["WanVideoVAELoader"]
                            vae_models = (vae_info.get("input", {}).get("required", {}).get("model_name") or [])
                            if isinstance(vae_models, list) and vae_models:
                                if isinstance(vae_models[0], list):
                                    vae_models = vae_models[0]
                                if vae_models:
                                    default_vae = vae_models[0]
                                    if isinstance(default_vae, str):
                                        default_vae = default_vae.split("/")[-1]
                                    node["inputs"]["model_name"] = default_vae
                                    logger.info(f"节点 {node_id}: 使用默认 VAE 模型 {default_vae}")
                except Exception as e:
                    logger.warning(f"无法获取 VAE 模型列表: {e}")
        
        # OnnxDetectionModelLoader: 规范化模型路径
        if "OnnxDetectionModelLoader" in class_type:
            if "yolo_model" in node["inputs"]:
                yolo_model = node["inputs"]["yolo_model"]
                if isinstance(yolo_model, str):
                    yolo_model = yolo_model.replace("\\", "/")
                    # 去除 onnx/ 前缀
                    if yolo_model.startswith("onnx/"):
                        yolo_model = yolo_model.replace("onnx/", "")
                    node["inputs"]["yolo_model"] = yolo_model
            if "vitpose_model" in node["inputs"]:
                vitpose_model = node["inputs"]["vitpose_model"]
                if isinstance(vitpose_model, str):
                    vitpose_model = vitpose_model.replace("\\", "/")
                    # 去除路径前缀，只保留文件名
                    if "/" in vitpose_model:
                        vitpose_model = vitpose_model.split("/")[-1]
                    node["inputs"]["vitpose_model"] = vitpose_model
        
        # VHS_VideoCombine: 检查并修复 images 输入类型
        if "VHS_VideoCombine" in class_type:
            if "images" in node["inputs"]:
                images_input = node["inputs"]["images"]
                if isinstance(images_input, list) and len(images_input) >= 1:
                    source_node_id = str(images_input[0])
                    if source_node_id in prompt:
                        source_node = prompt[source_node_id]
                        source_class = source_node.get("class_type", "")
                        source_type = source_node.get("type", "")
                        
                        # 检查源节点的输出定义（从原始工作流数据中获取）
                        # 只有在 UI 格式的工作流中才需要检查（有 nodes 数组）
                        original_node = None
                        if "nodes" in workflow_data:
                            for orig_node in workflow_data.get("nodes", []):
                                if str(orig_node.get("id")) == source_node_id:
                                    original_node = orig_node
                                    break
                        
                        if original_node:
                            outputs = original_node.get("outputs", [])
                            if len(outputs) > 0:
                                current_output_idx = images_input[1] if len(images_input) > 1 else 0
                                current_output_type = None
                                
                                # 检查当前连接的输出类型
                                if current_output_idx < len(outputs):
                                    current_output = outputs[current_output_idx]
                                    current_output_type = current_output.get("type", "")
                                
                                # 如果当前输出是 WANVIDIMAGE_EMBEDS，需要找到 IMAGE 输出
                                if current_output_type == "WANVIDIMAGE_EMBEDS":
                                    # 查找 IMAGE 类型的输出
                                    image_output_idx = None
                                    for idx, output in enumerate(outputs):
                                        output_type = output.get("type", "")
                                        output_name = output.get("name", "").lower()
                                        
                                        # 优先查找名称包含 "image" 或 "extend" 的 IMAGE 输出
                                        if output_type == "IMAGE":
                                            if ("extended_images" in output_name or "extend" in output_name or 
                                                "image" in output_name):
                                                image_output_idx = idx
                                                break
                                            # 如果没有找到名称匹配的，使用第一个 IMAGE 输出
                                            if image_output_idx is None:
                                                image_output_idx = idx
                                    
                                    # 如果找到了 IMAGE 输出，使用它
                                    if image_output_idx is not None:
                                        if len(images_input) < 2:
                                            images_input.append(image_output_idx)
                                        else:
                                            images_input[1] = image_output_idx
                                        logger.info(f"节点 {node_id} (VHS_VideoCombine): 修正 images 输入从节点 {source_node_id} "
                                                   f"的输出索引 {current_output_idx} (WANVIDIMAGE_EMBEDS) -> {image_output_idx} (IMAGE)")
                                    else:
                                        logger.warning(f"节点 {node_id} (VHS_VideoCombine): 源节点 {source_node_id} "
                                                     f"({source_class}) 只输出 WANVIDIMAGE_EMBEDS，没有 IMAGE 输出")
                                # 如果当前输出已经是 IMAGE，不需要修改
                                elif current_output_type == "IMAGE":
                                    # 确保输出索引正确设置
                                    if len(images_input) < 2:
                                        images_input.append(current_output_idx)
                                # 处理 WanVideoAddOneToAllExtendEmbeds 节点
                                elif ("WanVideoAddOneToAllExtendEmbeds" in source_class or 
                                      "WanVideoAddOneToAllExtendEmbeds" in str(source_type) or
                                      "extend" in source_node.get("title", "").lower()):
                                    # 查找 extended_images 输出（IMAGE 类型）
                                    extended_images_idx = None
                                    for idx, output in enumerate(outputs):
                                        output_name = output.get("name", "").lower()
                                        output_type = output.get("type", "")
                                        # 优先查找 extended_images 输出
                                        if ("extended_images" in output_name or "extend" in output_name) and output_type == "IMAGE":
                                            extended_images_idx = idx
                                            break
                                        # 如果没有找到名称匹配的，查找第一个 IMAGE 类型的输出
                                        if extended_images_idx is None and output_type == "IMAGE":
                                            extended_images_idx = idx
                                    
                                    # 如果找到了 IMAGE 输出，确保使用正确的索引
                                    if extended_images_idx is not None:
                                        if len(images_input) < 2 or images_input[1] != extended_images_idx:
                                            logger.info(f"节点 {node_id} (VHS_VideoCombine): 修正 images 输入来自节点 {source_node_id} "
                                                      f"的输出索引 {images_input[1] if len(images_input) > 1 else 'None'} -> {extended_images_idx}")
                                            if len(images_input) < 2:
                                                images_input.append(extended_images_idx)
                                            else:
                                                images_input[1] = extended_images_idx
                                    else:
                                        logger.warning(f"节点 {node_id} (VHS_VideoCombine): 源节点 {source_node_id} 没有找到 IMAGE 类型的输出")
                                # 如果源节点类型未知，但当前输出是 WANVIDIMAGE_EMBEDS，也尝试修复
                                elif current_output_type == "WANVIDIMAGE_EMBEDS":
                                    # 查找 IMAGE 类型的输出
                                    image_output_idx = None
                                    for idx, output in enumerate(outputs):
                                        output_type = output.get("type", "")
                                        if output_type == "IMAGE":
                                            image_output_idx = idx
                                            break
                                    
                                    if image_output_idx is not None:
                                        if len(images_input) < 2:
                                            images_input.append(image_output_idx)
                                        else:
                                            images_input[1] = image_output_idx
                                        logger.info(f"节点 {node_id} (VHS_VideoCombine): 修正 images 输入从节点 {source_node_id} "
                                                   f"的输出索引 {current_output_idx} (WANVIDIMAGE_EMBEDS) -> {image_output_idx} (IMAGE)")
                            else:
                                logger.warning(f"节点 {node_id} (VHS_VideoCombine): 源节点 {source_node_id} 没有输出定义")
                        else:
                            logger.warning(f"节点 {node_id} (VHS_VideoCombine): 无法在原始工作流中找到节点 {source_node_id}")
        
        # WanVideoDecode/WanVideoEncode: 验证并修正 tile 参数（在修正值类型错误部分之后再次验证）
        if "WanVideoDecode" in class_type or "WanVideoEncode" in class_type:
            tile_x = node["inputs"].get("tile_x", 0)
            tile_y = node["inputs"].get("tile_y", 0)
            tile_stride_x = node["inputs"].get("tile_stride_x", 0)
            tile_stride_y = node["inputs"].get("tile_stride_y", 0)
            
            # 再次验证 tile 参数
            # 根据错误信息，某些节点不允许 tile 为 0，需要至少 64
            # 如果 tile 为 0，设置为默认值以避免验证错误
            if tile_x == 0:
                # 设置为默认值以满足最小要求
                node["inputs"]["tile_x"] = 272  # 默认值
                tile_x = 272
                node["inputs"]["tile_stride_x"] = 144  # 默认值
                tile_stride_x = 144
                # 如果用户想禁用 tiling，应该设置 enable_vae_tiling = False
                node["inputs"]["enable_vae_tiling"] = False
                logger.info(f"节点 {node_id}: tile_x 为 0，设置为默认值 272（tiling 已禁用）")
            elif tile_x > 0:
                # 确保满足最小值要求
                if tile_x < 64:
                    node["inputs"]["tile_x"] = 64
                    tile_x = 64
                if tile_stride_x < 32:
                    node["inputs"]["tile_stride_x"] = 32
                    tile_stride_x = 32
                # 确保 tile > tile_stride
                if tile_stride_x >= tile_x:
                    node["inputs"]["tile_stride_x"] = max(32, tile_x - 32)
                    logger.warning(f"节点 {node_id}: 修正 tile_stride_x 必须小于 tile_x")
            
            if tile_y == 0:
                # 设置为默认值以满足最小要求
                node["inputs"]["tile_y"] = 272  # 默认值
                tile_y = 272
                node["inputs"]["tile_stride_y"] = 128  # 默认值
                tile_stride_y = 128
                # 如果用户想禁用 tiling，应该设置 enable_vae_tiling = False
                node["inputs"]["enable_vae_tiling"] = False
                logger.info(f"节点 {node_id}: tile_y 为 0，设置为默认值 272（tiling 已禁用）")
            elif tile_y > 0:
                # 确保满足最小值要求
                if tile_y < 64:
                    node["inputs"]["tile_y"] = 64
                    tile_y = 64
                if tile_stride_y < 32:
                    node["inputs"]["tile_stride_y"] = 32
                    tile_stride_y = 32
                # 确保 tile > tile_stride
                if tile_stride_y >= tile_y:
                    node["inputs"]["tile_stride_y"] = max(32, tile_y - 32)
                    logger.warning(f"节点 {node_id}: 修正 tile_stride_y 必须小于 tile_y")
        
        # WanVideoSampler: 确保所有必需输入都已设置
        if "WanVideoSampler" in class_type:
            if "shift" not in node["inputs"]:
                node["inputs"]["shift"] = 0.0
            if "riflex_freq_index" not in node["inputs"]:
                node["inputs"]["riflex_freq_index"] = 0
            if "force_offload" not in node["inputs"]:
                node["inputs"]["force_offload"] = False
    
    # 验证节点连接的类型匹配（检测 WANVIDIMAGE_EMBEDS vs IMAGE 不匹配）
    logger.info("验证节点连接类型匹配...")
    type_mismatch_warnings = []
    type_mismatch_fixes = []
    
    # 首先，检查并修复所有 VHS_VideoCombine 节点的类型不匹配
    for node_id, node in prompt.items():
        class_type = node.get("class_type", "")
        if "VHS_VideoCombine" not in class_type or "inputs" not in node:
            continue
        
        if "images" in node["inputs"]:
            images_input = node["inputs"]["images"]
            if isinstance(images_input, list) and len(images_input) >= 1:
                source_node_id = str(images_input[0])
                if source_node_id in prompt:
                    source_node = prompt[source_node_id]
                    source_class = source_node.get("class_type", "")
                    
                    # 检查源节点是否输出 WANVIDIMAGE_EMBEDS
                    # 需要从原始工作流数据中查找输出类型
                    if "nodes" in workflow_data:
                        for orig_node in workflow_data.get("nodes", []):
                            if str(orig_node.get("id")) == source_node_id:
                                outputs = orig_node.get("outputs", [])
                                if not outputs:
                                    break
                                
                                # 获取当前连接的输出索引
                                current_output_idx = images_input[1] if len(images_input) > 1 else 0
                                
                                # 检查当前连接的输出类型
                                current_output_type = None
                                if current_output_idx < len(outputs):
                                    current_output = outputs[current_output_idx]
                                    current_output_type = current_output.get("type", "")
                                
                                # 如果源节点是 WanVideoAddOneToAllExtendEmbeds，总是查找 IMAGE 输出
                                if "WanVideoAddOneToAllExtendEmbeds" in source_class or current_output_type == "WANVIDIMAGE_EMBEDS":
                                    # 查找 IMAGE 类型的输出
                                    image_output_idx = None
                                    for img_idx, img_output in enumerate(outputs):
                                        output_type = img_output.get("type", "")
                                        output_name = img_output.get("name", "").lower()
                                        
                                        # 优先查找 extended_images 或包含 "image" 的输出
                                        if output_type == "IMAGE":
                                            if ("extended_images" in output_name or "extend" in output_name or 
                                                "image" in output_name):
                                                image_output_idx = img_idx
                                                break
                                            # 如果没有找到名称匹配的，使用第一个 IMAGE 输出
                                            if image_output_idx is None:
                                                image_output_idx = img_idx
                                    
                                    if image_output_idx is not None:
                                        # 修复：使用 IMAGE 输出索引
                                        if len(images_input) < 2:
                                            images_input.append(image_output_idx)
                                        else:
                                            images_input[1] = image_output_idx
                                        type_mismatch_fixes.append(
                                            f"节点 {node_id} (VHS_VideoCombine): 修正 images 输入从节点 {source_node_id} "
                                            f"的输出索引 {current_output_idx} ({current_output_type or 'unknown'}) -> {image_output_idx} (IMAGE)"
                                        )
                                        logger.info(type_mismatch_fixes[-1])
                                    else:
                                        # 如果找不到 IMAGE 输出，记录警告
                                        type_mismatch_warnings.append(
                                            f"节点 {node_id} (VHS_VideoCombine): 源节点 {source_node_id} "
                                            f"({source_class}) 只输出 WANVIDIMAGE_EMBEDS，没有 IMAGE 输出"
                                        )
                                break
    
    # 检查其他可能的类型不匹配
    for node_id, node in prompt.items():
        class_type = node.get("class_type", "")
        if "inputs" not in node:
            continue
        
        # 检查可能导致类型不匹配的常见节点
        for input_name, input_value in node["inputs"].items():
            if isinstance(input_value, list) and len(input_value) >= 1:
                source_node_id = str(input_value[0])
                if source_node_id in prompt:
                    source_node = prompt[source_node_id]
                    source_class = source_node.get("class_type", "")
                    
                    # 检查常见的类型不匹配情况
                    if "WanVideoAddOneToAllExtendEmbeds" in source_class:
                        # 如果目标节点期望 IMAGE 类型输入
                        if input_name in ["images", "image"] and "VHS_VideoCombine" not in class_type:
                            # 记录警告，但可能无法自动修复
                            type_mismatch_warnings.append(
                                f"节点 {node_id} ({class_type}) 的输入 {input_name} 连接到节点 {source_node_id} "
                                f"({source_class})，可能存在类型不匹配 (WANVIDIMAGE_EMBEDS vs IMAGE)"
                            )
    
    if type_mismatch_fixes:
        logger.info(f"修复了 {len(type_mismatch_fixes)} 个类型不匹配问题")
    
    if type_mismatch_warnings:
        logger.warning(f"发现 {len(type_mismatch_warnings)} 个潜在的类型不匹配:")
        for warning in type_mismatch_warnings[:5]:  # 只显示前5个
            logger.warning(f"  {warning}")
        if len(type_mismatch_warnings) > 5:
            logger.warning(f"  ... 还有 {len(type_mismatch_warnings) - 5} 个警告未显示")
    
    # 验证并修复缺失的节点连接（KeyError 问题）
    logger.info("验证节点连接完整性...")
    missing_node_errors = []
    missing_node_fixes = []
    
    # 收集需要删除的输入项，避免在迭代时修改字典
    inputs_to_remove = []
    
    for node_id, node in prompt.items():
        class_type = node.get("class_type", "")
        if "inputs" not in node:
            continue
        
        # 使用 list() 创建副本以避免迭代时修改字典
        for input_name, input_value in list(node["inputs"].items()):
            if isinstance(input_value, list) and len(input_value) >= 1:
                source_node_id = str(input_value[0])
                if source_node_id not in prompt:
                    missing_node_errors.append(
                        f"节点 {node_id} ({class_type}) 的输入 {input_name} 引用了不存在的节点 {source_node_id}"
                    )
                    # 尝试从原始工作流中查找该节点或替代节点
                    if "nodes" in workflow_data:
                        found_alternative = False
                        alternative_node_id = None
                        
                        # 首先检查是否是 SetNode/GetNode 引用的节点
                        for orig_node in workflow_data.get("nodes", []):
                            orig_node_id = str(orig_node.get("id"))
                            orig_node_type = orig_node.get("type", "")
                            
                            # 检查是否是 SetNode 名称匹配
                            if orig_node_type == "SetNode":
                                widgets = orig_node.get("widgets_values", [])
                                if widgets and isinstance(widgets, list) and len(widgets) > 0:
                                    if widgets[0] == source_node_id:
                                        # 这是一个 SetNode 名称，需要找到对应的实际节点
                                        # 查找连接到这个 SetNode 的实际节点
                                        for link in workflow_data.get("links", []):
                                            if len(link) >= 6 and str(link[1]) == orig_node_id:
                                                # 找到连接到 SetNode 的源节点
                                                actual_source_id = str(link[1])
                                                if actual_source_id in prompt:
                                                    alternative_node_id = actual_source_id
                                                    found_alternative = True
                                                    break
                                        if found_alternative:
                                            break
                            
                            # 检查是否是 GetNode 引用的节点
                            if orig_node_type == "GetNode" or "GetNode" in str(orig_node_type):
                                widgets = orig_node.get("widgets_values", [])
                                if widgets and isinstance(widgets, list) and len(widgets) > 0:
                                    if widgets[0] == source_node_id:
                                        # 这是一个 GetNode 名称，需要找到对应的 SetNode
                                        for sn_node in workflow_data.get("nodes", []):
                                            if sn_node.get("type") == "SetNode":
                                                sn_widgets = sn_node.get("widgets_values", [])
                                                if sn_widgets and isinstance(sn_widgets, list) and len(sn_widgets) > 0:
                                                    if sn_widgets[0] == source_node_id:
                                                        # 找到对应的 SetNode，然后找到它的源节点
                                                        for link in workflow_data.get("links", []):
                                                            if len(link) >= 6 and str(link[1]) == str(sn_node.get("id")):
                                                                actual_source_id = str(link[1])
                                                                if actual_source_id in prompt:
                                                                    alternative_node_id = actual_source_id
                                                                    found_alternative = True
                                                                    break
                                                        if found_alternative:
                                                            break
                                        if found_alternative:
                                            break
                        
                        if found_alternative and alternative_node_id:
                            # 使用替代节点
                            node["inputs"][input_name] = [alternative_node_id, input_value[1] if len(input_value) > 1 else 0]
                            missing_node_fixes.append(
                                f"节点 {node_id}: 将输入 {input_name} 从不存在的节点 {source_node_id} 改为 {alternative_node_id}"
                            )
                            logger.info(missing_node_fixes[-1])
                        else:
                            # 如果找不到替代节点，尝试查找同类型的节点
                            # 根据输入类型查找合适的替代节点
                            if input_name in ["image", "images"]:
                                # 查找 LoadImage 节点
                                image_node_id = find_node_by_class_type(prompt, "LoadImage")
                                if image_node_id:
                                    node["inputs"][input_name] = [image_node_id, 0]
                                    logger.warning(f"节点 {node_id}: 将输入 {input_name} 从不存在的节点 {source_node_id} 改为图像节点 {image_node_id}")
                                else:
                                    logger.warning(f"节点 {node_id}: 无法修复输入 {input_name}，引用的节点 {source_node_id} 不存在且找不到替代节点")
                            elif input_name in ["pose_images", "pose"]:
                                # 查找姿态相关节点
                                pose_node_id = find_node_by_class_type(prompt, "PoseDetection")
                                if pose_node_id:
                                    node["inputs"][input_name] = [pose_node_id, 0]
                                    logger.warning(f"节点 {node_id}: 将输入 {input_name} 从不存在的节点 {source_node_id} 改为姿态节点 {pose_node_id}")
                                else:
                                    logger.warning(f"节点 {node_id}: 无法修复输入 {input_name}，引用的节点 {source_node_id} 不存在且找不到替代节点")
                            else:
                                # 对于其他输入，收集需要删除的项
                                logger.warning(f"节点 {node_id}: 移除指向不存在节点 {source_node_id} 的连接 {input_name}")
                                inputs_to_remove.append((node_id, input_name))
    
    # 在迭代完成后删除收集的输入项
    for node_id, input_name in inputs_to_remove:
        if node_id in prompt and "inputs" in prompt[node_id] and input_name in prompt[node_id]["inputs"]:
            del prompt[node_id]["inputs"][input_name]
    
    if missing_node_fixes:
        logger.info(f"修复了 {len(missing_node_fixes)} 个缺失节点连接")
    
    if missing_node_errors:
        logger.warning(f"发现 {len(missing_node_errors)} 个缺失节点连接:")
        for error in missing_node_errors[:5]:
            logger.warning(f"  {error}")
        if len(missing_node_errors) > 5:
            logger.warning(f"  ... 还有 {len(missing_node_errors) - 5} 个错误未显示")
    
    # 最终修复：再次检查所有 VHS_VideoCombine 节点的类型匹配（在提交前最后一次）
    logger.info("最终检查 VHS_VideoCombine 节点类型匹配...")
    for node_id, node in prompt.items():
        if "VHS_VideoCombine" not in node.get("class_type", "") or "inputs" not in node:
            continue
        
        if "images" in node["inputs"]:
            images_input = node["inputs"]["images"]
            if isinstance(images_input, list) and len(images_input) >= 1:
                source_node_id = str(images_input[0])
                if source_node_id in prompt:
                    source_node = prompt[source_node_id]
                    source_class = source_node.get("class_type", "")
                    
                    # 如果源节点是 WanVideoAddOneToAllExtendEmbeds，确保使用 IMAGE 输出
                    if "WanVideoAddOneToAllExtendEmbeds" in source_class:
                        if "nodes" in workflow_data:
                            for orig_node in workflow_data.get("nodes", []):
                                if str(orig_node.get("id")) == source_node_id:
                                    outputs = orig_node.get("outputs", [])
                                    if outputs:
                                        # 查找 IMAGE 类型的输出
                                        image_output_idx = None
                                        for idx, output in enumerate(outputs):
                                            output_type = output.get("type", "")
                                            output_name = output.get("name", "").lower()
                                            if output_type == "IMAGE":
                                                # 优先查找 extended_images
                                                if "extended_images" in output_name or "extend" in output_name:
                                                    image_output_idx = idx
                                                    break
                                                # 否则使用第一个 IMAGE 输出
                                                if image_output_idx is None:
                                                    image_output_idx = idx
                                        
                                        if image_output_idx is not None:
                                            current_idx = images_input[1] if len(images_input) > 1 else 0
                                            if current_idx != image_output_idx:
                                                if len(images_input) < 2:
                                                    images_input.append(image_output_idx)
                                                else:
                                                    images_input[1] = image_output_idx
                                                logger.info(f"节点 {node_id} (VHS_VideoCombine): 最终修正 images 输入从节点 {source_node_id} "
                                                          f"的输出索引 {current_idx} -> {image_output_idx} (IMAGE)")
                                    break
    
    # 确保 GetImageSizeAndCount 节点有 image 输入
    for node_id, node in prompt.items():
        if "GetImageSizeAndCount" in node.get("class_type", ""):
            if "inputs" not in node:
                node["inputs"] = {}
            if "image" not in node["inputs"]:
                # 尝试查找 LoadImage 节点
                image_node_id = find_node_by_class_type(prompt, "LoadImage")
                if image_node_id:
                    node["inputs"]["image"] = [image_node_id, 0]
                    logger.info(f"节点 {node_id} (GetImageSizeAndCount): 连接到图像节点 {image_node_id}")
                else:
                    logger.warning(f"节点 {node_id} (GetImageSizeAndCount): 缺少 image 输入且找不到 LoadImage 节点")
    
    # 最终验证：确保所有必需输入都已设置（在提交前最后一次检查）
    logger.info("最终验证必需输入...")
    for node_id, node in prompt.items():
        class_type = node.get("class_type", "")
        if "inputs" not in node:
            node["inputs"] = {}
        
        # WanVideoModelLoader: 确保 quantization 和 base_precision 存在
        if "WanVideoModelLoader" in class_type:
            if "quantization" not in node["inputs"]:
                node["inputs"]["quantization"] = "disabled"
                logger.info(f"节点 {node_id}: 设置默认 quantization=disabled")
            if "base_precision" not in node["inputs"]:
                node["inputs"]["base_precision"] = "float16"
                logger.info(f"节点 {node_id}: 设置默认 base_precision=float16")
        
        # LoadWanVideoT5TextEncoder: 确保 precision 和 model_name 存在
        if "LoadWanVideoT5TextEncoder" in class_type:
            if "precision" not in node["inputs"]:
                node["inputs"]["precision"] = "float16"
                logger.info(f"节点 {node_id}: 设置默认 precision=float16")
            if "model_name" not in node["inputs"]:
                # 尝试从 API 获取默认值
                try:
                    url = f"http://{server_address}:8188/object_info"
                    with urllib.request.urlopen(url, timeout=5) as response:
                        object_info = json.loads(response.read())
                        if "LoadWanVideoT5TextEncoder" in object_info:
                            t5_info = object_info["LoadWanVideoT5TextEncoder"]
                            t5_models = (t5_info.get("input", {}).get("required", {}).get("model_name") or [])
                            if isinstance(t5_models, list) and t5_models:
                                if isinstance(t5_models[0], list):
                                    t5_models = t5_models[0]
                                if t5_models:
                                    node["inputs"]["model_name"] = t5_models[0]
                                    logger.info(f"节点 {node_id}: 设置默认 model_name={t5_models[0]}")
                except Exception as e:
                    logger.warning(f"节点 {node_id}: 无法获取 T5 模型列表: {e}")
        
        # WanVideoVAELoader: 确保 model_name 存在
        if "WanVideoVAELoader" in class_type:
            if "model_name" not in node["inputs"]:
                # 尝试从 API 获取默认值
                try:
                    url = f"http://{server_address}:8188/object_info"
                    with urllib.request.urlopen(url, timeout=5) as response:
                        object_info = json.loads(response.read())
                        if "WanVideoVAELoader" in object_info:
                            vae_info = object_info["WanVideoVAELoader"]
                            vae_models = (vae_info.get("input", {}).get("required", {}).get("model_name") or [])
                            if isinstance(vae_models, list) and vae_models:
                                if isinstance(vae_models[0], list):
                                    vae_models = vae_models[0]
                                if vae_models:
                                    default_vae = vae_models[0]
                                    if isinstance(default_vae, str):
                                        default_vae = default_vae.split("/")[-1]
                                    node["inputs"]["model_name"] = default_vae
                                    logger.info(f"节点 {node_id}: 设置默认 model_name={default_vae}")
                except Exception as e:
                    logger.warning(f"节点 {node_id}: 无法获取 VAE 模型列表: {e}")
        
        # WanVideoLoraSelect: 修复 LoRA 路径格式
        if "WanVideoLoraSelect" in class_type:
            if "lora" in node["inputs"]:
                lora_path = node["inputs"]["lora"]
                if isinstance(lora_path, str) and lora_path:
                    # 规范化路径
                    lora_path = lora_path.replace("\\", "/")
                    # 去除 ComfyUI/models/loras/ 前缀
                    if lora_path.startswith("ComfyUI/models/loras/"):
                        lora_path = lora_path.replace("ComfyUI/models/loras/", "")
                    elif lora_path.startswith("/ComfyUI/models/loras/"):
                        lora_path = lora_path.replace("/ComfyUI/models/loras/", "")
                    # 如果路径包含子目录但不包含 WanVideo/ 前缀，添加前缀
                    if "/" in lora_path and not lora_path.startswith("WanVideo/"):
                        lora_path = "WanVideo/" + lora_path
                    node["inputs"]["lora"] = lora_path
                    logger.info(f"节点 {node_id}: 规范化 LoRA 路径为 {lora_path}")
    
    logger.info("输入填充和值修正完成")
    
    # LoRA设置
    if lora_pairs and not is_mega_model:
        for i, lora_pair in enumerate(lora_pairs):
            if i < 4:
                lora_high = lora_pair.get("high")
                lora_low = lora_pair.get("low")
                lora_high_weight = lora_pair.get("high_weight", 1.0)
                lora_low_weight = lora_pair.get("low_weight", 1.0)
                
                if lora_high and "279" in prompt:
                    prompt["279"]["inputs"][f"lora_{i}"] = lora_high
                    prompt["279"]["inputs"][f"strength_{i}"] = lora_high_weight
                if lora_low and "553" in prompt:
                    prompt["553"]["inputs"][f"lora_{i}"] = lora_low
                    prompt["553"]["inputs"][f"strength_{i}"] = lora_low_weight
    
    # 连接ComfyUI
    http_url = f"http://{server_address}:8188/"
    for attempt in range(180):
        try:
            urllib.request.urlopen(http_url, timeout=5)
            break
        except Exception:
            if attempt == 179:
                raise Exception("无法连接到ComfyUI服务器")
            time.sleep(1)
    
    ws_url = f"ws://{server_address}:8188/ws?clientId={client_id}"
    ws = websocket.WebSocket()
    for attempt in range(36):
        try:
            ws.connect(ws_url)
            break
        except Exception:
            if attempt == 35:
                raise Exception("WebSocket连接超时")
            time.sleep(5)
    
    try:
        videos, execution_order = get_videos(ws, prompt, is_mega_model)
        ws.close()
        
        # 查找输出视频，优先选择最后执行的 VHS_VideoCombine 节点
        video_output_nodes = [node_id for node_id in videos if videos[node_id]]
        
        if not video_output_nodes:
            logger.error("未找到生成的视频")
            logger.error(f"可用的输出节点: {list(videos.keys())}")
            for node_id, video_list in videos.items():
                logger.error(f"  节点 {node_id}: {len(video_list)} 个视频")
            return {"error": "未找到视频输出，请检查工作流配置和ComfyUI日志"}
        
        # 优先选择策略：
        # 1. 优先选择 save_output=True 的 VHS_VideoCombine 节点
        # 2. 如果没有，选择 order 最大的节点（从工作流数据中获取）
        # 3. 如果还是没有，选择最后执行的节点
        # 4. 最后选择 ID 最大的节点
        selected_node_id = None
        
        # 确保节点ID类型一致（都转换为字符串）
        video_output_nodes_str = [str(node_id) for node_id in video_output_nodes]
        execution_order_str = [str(node_id) for node_id in execution_order]
        
        # 从工作流数据中获取节点的 order 信息
        node_orders = {}
        if "nodes" in workflow_data:
            for orig_node in workflow_data.get("nodes", []):
                node_id = str(orig_node.get("id"))
                node_order = orig_node.get("order", 0)
                node_orders[node_id] = node_order
        
        # 策略1: 优先选择 save_output=True 的 VHS_VideoCombine 节点
        save_output_nodes = []
        for node_id_str in video_output_nodes_str:
            if node_id_str in prompt:
                node = prompt[node_id_str]
                node_class = node.get("class_type", "")
                if "VHS_VideoCombine" in node_class:
                    # 检查 save_output 设置
                    save_output = node.get("inputs", {}).get("save_output", False)
                    if save_output:
                        save_output_nodes.append(node_id_str)
        
        if save_output_nodes:
            # 如果有多个 save_output=True 的节点，选择 order 最大的
            if len(save_output_nodes) > 1 and node_orders:
                selected_node_id = max(save_output_nodes, key=lambda nid: node_orders.get(nid, 0))
                logger.info(f"选择 save_output=True 且 order 最大的 VHS_VideoCombine 节点: {selected_node_id}")
            else:
                selected_node_id = save_output_nodes[0]
                logger.info(f"选择 save_output=True 的 VHS_VideoCombine 节点: {selected_node_id}")
        
        # 策略2: 如果没有 save_output=True 的节点，选择 order 最大的 VHS_VideoCombine 节点
        if not selected_node_id:
            vhs_nodes = []
            for node_id_str in video_output_nodes_str:
                if node_id_str in prompt:
                    node_class = prompt[node_id_str].get("class_type", "")
                    if "VHS_VideoCombine" in node_class:
                        vhs_nodes.append(node_id_str)
            
            if vhs_nodes and node_orders:
                selected_node_id = max(vhs_nodes, key=lambda nid: node_orders.get(nid, 0))
                logger.info(f"选择 order 最大的 VHS_VideoCombine 节点: {selected_node_id} (order: {node_orders.get(selected_node_id, 'unknown')})")
            elif vhs_nodes:
                # 如果没有 order 信息，选择 ID 最大的
                def try_int_compare(node_id):
                    try:
                        return int(str(node_id))
                    except (ValueError, TypeError):
                        return 0
                selected_node_id = max(vhs_nodes, key=try_int_compare)
                logger.info(f"选择 ID 最大的 VHS_VideoCombine 节点: {selected_node_id}")
        
        # 策略3: 如果没有找到 VHS_VideoCombine 节点，选择最后执行的任何视频节点
        if not selected_node_id:
            for node_id in reversed(execution_order_str):
                if node_id in video_output_nodes_str:
                    selected_node_id = node_id
                    logger.info(f"选择最后执行的视频节点: {node_id}")
                    break
        
        # 策略4: 如果还是没有找到，选择ID最大的节点（通常是最终输出）
        if not selected_node_id:
            def try_int_compare(node_id):
                try:
                    return int(str(node_id))
                except (ValueError, TypeError):
                    return 0
            
            selected_node_id = max(video_output_nodes_str, key=try_int_compare)
            logger.info(f"选择ID最大的视频节点: {selected_node_id}")
        
        if selected_node_id:
            # 确保使用正确的节点ID（可能是原始类型）
            actual_node_id = None
            for vid_node_id in video_output_nodes:
                if str(vid_node_id) == str(selected_node_id):
                    actual_node_id = vid_node_id
                    break
            
            if actual_node_id and videos[actual_node_id]:
                exec_index = execution_order_str.index(str(selected_node_id)) if str(selected_node_id) in execution_order_str else 'unknown'
                logger.info(f"成功生成视频，输出节点: {actual_node_id} (执行顺序: {exec_index})")
                logger.info(f"所有视频输出节点: {video_output_nodes}")
                return {"video": videos[actual_node_id][0]}
        
        # 如果仍然没有找到，返回第一个可用的视频
        selected_node_id = video_output_nodes[0]
        logger.warning(f"使用第一个可用的视频节点: {selected_node_id}")
        return {"video": videos[selected_node_id][0]}
    except Exception as e:
        ws.close()
        logger.error(f"视频生成失败: {e}", exc_info=True)
        return {"error": str(e)}


if __name__ == "__main__":
    print("Starting handler v3...")
    runpod.serverless.start({"handler": handler})
