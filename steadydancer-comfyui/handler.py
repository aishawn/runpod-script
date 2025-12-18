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

def should_skip_node(node_type):
    """检查节点类型是否应该被跳过（ComfyUI API 不支持的节点类型）"""
    if not node_type:
        return False
    node_type_str = str(node_type)
    # 跳过 Note 节点（注释节点）
    if node_type_str == "Note" or node_type_str.startswith("Note"):
        return True
    # 跳过 GetNode 和 SetNode 节点（ComfyUI-KJNodes 辅助节点）
    if node_type_str == "GetNode" or node_type_str == "SetNode":
        return True
    # 跳过 PrimitiveNode 节点（ComfyUI 辅助节点，API 不支持）
    if node_type_str == "PrimitiveNode":
        return True
    return False

def supplement_node_inputs_from_widgets(node_id, node_data, widgets_values):
    """根据 widgets_values 补充节点的 inputs（用于列表格式的 widgets_values）"""
    if not isinstance(widgets_values, list) or len(widgets_values) == 0:
        return
    
    class_type = node_data.get("class_type") or node_data.get("type", "")
    inputs = node_data.get("inputs", {})
    
    # 根据节点类型映射 widgets_values 到 inputs
    if class_type == "WanVideoTextEncodeCached":
        # widgets_values: [model_name, precision, positive_prompt, negative_prompt, quantization, use_disk_cache, device]
        if len(widgets_values) > 0 and "model_name" not in inputs:
            inputs["model_name"] = widgets_values[0]
        if len(widgets_values) > 1 and "precision" not in inputs:
            inputs["precision"] = widgets_values[1]
        if len(widgets_values) > 2 and "positive_prompt" not in inputs:
            inputs["positive_prompt"] = widgets_values[2]
        if len(widgets_values) > 3 and "negative_prompt" not in inputs:
            inputs["negative_prompt"] = widgets_values[3]
        if len(widgets_values) > 4 and "quantization" not in inputs:
            inputs["quantization"] = widgets_values[4]
        if len(widgets_values) > 5 and "use_disk_cache" not in inputs:
            inputs["use_disk_cache"] = widgets_values[5]
        if len(widgets_values) > 6 and "device" not in inputs:
            inputs["device"] = widgets_values[6]
    
    elif class_type == "WanVideoSamplerSettings":
        # widgets_values: [steps, ?, ?, seed, sampler, ?, scheduler, shift, force_offload, riflex_freq_index, ...]
        if len(widgets_values) > 7 and "shift" not in inputs:
            inputs["shift"] = widgets_values[7]
        if len(widgets_values) > 8 and "force_offload" not in inputs:
            inputs["force_offload"] = widgets_values[8]
        if len(widgets_values) > 9 and "riflex_freq_index" not in inputs:
            inputs["riflex_freq_index"] = widgets_values[9]
    
    elif class_type == "WanVideoModelLoader":
        # widgets_values: [model_path, load_device, base_precision, quantization, ...]
        if len(widgets_values) > 1 and "load_device" not in inputs:
            inputs["load_device"] = widgets_values[1]
        if len(widgets_values) > 2 and "base_precision" not in inputs:
            inputs["base_precision"] = widgets_values[2]
        if len(widgets_values) > 3 and "quantization" not in inputs:
            inputs["quantization"] = widgets_values[3]
    
    elif class_type == "WanVideoLoraSelect":
        # widgets_values: [lora_path, strength, ...]
        if len(widgets_values) > 0 and "lora" not in inputs:
            inputs["lora"] = widgets_values[0]
        if len(widgets_values) > 1 and "strength" not in inputs:
            inputs["strength"] = widgets_values[1]
    
    elif class_type == "WanVideoImageToVideoEncode":
        # widgets_values: [height, width, num_frames, start_latent_strength, end_latent_strength, noise_aug_strength, force_offload, ...]
        if len(widgets_values) > 3 and "start_latent_strength" not in inputs:
            inputs["start_latent_strength"] = widgets_values[3]
        if len(widgets_values) > 4 and "end_latent_strength" not in inputs:
            inputs["end_latent_strength"] = widgets_values[4]
        if len(widgets_values) > 5 and "noise_aug_strength" not in inputs:
            inputs["noise_aug_strength"] = widgets_values[5]
        if len(widgets_values) > 6 and "force_offload" not in inputs:
            inputs["force_offload"] = widgets_values[6]
    
    elif class_type == "WanVideoAddSteadyDancerEmbeds":
        # widgets_values: [pose_strength_spatial, pose_strength_temporal, start_percent, end_percent, ...]
        if len(widgets_values) > 0 and "pose_strength_spatial" not in inputs:
            inputs["pose_strength_spatial"] = widgets_values[0]
        if len(widgets_values) > 1 and "pose_strength_temporal" not in inputs:
            inputs["pose_strength_temporal"] = widgets_values[1]
        if len(widgets_values) > 2 and "start_percent" not in inputs:
            inputs["start_percent"] = widgets_values[2]
        if len(widgets_values) > 3 and "end_percent" not in inputs:
            inputs["end_percent"] = widgets_values[3]
    
    elif class_type == "WanVideoBlockSwap":
        # widgets_values: [offload_txt_emb, offload_img_emb, blocks_to_swap, ...]
        if len(widgets_values) > 0 and "offload_txt_emb" not in inputs:
            inputs["offload_txt_emb"] = widgets_values[0]
        if len(widgets_values) > 1 and "offload_img_emb" not in inputs:
            inputs["offload_img_emb"] = widgets_values[1]
        if len(widgets_values) > 2 and "blocks_to_swap" not in inputs:
            inputs["blocks_to_swap"] = widgets_values[2]
    
    elif class_type == "WanVideoTorchCompileSettings":
        # widgets_values: [dynamo_cache_size_limit, backend, compile_transformer_blocks_only, mode, fullgraph, dynamic, ...]
        if len(widgets_values) > 0 and "dynamo_cache_size_limit" not in inputs:
            inputs["dynamo_cache_size_limit"] = widgets_values[0]
        if len(widgets_values) > 1 and "backend" not in inputs:
            inputs["backend"] = widgets_values[1]
        if len(widgets_values) > 2 and "compile_transformer_blocks_only" not in inputs:
            inputs["compile_transformer_blocks_only"] = widgets_values[2]
        if len(widgets_values) > 3 and "mode" not in inputs:
            inputs["mode"] = widgets_values[3]
        if len(widgets_values) > 4 and "fullgraph" not in inputs:
            inputs["fullgraph"] = widgets_values[4]
        if len(widgets_values) > 5 and "dynamic" not in inputs:
            inputs["dynamic"] = widgets_values[5]
    
    elif class_type == "ImageConcatMulti":
        # widgets_values: [direction, inputcount, match_image_size, ...]
        if len(widgets_values) > 0 and "direction" not in inputs:
            inputs["direction"] = widgets_values[0]
        if len(widgets_values) > 1 and "inputcount" not in inputs:
            inputs["inputcount"] = widgets_values[1]
        if len(widgets_values) > 2 and "match_image_size" not in inputs:
            inputs["match_image_size"] = widgets_values[2]
    
    elif class_type == "WanVideoDecode":
        # widgets_values: [tile_x, tile_y, tile_stride_x, tile_stride_y, ...]
        if len(widgets_values) > 0 and "tile_x" not in inputs:
            inputs["tile_x"] = widgets_values[0]
        if len(widgets_values) > 1 and "tile_y" not in inputs:
            inputs["tile_y"] = widgets_values[1]
        if len(widgets_values) > 2 and "tile_stride_x" not in inputs:
            inputs["tile_stride_x"] = widgets_values[2]
        if len(widgets_values) > 3 and "tile_stride_y" not in inputs:
            inputs["tile_stride_y"] = widgets_values[3]
    
    elif class_type == "WanVideoEncode":
        # widgets_values: [enable_vae_tiling, tile_x, tile_y, tile_stride_x, tile_stride_y, ...]
        if len(widgets_values) > 0 and "enable_vae_tiling" not in inputs:
            inputs["enable_vae_tiling"] = widgets_values[0]
        if len(widgets_values) > 1 and "tile_x" not in inputs:
            inputs["tile_x"] = widgets_values[1]
        if len(widgets_values) > 2 and "tile_y" not in inputs:
            inputs["tile_y"] = widgets_values[2]
        if len(widgets_values) > 3 and "tile_stride_x" not in inputs:
            inputs["tile_stride_x"] = widgets_values[3]
        if len(widgets_values) > 4 and "tile_stride_y" not in inputs:
            inputs["tile_stride_y"] = widgets_values[4]
    
    elif class_type == "WanVideoContextOptions":
        # widgets_values: [context_frames, context_overlap, context_stride, context_schedule, freenoise, verbose, ...]
        if len(widgets_values) > 0 and "context_frames" not in inputs:
            inputs["context_frames"] = widgets_values[0]
        if len(widgets_values) > 1 and "context_overlap" not in inputs:
            inputs["context_overlap"] = widgets_values[1]
        if len(widgets_values) > 2 and "context_stride" not in inputs:
            inputs["context_stride"] = widgets_values[2]
        if len(widgets_values) > 3 and "context_schedule" not in inputs:
            inputs["context_schedule"] = widgets_values[3]
        if len(widgets_values) > 4 and "freenoise" not in inputs:
            inputs["freenoise"] = widgets_values[4]
        if len(widgets_values) > 5 and "verbose" not in inputs:
            inputs["verbose"] = widgets_values[5]
    
    elif class_type == "GetImageRangeFromBatch":
        # widgets_values: [num_frames, start_index, ...]
        if len(widgets_values) > 0 and "num_frames" not in inputs:
            inputs["num_frames"] = widgets_values[0]
        if len(widgets_values) > 1 and "start_index" not in inputs:
            inputs["start_index"] = widgets_values[1]
    
    elif class_type == "WanVideoClipVisionEncode":
        # widgets_values: [image_1, strength_1, strength_2, crop, combine_embeds, clip_vision, force_offload, ...]
        if len(widgets_values) > 0 and "image_1" not in inputs:
            inputs["image_1"] = widgets_values[0]
        if len(widgets_values) > 1 and "strength_1" not in inputs:
            inputs["strength_1"] = widgets_values[1]
        if len(widgets_values) > 2 and "strength_2" not in inputs:
            inputs["strength_2"] = widgets_values[2]
        if len(widgets_values) > 3 and "crop" not in inputs:
            inputs["crop"] = widgets_values[3]
        if len(widgets_values) > 4 and "combine_embeds" not in inputs:
            inputs["combine_embeds"] = widgets_values[4]
        if len(widgets_values) > 5 and "clip_vision" not in inputs:
            inputs["clip_vision"] = widgets_values[5]
        if len(widgets_values) > 6 and "force_offload" not in inputs:
            inputs["force_offload"] = widgets_values[6]
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
    
