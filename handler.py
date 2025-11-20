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
import binascii # Base64 에러 처리를 위해 import
import subprocess
import time
# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


server_address = os.getenv('SERVER_ADDRESS', '127.0.0.1')
client_id = str(uuid.uuid4())
def to_nearest_multiple_of_16(value):
    """주어진 값을 가장 가까운 16의 배수로 보정, 최소 16 보장"""
    try:
        numeric_value = float(value)
    except Exception:
        raise Exception(f"width/height 값이 숫자가 아닙니다: {value}")
    adjusted = int(round(numeric_value / 16.0) * 16)
    if adjusted < 16:
        adjusted = 16
    return adjusted
def process_input(input_data, temp_dir, output_filename, input_type):
    """입력 데이터를 처리하여 파일 경로를 반환하는 함수"""
    if input_type == "path":
        # 경로인 경우 그대로 반환
        logger.info(f"📁 경로 입력 처리: {input_data}")
        return input_data
    elif input_type == "url":
        # URL인 경우 다운로드
        logger.info(f"🌐 URL 입력 처리: {input_data}")
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        return download_file_from_url(input_data, file_path)
    elif input_type == "base64":
        # Base64인 경우 디코딩하여 저장
        logger.info(f"🔢 Base64 입력 처리")
        return save_base64_to_file(input_data, temp_dir, output_filename)
    else:
        raise Exception(f"지원하지 않는 입력 타입: {input_type}")

        
