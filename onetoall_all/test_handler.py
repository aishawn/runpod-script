#!/usr/bin/env python3
"""
测试 handler 函数的脚本
在容器内运行此脚本来测试 handler 功能
"""

import json
import base64
import os

# 在导入 handler 之前，通过 monkey patch 阻止 runpod.serverless.start 自动执行
# 方法：先导入 runpod 并立即 patch，然后再导入 handler
import runpod
# 保存原始函数（虽然我们不会恢复它）
_original_start = runpod.serverless.start
# 用空函数替换，阻止自动启动
def _noop_start(*args, **kwargs):
    """空函数，用于阻止 runpod serverless worker 自动启动"""
    print("⚠️  runpod.serverless.start 被调用，但已被禁用（测试模式）")
    pass
runpod.serverless.start = _noop_start

# 现在可以安全地导入 handler，不会触发 serverless worker 启动
# 使用 importlib 来更精确地控制导入过程
import importlib
import handler as handler_module
# 确保 handler 模块中的 runpod.serverless.start 也被 patch 了
if hasattr(handler_module, 'runpod'):
    handler_module.runpod.serverless.start = _noop_start

# 导入 handler 函数
from handler import handler

def test_handler_basic():
    """测试基本功能 - 使用默认图片"""
    print("=" * 60)
    print("测试 1: 基本功能测试 (使用默认图片)")
    print("=" * 60)
    
    job = {
        "input": {
            "prompt": "running man, grab the gun",
            "seed": 42,
            "width": 480,
            "height": 832,
            "length": 81,
            "steps": 4,
            "cfg": 1.0
        }
    }
    
    try:
        result = handler(job)
        print(f"\n✅ 测试成功!")
        print(f"结果类型: {type(result)}")
        if "video" in result:
            video_b64 = result["video"]
            print(f"视频数据长度: {len(video_b64)} 字符")
            # 保存视频文件
            output_path = "test_output_1.mp4"
            with open(output_path, 'wb') as f:
                f.write(base64.b64decode(video_b64))
            print(f"📹 视频已保存到: {os.path.abspath(output_path)}")
        elif "error" in result:
            print(f"❌ 错误: {result['error']}")
        else:
            print(f"结果: {result}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_handler_with_image_path():
    """测试使用图片路径"""
    print("\n" + "=" * 60)
    print("测试 2: 使用图片路径")
    print("=" * 60)
    
    # 检查默认图片是否存在
    image_path = "/example_image.png"
    if not os.path.exists(image_path):
        print(f"⚠️  图片文件不存在: {image_path}")
        print("跳过此测试")
        return
    
    job = {
        "input": {
            "image_path": image_path,
            "prompt": "running man, grab the gun",
            "seed": 42,
            "width": 480,
            "height": 832,
            "length": 81,
            "steps": 4,
            "cfg": 1.0
        }
    }
    
    try:
        result = handler(job)
        print(f"\n✅ 测试成功!")
        if "video" in result:
            video_b64 = result["video"]
            print(f"视频数据长度: {len(video_b64)} 字符")
            # 保存视频文件
            output_path = "test_output_2.mp4"
            with open(output_path, 'wb') as f:
                f.write(base64.b64decode(video_b64))
            print(f"📹 视频已保存到: {os.path.abspath(output_path)}")
        elif "error" in result:
            print(f"❌ 错误: {result['error']}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_handler_with_image_base64():
    """测试使用 Base64 图片"""
    print("\n" + "=" * 60)
    print("测试 3: 使用 Base64 图片")
    print("=" * 60)
    
    # 读取默认图片并转换为 base64
    image_path = "/example_image.png"
    if not os.path.exists(image_path):
        print(f"⚠️  图片文件不存在: {image_path}")
        print("跳过此测试")
        return
    
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        job = {
            "input": {
                "image_base64": image_base64,
                "prompt": "running man, grab the gun",
                "seed": 42,
                "width": 480,
                "height": 832,
                "length": 81,
                "steps": 4,
                "cfg": 1.0
            }
        }
        
        result = handler(job)
        print(f"\n✅ 测试成功!")
        if "video" in result:
            video_b64 = result["video"]
            print(f"视频数据长度: {len(video_b64)} 字符")
            # 保存视频文件
            output_path = "test_output_3.mp4"
            with open(output_path, 'wb') as f:
                f.write(base64.b64decode(video_b64))
            print(f"📹 视频已保存到: {os.path.abspath(output_path)}")
        elif "error" in result:
            print(f"❌ 错误: {result['error']}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_handler_with_lora():
    """测试使用 LoRA"""
    print("\n" + "=" * 60)
    print("测试 4: 使用 LoRA (如果可用)")
    print("=" * 60)
    
    # 检查 LoRA 文件是否存在
    lora_path = "/ComfyUI/models/loras"
    if not os.path.exists(lora_path):
        print(f"⚠️  LoRA 目录不存在: {lora_path}")
        print("跳过此测试")
        return
    
    # 查找可用的 LoRA 文件
    lora_files = [f for f in os.listdir(lora_path) if f.endswith('.safetensors')]
    if not lora_files:
        print(f"⚠️  未找到 LoRA 文件")
        print("跳过此测试")
        return
    
    print(f"找到 LoRA 文件: {lora_files[:2]}")
    
    # 使用前两个 LoRA 文件（如果有的话）
    high_lora = lora_files[0] if len(lora_files) > 0 else None
    low_lora = lora_files[1] if len(lora_files) > 1 else lora_files[0]
    
    job = {
        "input": {
            "prompt": "running man, grab the gun",
            "seed": 42,
            "width": 480,
            "height": 832,
            "length": 81,
            "steps": 4,
            "cfg": 1.0,
            "lora_pairs": [
                {
                    "high": high_lora,
                    "low": low_lora,
                    "high_weight": 1.0,
                    "low_weight": 1.0
                }
            ]
        }
    }
    
    try:
        result = handler(job)
        print(f"\n✅ 测试成功!")
        if "video" in result:
            video_b64 = result["video"]
            print(f"视频数据长度: {len(video_b64)} 字符")
            # 保存视频文件
            output_path = "test_output_4_lora.mp4"
            with open(output_path, 'wb') as f:
                f.write(base64.b64decode(video_b64))
            print(f"📹 视频已保存到: {os.path.abspath(output_path)}")
        elif "error" in result:
            print(f"❌ 错误: {result['error']}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_handler_flf2v():
    """测试 FLF2V (双图片) 功能"""
    print("\n" + "=" * 60)
    print("测试 5: FLF2V 功能 (双图片)")
    print("=" * 60)
    
    image_path = "/example_image.png"
    if not os.path.exists(image_path):
        print(f"⚠️  图片文件不存在: {image_path}")
        print("跳过此测试")
        return
    
    job = {
        "input": {
            "image_path": image_path,
            "end_image_path": image_path,  # 使用同一张图片作为结束图片
            "prompt": "running man, grab the gun",
            "seed": 42,
            "width": 480,
            "height": 832,
            "length": 81,
            "steps": 4,
            "cfg": 1.0
        }
    }
    
    try:
        result = handler(job)
        print(f"\n✅ 测试成功!")
        if "video" in result:
            video_b64 = result["video"]
            print(f"视频数据长度: {len(video_b64)} 字符")
            # 保存视频文件
            output_path = "test_output_5_flf2v.mp4"
            with open(output_path, 'wb') as f:
                f.write(base64.b64decode(video_b64))
            print(f"📹 视频已保存到: {os.path.abspath(output_path)}")
        elif "error" in result:
            print(f"❌ 错误: {result['error']}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Handler 功能测试")
    print("=" * 60)
    print("\n注意: 确保 ComfyUI 服务正在运行 (http://127.0.0.1:8188)")
    print("如果未运行，请先执行: python /ComfyUI/main.py --listen --use-sage-attention &\n")
    
    # 检查 ComfyUI 是否运行
    import urllib.request
    try:
        response = urllib.request.urlopen("http://127.0.0.1:8188/", timeout=5)
        print("✅ ComfyUI 服务正在运行\n")
    except Exception as e:
        print(f"⚠️  ComfyUI 服务未运行: {e}")
        print("请先启动 ComfyUI 服务\n")
        return
    
    # 运行测试
    test_handler_basic()
    test_handler_with_image_path()
    test_handler_with_image_base64()
    # test_handler_with_lora()
    # test_handler_flf2v()
    
    print("\n" + "=" * 60)
    print("所有测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()