def queue_prompt(prompt):
    url = f"http://{server_address}:8188/prompt"
    logger.info(f"Queueing prompt to: {url}")
    
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

def get_videos(ws, prompt):
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
                # 捕获执行错误
                error_data = message.get('data', {})
                error_info = error_data.get('error', 'Unknown execution error')
                error_type = error_data.get('type', '')
                node_id = error_data.get('node_id', '')
                
                # 检查是否是 OOM 错误
                if 'OutOfMemoryError' in str(error_info) or 'OOM' in str(error_info):
                    logger.error(f"❌ GPU 内存不足 (OOM) 错误 - 节点: {node_id}, 类型: {error_type}")
                    logger.error(f"错误详情: {error_info}")
                    logger.error("建议: 1) 减小图像分辨率 (width/height) 2) 减少帧数 (length) 3) 缩短提示词长度")
                else:
                    logger.error(f"Execution error received - 节点: {node_id}, 类型: {error_type}, 错误: {error_info}")
        else:
            continue

    history = get_history(prompt_id)[prompt_id]
    
    # 检查是否有错误信息
    if 'error' in history:
        error_info = history['error']
        if isinstance(error_info, dict):
            error_info = error_info.get('message', str(error_info))
        
        # 检查是否是 OOM 错误
        error_str = str(error_info)
        if 'OutOfMemoryError' in error_str or 'OOM' in error_str or 'allocation' in error_str.lower():
            logger.error(f"❌ GPU 内存不足 (OOM) 错误")
            logger.error(f"错误详情: {error_info}")
            logger.error("建议解决方案:")
            logger.error("  1. 减小图像分辨率 (width/height) - 当前值可能过大")
            logger.error("  2. 减少视频帧数 (length) - 当前值可能过大")
            logger.error("  3. 缩短提示词长度 - 过长的提示词会消耗更多内存")
            logger.error("  4. 降低 batch_size (如果可配置)")
            raise Exception(f"GPU 内存不足 (OOM): {error_info}. 请尝试减小分辨率、帧数或提示词长度。")
        else:
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
    """
    处理 SteadyDancer 视频生成任务
    """
    job_input = job.get("input", {})

    # 记录job_input，但排除base64数据以避免日志过长
    log_input = {k: v for k, v in job_input.items() if k not in ["image_base64", "end_image_base64", "video_base64", "reference_video_base64"]}
    if "image_base64" in job_input:
        log_input["image_base64"] = f"<base64 data, length: {len(job_input['image_base64'])}>"
    if "end_image_base64" in job_input:
        log_input["end_image_base64"] = f"<base64 data, length: {len(job_input['end_image_base64'])}>"
    if "video_base64" in job_input:
        log_input["video_base64"] = f"<base64 data, length: {len(job_input['video_base64'])}>"
    if "reference_video_base64" in job_input:
        log_input["reference_video_base64"] = f"<base64 data, length: {len(job_input['reference_video_base64'])}>"
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

    # LoRA 설정 확인 - 배열로 받아서 처리
    lora_pairs = job_input.get("lora_pairs", [])
    
    # 최대 4개 LoRA까지 지원
    lora_count = min(len(lora_pairs), 4)
    if lora_count > len(lora_pairs):
        logger.warning(f"LoRA 개수가 {len(lora_pairs)}개입니다. 최대 4개까지만 지원됩니다. 처음 4개만 사용합니다.")
        lora_pairs = lora_pairs[:4]
    
    # 워크플로우 파일 선택
    # SteadyDancer 工作流 - 支持 use_steadydancer 和 use_steadydancer_workflow 两种参数名
    use_steadydancer_workflow = job_input.get("use_steadydancer_workflow", False) or job_input.get("use_steadydancer", False)
    if use_steadydancer_workflow or os.path.exists("/wanvideo_SteadyDancer_example_01.json"):
        workflow_file = "/wanvideo_SteadyDancer_example_01.json"
        logger.info(f"Using SteadyDancer workflow")
    else:
        # 默认使用 SteadyDancer 工作流
        workflow_file = "/wanvideo_SteadyDancer_example_01.json"
        logger.info(f"Using SteadyDancer workflow (default)")
    
    workflow_data = load_workflow(workflow_file)
    
    # 提前获取 length 值，因为在转换 workflow 时可能会用到
    length = job_input.get("length", 81)
    
    # 转换 workflow 格式：如果使用 nodes 数组格式，转换为节点 ID key 格式
    if "nodes" in workflow_data:
        # SteadyDancer 工作流使用 nodes 数组格式，需要转换
        prompt = {}
        
        # 首先收集所有有效节点 ID（排除 Note、GetNode、SetNode 节点）
        valid_node_ids = set()
        for node in workflow_data["nodes"]:
            node_id = str(node["id"]).lstrip('#')  # 移除可能的 '#' 前缀
            node_type = node.get("type", "")
            # 跳过不支持的节点类型
            if should_skip_node(node_type):
                logger.info(f"跳过 {node_type} 节点 {node_id}（ComfyUI API 不支持）")
                continue
            valid_node_ids.add(node_id)
        
        # 建立 link_id 到 [node_id, output_index] 的映射
        # 只包含指向有效节点的 link（源节点和目标节点都必须是有效节点）
        links_map = {}
        if "links" in workflow_data:
            for link in workflow_data["links"]:
                # link 格式: [link_id, source_node_id, source_output_index, target_node_id, target_input_index, type]
                if len(link) >= 6:
                    link_id = link[0]
                    source_node_id = str(link[1]).lstrip('#')  # 移除可能的 '#' 前缀
                    source_output_index = link[2]
                    target_node_id = str(link[3]).lstrip('#')  # 移除可能的 '#' 前缀
                    target_input_index = link[4]
                    # 只存储源节点和目标节点都在有效节点中的 link
                    if source_node_id in valid_node_ids and target_node_id in valid_node_ids:
                        links_map[link_id] = [source_node_id, source_output_index]
                    else:
                        if source_node_id not in valid_node_ids:
                            logger.warning(f"跳过 link {link_id}：源节点 {source_node_id} 不存在（可能是被跳过的辅助节点）")
                        if target_node_id not in valid_node_ids:
                            logger.warning(f"跳过 link {link_id}：目标节点 {target_node_id} 不存在（可能是被跳过的辅助节点）")
        
        for node in workflow_data["nodes"]:
            node_id = str(node["id"]).lstrip('#')  # 确保节点 ID 不包含 '#' 前缀
            
            # 跳过不支持的节点类型
            node_type = node.get("type", "")
            if should_skip_node(node_type):
                logger.info(f"跳过 {node_type} 节点 {node_id}（ComfyUI API 不支持）")
                continue
            
            # 创建符合 ComfyUI API 格式的节点对象
            converted_node = {}
            # 复制所有字段
            for key, value in node.items():
                if key != "id":  # 排除 id 字段
                    if key == "inputs":
                        # 转换 inputs 数组为 inputs 对象
                        converted_inputs = {}
                        # 获取节点的 widgets_values（如果存在）
                        widgets_values = node.get("widgets_values", [])
                        
                        # widgets_values 可能是列表或字典
                        # 如果是字典（如 VHS_VideoCombine），需要按 input 名称匹配
                        # 如果是列表，按顺序匹配有 widget 的 inputs
                        widgets_values_is_dict = isinstance(widgets_values, dict)
                        
                        if not widgets_values_is_dict:
                            # 确保是列表
                            if not isinstance(widgets_values, list):
                                widgets_values = []
                        
                        # widgets_values 按 inputs 顺序包含所有有 widget 的输入值（不管是否有 link）
                        # 需要按 inputs 顺序遍历，但只对有 widget 的输入从 widgets_values 获取值
                        widget_index = 0
                        if isinstance(value, list):
                            for input_index, input_item in enumerate(value):
                                if isinstance(input_item, dict) and "name" in input_item:
                                    input_name = input_item["name"]
                                    has_widget = "widget" in input_item
                                    has_link = "link" in input_item and input_item["link"] is not None
                                    
                                    if has_link:
                                        # 如果有 link，转换为 [node_id, output_index] 格式
                                        link_id = input_item["link"]
                                        if link_id in links_map:
                                            # links_map 中只包含有效节点的链接，所以不需要再次验证
                                            source_node_id, source_output_index = links_map[link_id]
                                            converted_inputs[input_name] = [source_node_id, source_output_index]
                                        else:
                                            # 如果找不到 link，可能是引用了被跳过的节点
                                            logger.warning(f"节点 {node_id} 的输入 {input_name} 的 link {link_id} 不存在（可能指向被跳过的辅助节点），跳过此输入")
                                            # 不设置此输入，让 ComfyUI 使用默认值
                                        # 如果有 widget，需要跳过 widgets_values 中的对应值（仅当是列表时）
                                        if not widgets_values_is_dict and has_widget and widget_index < len(widgets_values):
                                            widget_index += 1
                                    else:
                                        # 如果没有 link，尝试从 value 字段或 widgets_values 获取值
                                        if "value" in input_item:
                                            converted_inputs[input_name] = input_item["value"]
                                        elif has_widget:
                                            # 从 widgets_values 获取值
                                            widget_value = None
                                            if widgets_values_is_dict:
                                                # 字典模式：按名称匹配
                                                widget_value = widgets_values.get(input_name)
                                            elif widget_index < len(widgets_values):
                                                # 列表模式：按顺序匹配
                                                widget_value = widgets_values[widget_index]
                                                widget_index += 1
                                            
                                            # 跳过 null 值（可能是可选输入）
                                            if widget_value is not None:
                                                converted_inputs[input_name] = widget_value
                                        # 如果没有值，不设置（可能是可选输入）
                        
                        # 如果 widgets_values 是字典，将所有 widget 值复制到 inputs 中
                        # 这对于 VHS_VideoCombine 等节点很重要，因为它们有很多 widget 参数
                        if widgets_values_is_dict:
                            for widget_name, widget_value in widgets_values.items():
                                # 跳过特殊字段（如 videopreview）
                                if widget_name in ["videopreview"]:
                                    continue
                                # 如果输入已经有值（如有 link 的输入），不覆盖
                                if widget_name not in converted_inputs:
                                    # 跳过 null 值
                                    if widget_value is not None:
                                        converted_inputs[widget_name] = widget_value
                        
                        converted_node["inputs"] = converted_inputs
                    else:
                        converted_node[key] = value
            # 将 type 字段转换为 class_type（ComfyUI API 需要）
            if "type" in converted_node:
                node_type = converted_node["type"]
                # 检查节点类型是否包含管道符（命名空间），如 "MathExpression|pysssss"
                if "|" in node_type:
                    # 如果包含管道符，直接使用
                    converted_node["class_type"] = node_type
                else:
                    # 如果不包含管道符，检查是否有properties中的cnr_id
                    properties = converted_node.get("properties", {})
                    cnr_id = properties.get("cnr_id")
                    if cnr_id:
                        # 尝试使用 "节点类型|插件ID" 格式
                        # 但ComfyUI API通常只需要节点类型名称，不需要插件ID
                        converted_node["class_type"] = node_type
                    else:
                        converted_node["class_type"] = node_type
                # 保留 type 字段（某些情况下可能需要）
            # 确保节点有 class_type 字段（ComfyUI API 必需）
            if "class_type" not in converted_node:
                if "type" in converted_node:
                    converted_node["class_type"] = converted_node["type"]
                else:
                    logger.warning(f"节点 {node_id} 缺少 type 和 class_type 字段")
            
            # 对于列表格式的 widgets_values，根据节点类型补充缺失的 inputs
            # 需要在设置 class_type 之后调用
            widgets_values = node.get("widgets_values", [])
            if not isinstance(widgets_values, dict) and isinstance(widgets_values, list) and len(widgets_values) > 0:
                supplement_node_inputs_from_widgets(node_id, converted_node, widgets_values)
            
            prompt[node_id] = converted_node
        
        # 验证所有引用的节点都存在，并移除无效引用
        missing_nodes = set()
        nodes_to_remove = []
        for node_id, node_data in prompt.items():
            # 双重检查：确保 prompt 中不包含不支持的节点类型
            node_type = node_data.get("type") or node_data.get("class_type", "")
            if should_skip_node(node_type):
                logger.warning(f"发现无效节点 {node_id} (类型: {node_type})，将从 prompt 中移除")
                nodes_to_remove.append(node_id)
                continue
            
            inputs = node_data.get("inputs", {})
            inputs_to_remove = []
            for input_name, input_value in inputs.items():
                if isinstance(input_value, list) and len(input_value) >= 2:
                    referenced_node_id = str(input_value[0]).lstrip('#')
                    if referenced_node_id not in valid_node_ids:
                        missing_nodes.add(referenced_node_id)
                        logger.warning(f"节点 {node_id} 的输入 {input_name} 引用了不存在的节点 {referenced_node_id}，将移除此引用")
                        inputs_to_remove.append(input_name)
            
            # 移除无效的输入引用
            for input_name in inputs_to_remove:
                del inputs[input_name]
        
        # 移除无效节点
        for node_id in nodes_to_remove:
            del prompt[node_id]
            logger.info(f"已移除无效节点 {node_id}")
        
        if missing_nodes:
            logger.warning(f"发现 {len(missing_nodes)} 个不存在的节点引用: {missing_nodes}，已自动移除")
        
        logger.info(f"已转换 nodes 数组格式为节点 ID key 格式，共 {len(prompt)} 个有效节点")
    else:
        # 如果已经是节点 ID key 格式，直接使用
        prompt = workflow_data
    
    # SteadyDancer 工作流参数
    steps = job_input.get("steps", 4)
    seed = job_input.get("seed", 42)
    cfg = job_input.get("cfg", 1.0)
    scheduler = job_input.get("scheduler", "dpm++_sde")
    sampler_name = job_input.get("sampler", "fixed")  # 默认使用 fixed
    
    # 支持多提示词输入（用于生成更长视频）
    # 可以是字符串（用换行符分隔）或数组
    prompt_input = job_input.get("prompt", "running man, grab the gun")
    if isinstance(prompt_input, list):
        # 如果是数组，用换行符连接
        positive_prompt = "\n".join(str(p) for p in prompt_input if p)
    elif isinstance(prompt_input, str):
        # 如果是字符串，直接使用（可能包含换行符）
        positive_prompt = prompt_input
    else:
        positive_prompt = str(prompt_input)
    
    # 计算提示词数量（用于日志和验证）
    prompt_lines = [line.strip() for line in positive_prompt.split("\n") if line.strip()]
    prompt_count = len(prompt_lines)
    if prompt_count > 1:
        # 根据 Hugging Face 讨论：总视频长度 = length * prompt_count
        # length 是每个 batch 的帧数
        total_frames = length * prompt_count
        # 转换为秒数（假设 16fps）
        total_seconds = total_frames / 16.0
        logger.info(f"📹 多提示词模式: {prompt_count} 个提示词，每个 batch {length} 帧，总长度约 {total_seconds:.1f} 秒 ({total_frames} 帧)")
        logger.info(f"提示词列表: {[p[:50] + '...' if len(p) > 50 else p for p in prompt_lines]}")
    
    negative_prompt = job_input.get("negative_prompt", "")
    
    # 提示词长度检查 - 过长的提示词可能导致 OOM
    max_prompt_length = 500  # 建议最大长度（单个提示词）
    if prompt_count > 1:
        # 多提示词模式：检查每个提示词的长度
        for i, prompt_line in enumerate(prompt_lines):
            if len(prompt_line) > max_prompt_length:
                logger.warning(f"⚠️ 提示词 {i+1}/{prompt_count} 长度 ({len(prompt_line)} 字符) 超过建议值 ({max_prompt_length} 字符)")
    else:
        # 单提示词模式：检查总长度
        if len(positive_prompt) > max_prompt_length:
            logger.warning(f"⚠️ 提示词长度 ({len(positive_prompt)} 字符) 超过建议值 ({max_prompt_length} 字符)，可能导致 GPU 内存不足")
            logger.warning(f"提示词前100字符: {positive_prompt[:100]}...")
    
    # 해상도(폭/높이) 16배수 보정
    original_width = job_input.get("width", 480)
    original_height = job_input.get("height", 832)
    adjusted_width = to_nearest_multiple_of_16(original_width)
    adjusted_height = to_nearest_multiple_of_16(original_height)
    if adjusted_width != original_width:
        logger.info(f"Width adjusted to nearest multiple of 16: {original_width} -> {adjusted_width}")
    if adjusted_height != original_height:
        logger.info(f"Height adjusted to nearest multiple of 16: {original_height} -> {adjusted_height}")
    
    if use_steadydancer_workflow or os.path.exists("/wanvideo_SteadyDancer_example_01.json"):
        # SteadyDancer 工作流节点配置
        logger.info("配置 SteadyDancer 工作流节点")
        
        # 节点76: LoadImage (参考图像)
        if "76" in prompt:
            if "widgets_values" in prompt["76"]:
                prompt["76"]["widgets_values"][0] = image_path
            if "inputs" not in prompt["76"]:
                prompt["76"]["inputs"] = {}
            prompt["76"]["inputs"]["image"] = image_path
            logger.info(f"节点76 (参考图像): {image_path}")
        
        # 节点75: VHS_LoadVideo (参考视频) - 可选
        # 支持 reference_video_path, reference_video_url, reference_video_base64, video_base64 多种参数名
        reference_video_path = None
        if "reference_video_path" in job_input:
            reference_video_path = process_input(job_input["reference_video_path"], task_id, "reference_video.mp4", "path")
        elif "reference_video_url" in job_input:
            reference_video_path = process_input(job_input["reference_video_url"], task_id, "reference_video.mp4", "url")
        elif "reference_video_base64" in job_input:
            reference_video_path = process_input(job_input["reference_video_base64"], task_id, "reference_video.mp4", "base64")
        elif "video_base64" in job_input:
            reference_video_path = process_input(job_input["video_base64"], task_id, "reference_video.mp4", "base64")
        
        if reference_video_path and "75" in prompt:
            if "widgets_values" in prompt["75"]:
                widgets = prompt["75"]["widgets_values"]
                if isinstance(widgets, dict):
                    widgets["video"] = reference_video_path
                    if "videopreview" in widgets and isinstance(widgets["videopreview"], dict):
                        if "params" in widgets["videopreview"]:
                            widgets["videopreview"]["params"]["filename"] = reference_video_path
            logger.info(f"节点75 (参考视频): {reference_video_path}")
        elif "75" in prompt:
            logger.info("未提供参考视频，将仅使用参考图像和提示词生成运动")
        
        # 节点22: WanVideoModelLoader - SteadyDancer模型
        if "22" in prompt:
            steadydancer_model = "WanVideo/SteadyDancer/Wan21_SteadyDancer_fp8_e4m3fn_scaled_KJ.safetensors"
            if "widgets_values" in prompt["22"]:
                widgets = prompt["22"]["widgets_values"]
                if len(widgets) > 0:
                    widgets[0] = steadydancer_model
            if "inputs" not in prompt["22"]:
                prompt["22"]["inputs"] = {}
            prompt["22"]["inputs"]["model"] = steadydancer_model
            logger.info(f"节点22 (SteadyDancer模型): {steadydancer_model}")
        
        # 节点90: OnnxDetectionModelLoader - 姿态检测模型
        if "90" in prompt:
            if "widgets_values" in prompt["90"]:
                widgets = prompt["90"]["widgets_values"]
                if len(widgets) >= 2:
                    widgets[0] = "vitpose_h_wholebody_model.onnx"
                    widgets[1] = "yolov10m.onnx"
            logger.info(f"节点90 (姿态检测模型): vitpose_h_wholebody_model.onnx, yolov10m.onnx")
        
        # 节点92: WanVideoTextEncodeCached - 文本编码
        if "92" in prompt:
            if "widgets_values" in prompt["92"]:
                widgets = prompt["92"]["widgets_values"]
                if len(widgets) >= 4:
                    widgets[0] = "umt5-xxl-enc-bf16.safetensors"
                    widgets[2] = positive_prompt
                    widgets[3] = negative_prompt
            if "inputs" not in prompt["92"]:
                prompt["92"]["inputs"] = {}
            prompt["92"]["inputs"]["text"] = positive_prompt
            prompt["92"]["inputs"]["negative_text"] = negative_prompt
            logger.info(f"节点92 (文本编码): {positive_prompt[:50]}...")
        
        # 节点69: WanVideoLoraSelect - LoRA选择
        if "69" in prompt:
            lora_path = "WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
            if "widgets_values" in prompt["69"]:
                widgets = prompt["69"]["widgets_values"]
                if len(widgets) > 0:
                    widgets[0] = lora_path
            # 同时更新 inputs
            if "inputs" not in prompt["69"]:
                prompt["69"]["inputs"] = {}
            prompt["69"]["inputs"]["lora"] = lora_path
            # strength 参数如果有默认值，从 widgets_values 获取，否则使用默认值 1.0
            if "widgets_values" in prompt["69"] and len(prompt["69"]["widgets_values"]) > 1:
                prompt["69"]["inputs"]["strength"] = prompt["69"]["widgets_values"][1]
            else:
                prompt["69"]["inputs"]["strength"] = 1.0
            logger.info(f"节点69 (LoRA): {lora_path}")
        
        # 节点63: WanVideoImageToVideoEncode - 图像到视频编码
        if "63" in prompt:
            if "widgets_values" in prompt["63"]:
                widgets = prompt["63"]["widgets_values"]
                if len(widgets) >= 3:
                    widgets[0] = adjusted_height
                    widgets[1] = adjusted_width
                    widgets[2] = length
            if "inputs" not in prompt["63"]:
                prompt["63"]["inputs"] = {}
            prompt["63"]["inputs"]["width"] = adjusted_width
            prompt["63"]["inputs"]["height"] = adjusted_height
            prompt["63"]["inputs"]["num_frames"] = length
            logger.info(f"节点63 (图像到视频编码): width={adjusted_width}, height={adjusted_height}, num_frames={length}")
        
        # 节点119: WanVideoSamplerSettings - 采样器设置
        # widgets_values顺序: [steps, ?, ?, seed, ?, ?, scheduler, ...]
        # 根据JSON: [4, 1, 5, 42, "fixed", true, "dpm++_sde", ...]
        if "119" in prompt:
            if "widgets_values" in prompt["119"]:
                widgets = prompt["119"]["widgets_values"]
                # 确保widgets_values有足够的长度
                while len(widgets) < 7:
                    widgets.append(None)
                widgets[0] = steps  # steps
                widgets[3] = seed   # seed
                if len(widgets) > 6:
                    widgets[6] = scheduler  # scheduler (索引6)
                if len(widgets) > 4:
                    widgets[4] = sampler_name  # sampler_name (索引4)
            if "inputs" not in prompt["119"]:
                prompt["119"]["inputs"] = {}
            prompt["119"]["inputs"]["steps"] = steps
            prompt["119"]["inputs"]["seed"] = seed
            prompt["119"]["inputs"]["cfg"] = cfg
            prompt["119"]["inputs"]["scheduler"] = scheduler
            logger.info(f"节点119 (采样器设置): steps={steps}, seed={seed}, cfg={cfg}, scheduler={scheduler}, sampler={sampler_name}")
        
        # 节点83: VHS_VideoCombine - 视频输出
        if "83" in prompt:
            if "widgets_values" in prompt["83"]:
                widgets = prompt["83"]["widgets_values"]
                if isinstance(widgets, dict):
                    widgets["frame_rate"] = job_input.get("frame_rate", 24)
                    widgets["filename_prefix"] = job_input.get("filename_prefix", "WanVideoWrapper_SteadyDancer")
                    widgets["format"] = "video/h264-mp4"
                    widgets["save_output"] = True
                    # 确保所有必需的参数都有值
                    if "loop_count" not in widgets:
                        widgets["loop_count"] = 0
                    if "pingpong" not in widgets:
                        widgets["pingpong"] = False
            # 同时更新 inputs，确保参数被正确设置
            if "inputs" not in prompt["83"]:
                prompt["83"]["inputs"] = {}
            prompt["83"]["inputs"]["frame_rate"] = job_input.get("frame_rate", 24)
            prompt["83"]["inputs"]["filename_prefix"] = job_input.get("filename_prefix", "WanVideoWrapper_SteadyDancer")
            prompt["83"]["inputs"]["format"] = "video/h264-mp4"
            prompt["83"]["inputs"]["save_output"] = True
            prompt["83"]["inputs"]["loop_count"] = 0
            prompt["83"]["inputs"]["pingpong"] = False
            logger.info(f"节点83 (视频输出): 已配置")
        
        # 节点117: VHS_VideoCombine - 视频输出（中间节点，用于姿态检测）
        if "117" in prompt:
            if "widgets_values" in prompt["117"]:
                widgets = prompt["117"]["widgets_values"]
                if isinstance(widgets, dict):
                    # 节点117通常用于中间输出，不需要保存
                    if "save_output" not in widgets:
                        widgets["save_output"] = False
                    if "loop_count" not in widgets:
                        widgets["loop_count"] = 0
                    if "pingpong" not in widgets:
                        widgets["pingpong"] = False
                    if "format" not in widgets:
                        widgets["format"] = "video/h264-mp4"
                    if "frame_rate" not in widgets:
                        widgets["frame_rate"] = 24
            # 同时更新 inputs
            if "inputs" not in prompt["117"]:
                prompt["117"]["inputs"] = {}
            prompt["117"]["inputs"]["save_output"] = False
            prompt["117"]["inputs"]["loop_count"] = 0
            prompt["117"]["inputs"]["pingpong"] = False
            prompt["117"]["inputs"]["format"] = "video/h264-mp4"
            prompt["117"]["inputs"]["frame_rate"] = 24
            logger.info(f"节点117 (视频输出): 已配置")
        
        logger.info("SteadyDancer 工作流节点配置完成")

    # 验证关键参数设置 - 无条件输出验证信息
    logger.info("=" * 60)
    logger.info("验证关键节点配置:")
    
    if use_steadydancer_workflow or os.path.exists("/wanvideo_SteadyDancer_example_01.json"):
        # SteadyDancer 工作流验证
        if "76" in prompt:
            if "widgets_values" in prompt["76"]:
                image_in_76 = prompt["76"]["widgets_values"][0] if prompt["76"]["widgets_values"] else None
                logger.info(f"✓ 节点76 (参考图像): {image_in_76}")
        if "75" in prompt:
            if "widgets_values" in prompt["75"]:
                widgets = prompt["75"]["widgets_values"]
                if isinstance(widgets, dict) and "video" in widgets:
                    video_in_75 = widgets["video"]
                    logger.info(f"✓ 节点75 (参考视频): {video_in_75}")
                else:
                    logger.info(f"✓ 节点75 (参考视频): 未提供")
        if "22" in prompt:
            if "widgets_values" in prompt["22"]:
                model_in_22 = prompt["22"]["widgets_values"][0] if prompt["22"]["widgets_values"] else None
                logger.info(f"✓ 节点22 (SteadyDancer模型): {model_in_22}")
        if "90" in prompt:
            logger.info(f"✓ 节点90 (姿态检测模型): 已配置")
        if "92" in prompt:
            logger.info(f"✓ 节点92 (文本编码): 已配置")
        if "69" in prompt:
            logger.info(f"✓ 节点69 (LoRA): 已配置")
        if "63" in prompt:
            logger.info(f"✓ 节点63 (图像到视频编码): 已配置")
        if "119" in prompt:
            logger.info(f"✓ 节点119 (采样器设置): 已配置")
        if "83" in prompt:
            logger.info(f"✓ 节点83 (视频输出): 已配置")
    
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
        videos = get_videos(ws, prompt)
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