def download_file_from_url(url, output_path):
    """URL에서 파일을 다운로드하는 함수"""
    try:
        # wget을 사용하여 파일 다운로드
        result = subprocess.run([
            'wget', '-O', output_path, '--no-verbose', url
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ URL에서 파일을 성공적으로 다운로드했습니다: {url} -> {output_path}")
            return output_path
        else:
            logger.error(f"❌ wget 다운로드 실패: {result.stderr}")
            raise Exception(f"URL 다운로드 실패: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("❌ 다운로드 시간 초과")
        raise Exception("다운로드 시간 초과")
    except Exception as e:
        logger.error(f"❌ 다운로드 중 오류 발생: {e}")
        raise Exception(f"다운로드 중 오류 발생: {e}")


def save_base64_to_file(base64_data, temp_dir, output_filename):
    """Base64 데이터를 파일로 저장하는 함수"""
    try:
        # Base64 문자열 디코딩
        decoded_data = base64.b64decode(base64_data)
        
        # 디렉토리가 존재하지 않으면 생성
        os.makedirs(temp_dir, exist_ok=True)
        
        # 파일로 저장
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        with open(file_path, 'wb') as f:
            f.write(decoded_data)
        
        logger.info(f"✅ Base64 입력을 '{file_path}' 파일로 저장했습니다.")
        return file_path
    except (binascii.Error, ValueError) as e:
        logger.error(f"❌ Base64 디코딩 실패: {e}")
        raise Exception(f"Base64 디코딩 실패: {e}")
    
def queue_prompt(prompt, is_mega_model=False):
    url = f"http://{server_address}:8188/prompt"
    logger.info(f"Queueing prompt to: {url}")
    
    # 调试：检查关键节点的配置（发送前最后验证）
    logger.info("发送prompt前的最后验证:")
    if is_mega_model:
        # Rapid-AIO-Mega.json 验证
        if "16" in prompt and "widgets_values" in prompt["16"]:
            image_path_check = prompt["16"]["widgets_values"][0] if prompt["16"]["widgets_values"] else None
            logger.info(f"  节点16的image = {image_path_check}")
        if "28" in prompt and "widgets_values" in prompt["28"]:
            widgets = prompt["28"]["widgets_values"]
            logger.info(f"  节点28的strength = {widgets[3]} (I2V mode)")
    else:
        # 标准 workflow 验证
        if "541" in prompt and "inputs" in prompt["541"]:
            fun_or_fl2v = prompt["541"]["inputs"].get("fun_or_fl2v_model")
            logger.info(f"  节点541的fun_or_fl2v_model = {fun_or_fl2v} (类型: {type(fun_or_fl2v).__name__})")
        if "244" in prompt and "inputs" in prompt["244"]:
            image_path_check = prompt["244"]["inputs"].get("image")
            logger.info(f"  节点244的image = {image_path_check}")
    
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    req.add_header('Content-Type', 'application/json')
    try:
        response = urllib.request.urlopen(req)
        return json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"HTTP Error {e.code}: {e.reason}")
        logger.error(f"Error response: {error_body}")
        try:
            error_json = json.loads(error_body)
            logger.error(f"Error details: {json.dumps(error_json, indent=2)}")
        except:
            pass
        raise Exception(f"ComfyUI API 错误 ({e.code}): {error_body}")

def get_image(filename, subfolder, folder_type):
    url = f"http://{server_address}:8188/view"
    logger.info(f"Getting image from: {url}")
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen(f"{url}?{url_values}") as response:
        return response.read()

def get_history(prompt_id):
    url = f"http://{server_address}:8188/history/{prompt_id}"
    logger.info(f"Getting history from: {url}")
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())

def get_videos(ws, prompt, is_mega_model=False):
    prompt_id = queue_prompt(prompt, is_mega_model)['prompt_id']
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
                # 捕获执行错误
                error_info = message.get('data', {}).get('error', 'Unknown execution error')
                logger.error(f"Execution error received: {error_info}")
        else:
            continue

    history = get_history(prompt_id)[prompt_id]
    
    # 检查是否有错误信息
    if 'error' in history:
        error_info = history['error']
        if isinstance(error_info, dict):
            error_info = error_info.get('message', str(error_info))
        logger.error(f"Error in history: {error_info}")
        raise Exception(f"ComfyUI execution error: {error_info}")
    
    # 检查 outputs 是否存在
    if 'outputs' not in history:
        if error_info:
            raise Exception(f"ComfyUI execution error: {error_info}")
        raise Exception("No outputs found in execution history")
    
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        videos_output = []
        # 支持多种视频输出格式：gifs (标准 workflow) 和 videos (VHS_VideoCombine)
        video_list = None
        if 'gifs' in node_output:
            video_list = node_output['gifs']
        elif 'videos' in node_output:
            video_list = node_output['videos']
        
        if video_list:
            for video in video_list:
                # fullpath를 이용하여 직접 파일을 읽고 base64로 인코딩
                if 'fullpath' in video:
                    with open(video['fullpath'], 'rb') as f:
                        video_data = base64.b64encode(f.read()).decode('utf-8')
                    videos_output.append(video_data)
                elif 'filename' in video:
                    # 如果没有 fullpath，尝试使用 filename 和 subfolder
                    subfolder = video.get('subfolder', '')
                    folder_type = video.get('type', 'output')
                    filename = video['filename']
                    try:
                        video_bytes = get_image(filename, subfolder, folder_type)
                        video_data = base64.b64encode(video_bytes).decode('utf-8')
                        videos_output.append(video_data)
                    except Exception as e:
                        logger.warning(f"无法读取视频文件 {filename}: {e}")
        output_videos[node_id] = videos_output

    return output_videos

def get_available_models():
    """获取 ComfyUI 中可用的模型列表"""
    try:
        url = f"http://{server_address}:8188/object_info"
        with urllib.request.urlopen(url, timeout=5) as response:
            object_info = json.loads(response.read())
            models = []
            
            # 首先尝试 WanVideoModelLoader（用于标准 workflow）
            if "WanVideoModelLoader" in object_info:
                loader_info = object_info["WanVideoModelLoader"]
                # 尝试不同的返回格式
                if "model" in loader_info:
                    models = loader_info["model"]
                elif "input" in loader_info and "required" in loader_info["input"]:
                    if "model" in loader_info["input"]["required"]:
                        models = loader_info["input"]["required"]["model"]
                
                # 处理嵌套列表的情况
                if models and isinstance(models, list) and len(models) > 0:
                    if isinstance(models[0], list):
                        models = models[0]
                    models = [m for m in models if isinstance(m, str)]
            
            # 如果没有找到，尝试 CheckpointLoaderSimple（用于 Rapid-AIO-Mega.json）
            if not models and "CheckpointLoaderSimple" in object_info:
                loader_info = object_info["CheckpointLoaderSimple"]
                if "ckpt_name" in loader_info:
                    models = loader_info["ckpt_name"]
                elif "input" in loader_info and "required" in loader_info["input"]:
                    if "ckpt_name" in loader_info["input"]["required"]:
                        models = loader_info["input"]["required"]["ckpt_name"]
                
                # 处理嵌套列表的情况
                if models and isinstance(models, list) and len(models) > 0:
                    if isinstance(models[0], list):
                        models = models[0]
                    models = [m for m in models if isinstance(m, str)]
            
            if models:
                logger.info(f"可用模型列表: {models}")
            return models if models else []
    except Exception as e:
        logger.warning(f"获取可用模型列表失败: {e}")
        return []

def update_model_in_prompt(prompt, node_id, available_models):
    """更新 prompt 中指定节点的模型名称，如果模型不存在则使用第一个可用模型"""
    if node_id not in prompt:
        return False
    
    node = prompt[node_id]
    if "inputs" not in node or "model" not in node["inputs"]:
        return False
    
    current_model = node["inputs"]["model"]
    logger.info(f"节点 {node_id} 配置文件中的模型: {current_model}")
    
    # 如果当前模型在可用列表中，不需要更新
    if current_model in available_models:
        logger.info(f"节点 {node_id} 使用配置文件中的模型: {current_model}")
        return False
    
    # 优先选择 I2V 相关的模型（包含 I2V 关键字）
    i2v_models = [m for m in available_models if "I2V" in m.upper() or "i2v" in m.lower()]
    if i2v_models:
        new_model = i2v_models[0]
        logger.info(f"节点 {node_id} 模型更新: {current_model} -> {new_model} (配置文件中的模型不在可用列表中，已自动替换为 I2V 模型)")
        node["inputs"]["model"] = new_model
        return True
    
    # 如果没有 I2V 模型，使用第一个可用模型
    if available_models:
        new_model = available_models[0]
        logger.info(f"节点 {node_id} 模型更新: {current_model} -> {new_model} (配置文件中的模型不在可用列表中，已自动替换为第一个可用模型)")
        node["inputs"]["model"] = new_model
        return True
    
    return False

def load_workflow(workflow_path):
    """加载并验证工作流JSON文件"""
    if not os.path.exists(workflow_path):
        raise FileNotFoundError(f"工作流文件不存在: {workflow_path}")
    
    file_size = os.path.getsize(workflow_path)
    logger.info(f"加载工作流文件: {workflow_path} (大小: {file_size} 字节)")
    
    if file_size == 0:
        raise ValueError(f"工作流文件为空: {workflow_path}")
    
    try:
        with open(workflow_path, 'r', encoding='utf-8') as file:
            content = file.read()
            # 检查文件内容是否看起来像JSON（以{或[开头）
            content_stripped = content.strip()
            if not content_stripped.startswith(('{', '[')):
                # 显示前500个字符以便调试
                preview = content[:500] if len(content) > 500 else content
                logger.error(f"文件内容不是有效的JSON格式。前500字符: {preview}")
                raise ValueError(f"工作流文件不是有效的JSON格式: {workflow_path}")
            
            return json.loads(content)
    except json.JSONDecodeError as e:
        # 显示错误位置附近的内容
        with open(workflow_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            error_line = e.lineno - 1 if e.lineno > 0 else 0
            start_line = max(0, error_line - 2)
            end_line = min(len(lines), error_line + 3)
            context = ''.join(lines[start_line:end_line])
            logger.error(f"JSON解析错误 (行 {e.lineno}, 列 {e.colno}):\n{context}")
        raise ValueError(f"工作流文件JSON格式错误: {workflow_path} - {str(e)}")
    except Exception as e:
        logger.error(f"加载工作流文件时发生错误: {workflow_path} - {str(e)}")
        raise

def handler(job):
    job_input = job.get("input", {})

    # 记录job_input，但排除base64数据以避免日志过长
    log_input = {k: v for k, v in job_input.items() if k not in ["image_base64", "end_image_base64"]}
    if "image_base64" in job_input:
        log_input["image_base64"] = f"<base64 data, length: {len(job_input['image_base64'])}>"
    if "end_image_base64" in job_input:
        log_input["end_image_base64"] = f"<base64 data, length: {len(job_input['end_image_base64'])}>"
    logger.info(f"Received job input: {log_input}")
    task_id = f"task_{uuid.uuid4()}"

    # 이미지 입력 처리 (image_path, image_url, image_base64 중 하나만 사용)
    image_path = None
    if "image_path" in job_input:
        image_path = process_input(job_input["image_path"], task_id, "input_image.jpg", "path")
    elif "image_url" in job_input:
        image_path = process_input(job_input["image_url"], task_id, "input_image.jpg", "url")
    elif "image_base64" in job_input:
        image_path = process_input(job_input["image_base64"], task_id, "input_image.jpg", "base64")
    else:
        # 기본값 사용
        image_path = "/example_image.png"
        logger.info("기본 이미지 파일을 사용합니다: /example_image.png")

    # 엔드 이미지 입력 처리 (end_image_path, end_image_url, end_image_base64 중 하나만 사용)
    end_image_path_local = None
    if "end_image_path" in job_input:
        end_image_path_local = process_input(job_input["end_image_path"], task_id, "end_image.jpg", "path")
    elif "end_image_url" in job_input:
        end_image_path_local = process_input(job_input["end_image_url"], task_id, "end_image.jpg", "url")
    elif "end_image_base64" in job_input:
        end_image_path_local = process_input(job_input["end_image_base64"], task_id, "end_image.jpg", "base64")
    
    # LoRA 설정 확인 - 배열로 받아서 처리
    lora_pairs = job_input.get("lora_pairs", [])
    
    # 최대 4개 LoRA까지 지원
    lora_count = min(len(lora_pairs), 4)
    if lora_count > len(lora_pairs):
        logger.warning(f"LoRA 개수가 {len(lora_pairs)}개입니다. 최대 4개까지만 지원됩니다. 처음 4개만 사용합니다.")
        lora_pairs = lora_pairs[:4]
    
    # 获取可用模型列表，用于检测 MEGA/AIO 模型
    available_models = get_available_models()
    
    # 检测是否为 MEGA/AIO 模型（支持 I2V 和 T2V 的 all-in-one 模型）
    is_mega_model = False
    if available_models:
        for model_name in available_models:
            model_name_lower = model_name.lower()
            if "mega" in model_name_lower or "aio" in model_name_lower or "all-in-one" in model_name_lower or "allinone" in model_name_lower:
                is_mega_model = True
                logger.info(f"检测到 MEGA/AIO 模型: {model_name}, 将使用 Rapid-AIO-Mega workflow")
                break
    
    # 워크플로우 파일 선택
    # MEGA/AIO 模型使用 Rapid-AIO-Mega.json，否则使用标准 workflow
    if is_mega_model:
        workflow_file = "/Rapid-AIO-Mega.json"
        logger.info(f"Using Rapid-AIO-Mega workflow for MEGA/AIO model")
    else:
        workflow_file = "/new_Wan22_flf2v_api.json" if end_image_path_local else "/new_Wan22_api.json"
        logger.info(f"Using {'FLF2V' if end_image_path_local else 'single'} workflow with {lora_count} LoRA pairs")
    
    workflow_data = load_workflow(workflow_file)
    
    # 转换 workflow 格式：如果使用 nodes 数组格式，转换为节点 ID key 格式
    if "nodes" in workflow_data:
        # Rapid-AIO-Mega.json 使用 nodes 数组格式，需要转换
        prompt = {}
        for node in workflow_data["nodes"]:
            node_id = str(node["id"])
            # 创建符合 ComfyUI API 格式的节点对象
            converted_node = {}
            # 复制所有字段
            for key, value in node.items():
                if key != "id":  # 排除 id 字段
                    converted_node[key] = value
            # 将 type 字段转换为 class_type（ComfyUI API 需要）
            if "type" in converted_node:
                converted_node["class_type"] = converted_node["type"]
                # 保留 type 字段（某些情况下可能需要）
            prompt[node_id] = converted_node
        logger.info("已转换 nodes 数组格式为节点 ID key 格式")
    else:
        # new_Wan22_api.json 使用节点 ID key 格式
        prompt = workflow_data
    
    # 更新模型名称（仅对标准 workflow）
    if not is_mega_model and available_models:
        # 更新节点 122 和 549 的模型名称（如果存在）
        update_model_in_prompt(prompt, "122", available_models)
        update_model_in_prompt(prompt, "549", available_models)
    elif is_mega_model and available_models:
        # 对于 Rapid-AIO-Mega.json，更新节点 26 (CheckpointLoaderSimple) 的模型
        if "26" in prompt and "widgets_values" in prompt["26"]:
            current_model = prompt["26"]["widgets_values"][0] if prompt["26"]["widgets_values"] else ""
            # 查找 MEGA/AIO 模型
            mega_models = [m for m in available_models if "mega" in m.lower() or "aio" in m.lower() or "all-in-one" in m.lower() or "allinone" in m.lower()]
            if mega_models:
                new_model = mega_models[0]
                if current_model != new_model:
                    prompt["26"]["widgets_values"][0] = new_model
                    logger.info(f"节点 26 模型更新: {current_model} -> {new_model}")
            elif available_models:
                # 如果没有找到 MEGA 模型，使用第一个可用模型
                new_model = available_models[0]
                if current_model != new_model:
                    prompt["26"]["widgets_values"][0] = new_model
                    logger.info(f"节点 26 模型更新: {current_model} -> {new_model}")
    
    length = job_input.get("length", 81)
    # All-in-one 模型推荐使用 4 steps，但保持向后兼容允许自定义
    steps = job_input.get("steps", 4)
    seed = job_input.get("seed", 42)
    cfg = job_input.get("cfg", 1.0)
    positive_prompt = job_input.get("prompt", "running man, grab the gun")
    negative_prompt = job_input.get("negative_prompt", "")
    
    # 해상도(폭/높이) 16배수 보정
    original_width = job_input.get("width", 480)
    original_height = job_input.get("height", 832)
    adjusted_width = to_nearest_multiple_of_16(original_width)
    adjusted_height = to_nearest_multiple_of_16(original_height)
    if adjusted_width != original_width:
        logger.info(f"Width adjusted to nearest multiple of 16: {original_width} -> {adjusted_width}")
    if adjusted_height != original_height:
        logger.info(f"Height adjusted to nearest multiple of 16: {original_height} -> {adjusted_height}")
    
    if is_mega_model:
        # Rapid-AIO-Mega.json workflow 节点配置
        # 节点16: LoadImage (起始图像)
        if "16" in prompt and "widgets_values" in prompt["16"]:
            prompt["16"]["widgets_values"][0] = image_path
            logger.info(f"节点16 (起始图像): {image_path}")
        
        # 节点37: LoadImage (结束图像，可选)
        if end_image_path_local and "37" in prompt and "widgets_values" in prompt["37"]:
            prompt["37"]["widgets_values"][0] = end_image_path_local
            logger.info(f"节点37 (结束图像): {end_image_path_local}")
        
        # 节点34: WanVideoVACEStartToEndFrame - widgets_values[0] 是 num_frames
        if "34" in prompt and "widgets_values" in prompt["34"]:
            prompt["34"]["widgets_values"][0] = length
            logger.info(f"节点34 (VACE num_frames): {length}")
        
        # 节点48: PrimitiveInt - widgets_values[0] 是帧数
        if "48" in prompt and "widgets_values" in prompt["48"]:
            prompt["48"]["widgets_values"][0] = length
            logger.info(f"节点48 (帧数): {length}")
        
        # 节点28: WanVaceToVideo - widgets_values[3] 是 strength (1=I2V), widgets_values[0] 和 widgets_values[1] 是宽高
        if "28" in prompt and "widgets_values" in prompt["28"]:
            prompt["28"]["widgets_values"][0] = adjusted_width
            prompt["28"]["widgets_values"][1] = adjusted_height
            prompt["28"]["widgets_values"][2] = length  # length
            prompt["28"]["widgets_values"][3] = 1  # strength = 1 for I2V
            prompt["28"]["widgets_values"][4] = 1  # 保持原值
            logger.info(f"节点28 (WanVaceToVideo): width={adjusted_width}, height={adjusted_height}, length={length}, strength=1 (I2V)")
        
        # 节点9: CLIPTextEncode (正面提示词)
        if "9" in prompt and "widgets_values" in prompt["9"]:
            prompt["9"]["widgets_values"][0] = positive_prompt
            logger.info(f"节点9 (正面提示词): {positive_prompt}")
        
        # 节点10: CLIPTextEncode (负面提示词)
        if "10" in prompt and "widgets_values" in prompt["10"]:
            prompt["10"]["widgets_values"][0] = negative_prompt
            logger.info(f"节点10 (负面提示词): {negative_prompt}")
        
        # 节点8: KSampler - widgets_values[0] 是 seed, widgets_values[2] 是 steps, widgets_values[3] 是 cfg
        if "8" in prompt and "widgets_values" in prompt["8"]:
            prompt["8"]["widgets_values"][0] = seed
            prompt["8"]["widgets_values"][2] = steps
            prompt["8"]["widgets_values"][3] = cfg
            logger.info(f"节点8 (KSampler): seed={seed}, steps={steps}, cfg={cfg}")
    else:
        # 标准 workflow (new_Wan22_api.json) 节点配置
        prompt["244"]["inputs"]["image"] = image_path
        prompt["541"]["inputs"]["num_frames"] = length
        # 当有输入图像时，必须设置 fun_or_fl2v_model 为 true 以支持 I2V 模式
        if image_path and "541" in prompt and "inputs" in prompt["541"]:
            # 强制设置为布尔值 True，确保JSON序列化正确
            prompt["541"]["inputs"]["fun_or_fl2v_model"] = True
            # 验证设置是否成功
            actual_value = prompt["541"]["inputs"].get("fun_or_fl2v_model")
            logger.info(f"已设置 fun_or_fl2v_model = {actual_value} (类型: {type(actual_value).__name__}) 以支持 I2V 模式")
        prompt["135"]["inputs"]["positive_prompt"] = positive_prompt
        prompt["220"]["inputs"]["seed"] = seed
        prompt["540"]["inputs"]["seed"] = seed
        prompt["540"]["inputs"]["cfg"] = cfg
        prompt["235"]["inputs"]["value"] = adjusted_width
        prompt["236"]["inputs"]["value"] = adjusted_height
    
    if not is_mega_model:
        # 标准 workflow 的 context_overlap 和 steps 设置
        # context_overlap 动态调整：确保不超过总帧数，且对短视频使用更保守的值
        user_overlap = job_input.get("context_overlap")
        if user_overlap is not None:
            # 用户指定了值，但需要确保不超过总帧数
            context_overlap = min(user_overlap, length - 1) if length > 1 else 0
            if user_overlap != context_overlap:
                logger.warning(f"context_overlap {user_overlap} exceeds length {length}, adjusted to {context_overlap}")
        else:
            # 自动计算：对于短视频使用更小的值
            if length < 50:
                # 短视频：最多 30% 或 12，取较小值
                context_overlap = min(12, max(1, int(length * 0.3)))
            else:
                # 长视频：最多 60% 或 48，取较小值
                context_overlap = min(48, max(12, int(length * 0.6)))
            logger.info(f"Auto-calculated context_overlap: {context_overlap} for length: {length}")
        
        if "498" in prompt:
            prompt["498"]["inputs"]["context_overlap"] = context_overlap
        
        # step 설정 적용
        if "834" in prompt:
            prompt["834"]["inputs"]["steps"] = steps
            logger.info(f"Steps set to: {steps}")
            lowsteps = int(steps*0.6)
            if "829" in prompt:
                prompt["829"]["inputs"]["step"] = lowsteps
                logger.info(f"LowSteps set to: {lowsteps}")

        # 엔드 이미지가 있는 경우 617번 노드에 경로 적용 (FLF2V 전용)
        if end_image_path_local and "617" in prompt:
            prompt["617"]["inputs"]["image"] = end_image_path_local
    
    # LoRA 설정 적용
    if lora_count > 0:
        if is_mega_model:
            # Rapid-AIO-Mega.json 可能不支持 LoRA，记录警告
            logger.warning(f"Rapid-AIO-Mega workflow 不支持 LoRA 设置，已忽略 {lora_count} 个 LoRA pairs")
        else:
            # 标准 workflow 的 LoRA 设置 - HIGH LoRA는 노드 279, LOW LoRA는 노드 553
            high_lora_node_id = "279"
            low_lora_node_id = "553"
            
            # 입력받은 LoRA pairs 적용 (lora_1부터 시작)
            for i, lora_pair in enumerate(lora_pairs):
                if i < 4:  # 최대 4개까지만
                    lora_high = lora_pair.get("high")
                    lora_low = lora_pair.get("low")
                    lora_high_weight = lora_pair.get("high_weight", 1.0)
                    lora_low_weight = lora_pair.get("low_weight", 1.0)
                    
                    # HIGH LoRA 설정 (노드 279번, lora_0부터 시작)
                    if lora_high and high_lora_node_id in prompt:
                        prompt[high_lora_node_id]["inputs"][f"lora_{i}"] = lora_high
                        prompt[high_lora_node_id]["inputs"][f"strength_{i}"] = lora_high_weight
                        logger.info(f"LoRA {i+1} HIGH applied to node 279: {lora_high} with weight {lora_high_weight}")
                    
                    # LOW LoRA 설정 (노드 553번, lora_0부터 시작)
                    if lora_low and low_lora_node_id in prompt:
                        prompt[low_lora_node_id]["inputs"][f"lora_{i}"] = lora_low
                        prompt[low_lora_node_id]["inputs"][f"strength_{i}"] = lora_low_weight
                        logger.info(f"LoRA {i+1} LOW applied to node 553: {lora_low} with weight {lora_low_weight}")

    # 验证关键参数设置 - 无条件输出验证信息
    logger.info("=" * 60)
    logger.info("验证关键节点配置:")
    
    if is_mega_model:
        # Rapid-AIO-Mega.json 验证
        if "16" in prompt and "widgets_values" in prompt["16"]:
            image_in_16 = prompt["16"]["widgets_values"][0] if prompt["16"]["widgets_values"] else None
            logger.info(f"✓ 节点16 (起始图像): {image_in_16}")
        if "28" in prompt and "widgets_values" in prompt["28"]:
            widgets = prompt["28"]["widgets_values"]
            logger.info(f"✓ 节点28 (WanVaceToVideo): width={widgets[0]}, height={widgets[1]}, length={widgets[2]}, strength={widgets[3]} (I2V)")
        if "34" in prompt and "widgets_values" in prompt["34"]:
            num_frames_34 = prompt["34"]["widgets_values"][0] if prompt["34"]["widgets_values"] else None
            logger.info(f"✓ 节点34 (VACE num_frames): {num_frames_34}")
        if "8" in prompt and "widgets_values" in prompt["8"]:
            widgets = prompt["8"]["widgets_values"]
            logger.info(f"✓ 节点8 (KSampler): seed={widgets[0]}, steps={widgets[2]}, cfg={widgets[3]}")
    else:
        # 标准 workflow 验证
        if "244" in prompt:
            if "inputs" in prompt["244"]:
                image_in_244 = prompt["244"]["inputs"].get("image")
                logger.info(f"✓ 节点244 (LoadImage): image = {image_in_244}")
            else:
                logger.warning("✗ 节点244 缺少 inputs")
        else:
            logger.warning("✗ 节点244 不存在")
        
        if "541" in prompt:
            if "inputs" in prompt["541"]:
                fun_or_fl2v_value = prompt["541"]["inputs"].get("fun_or_fl2v_model")
                logger.info(f"✓ 节点541 (WanVideoImageToVideoEncode): fun_or_fl2v_model = {fun_or_fl2v_value} (类型: {type(fun_or_fl2v_value).__name__})")
                if fun_or_fl2v_value != True:
                    logger.warning(f"⚠ 警告: fun_or_fl2v_model 不是 True，实际值: {fun_or_fl2v_value}")
                
                num_frames = prompt["541"]["inputs"].get("num_frames")
                logger.info(f"  - num_frames = {num_frames}")
            else:
                logger.warning("✗ 节点541 缺少 inputs")
        else:
            logger.warning("✗ 节点541 不存在")
    
    logger.info("=" * 60)
    
    ws_url = f"ws://{server_address}:8188/ws?clientId={client_id}"
    logger.info(f"Connecting to WebSocket: {ws_url}")
    
    # 먼저 HTTP 연결이 가능한지 확인
    http_url = f"http://{server_address}:8188/"
    logger.info(f"Checking HTTP connection to: {http_url}")
    
    # HTTP 연결 확인 (최대 1분)
    max_http_attempts = 180
    for http_attempt in range(max_http_attempts):
        try:
            import urllib.request
            response = urllib.request.urlopen(http_url, timeout=5)
            logger.info(f"HTTP 연결 성공 (시도 {http_attempt+1})")
            break
        except Exception as e:
            logger.warning(f"HTTP 연결 실패 (시도 {http_attempt+1}/{max_http_attempts}): {e}")
            if http_attempt == max_http_attempts - 1:
                raise Exception("ComfyUI 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
            time.sleep(1)
    
    ws = websocket.WebSocket()
    # 웹소켓 연결 시도 (최대 3분)
    max_attempts = int(180/5)  # 3분 (1초에 한 번씩 시도)
    for attempt in range(max_attempts):
        import time
        try:
            ws.connect(ws_url)
            logger.info(f"웹소켓 연결 성공 (시도 {attempt+1})")
            break
        except Exception as e:
            logger.warning(f"웹소켓 연결 실패 (시도 {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                raise Exception("웹소켓 연결 시간 초과 (3분)")
            time.sleep(5)
    try:
        videos = get_videos(ws, prompt, is_mega_model)
        ws.close()

        # 이미지가 없는 경우 처리
        for node_id in videos:
            if videos[node_id]:
                return {"video": videos[node_id][0]}
        
        return {"error": "비디오를를 찾을 수 없습니다."}
    except Exception as e:
        ws.close()
        error_message = str(e)
        logger.error(f"Video generation failed: {error_message}")
        return {"error": error_message}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})