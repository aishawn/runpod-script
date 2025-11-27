#!/usr/bin/env python3
"""
将 MP4 文件上传到 Cloudflare R2 的脚本
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError
from pathlib import Path

# R2 配置（硬编码）
DEFAULT_R2_BUCKET = "generate-image"
DEFAULT_R2_ENDPOINT = "https://54815f0378b47a05bdb27abfbb296e02.r2.cloudflarestorage.com"
DEFAULT_R2_ACCESS_KEY_ID = "33ce9b42035c24059e421092eb7d3437"
DEFAULT_R2_SECRET_ACCESS_KEY = "7e898d9484a4d55f59189be2a99cbb34aaed2828b34acfb56b42bec600ac666d"
DEFAULT_STORAGE_DOMAIN = "pub-adba99cbc4cd4237a5ed7de21ad26f3c.r2.dev"

def upload_mp4_to_r2(
    file_path: str,
    bucket_name: str = None,
    object_key: str = None,
    endpoint_url: str = None,
    access_key_id: str = None,
    secret_access_key: str = None,
    region: str = "auto"
):
    """
    上传 MP4 文件到 Cloudflare R2
    
    参数:
        file_path: 本地 MP4 文件路径
        bucket_name: R2 bucket 名称
        object_key: R2 中的对象键（路径），如果为 None 则使用文件名
        endpoint_url: R2 endpoint URL（例如: https://xxx.r2.cloudflarestorage.com）
        access_key_id: R2 Access Key ID
        secret_access_key: R2 Secret Access Key
        region: 区域，默认为 "auto"
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return False
    
    # 检查是否为 MP4 文件
    if not file_path.lower().endswith('.mp4'):
        print(f"⚠️  警告: 文件不是 .mp4 格式: {file_path}")
    
    # 如果没有指定 object_key，使用文件名
    if object_key is None:
        object_key = os.path.basename(file_path)
    
    # 使用硬编码的默认值，如果未提供参数则从环境变量获取，最后使用默认值
    endpoint_url = endpoint_url or os.getenv('R2_ENDPOINT_URL') or DEFAULT_R2_ENDPOINT
    access_key_id = access_key_id or os.getenv('R2_ACCESS_KEY_ID') or DEFAULT_R2_ACCESS_KEY_ID
    secret_access_key = secret_access_key or os.getenv('R2_SECRET_ACCESS_KEY') or DEFAULT_R2_SECRET_ACCESS_KEY
    bucket_name = bucket_name or os.getenv('R2_BUCKET_NAME') or os.getenv('R2_BUCKET') or DEFAULT_R2_BUCKET
    
    # 验证必要的配置
    if not endpoint_url:
        print("❌ 错误: 未提供 R2 endpoint URL")
        print("   请通过参数或环境变量 R2_ENDPOINT_URL 提供")
        return False
    
    if not access_key_id:
        print("❌ 错误: 未提供 R2 Access Key ID")
        print("   请通过参数或环境变量 R2_ACCESS_KEY_ID 提供")
        return False
    
    if not secret_access_key:
        print("❌ 错误: 未提供 R2 Secret Access Key")
        print("   请通过参数或环境变量 R2_SECRET_ACCESS_KEY 提供")
        return False
    
    if not bucket_name:
        print("❌ 错误: 未提供 R2 bucket 名称")
        print("   请通过参数或环境变量 R2_BUCKET_NAME 提供")
        return False
    
    try:
        # 创建 S3 客户端（R2 兼容 S3 API）
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region
        )
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        print(f"📁 文件: {file_path}")
        print(f"📦 大小: {file_size / (1024*1024):.2f} MB")
        print(f"🪣 Bucket: {bucket_name}")
        print(f"🔑 对象键: {object_key}")
        print(f"⏳ 开始上传...")
        
        # 上传文件
        s3_client.upload_file(
            file_path,
            bucket_name,
            object_key,
            ExtraArgs={'ContentType': 'video/mp4'}
        )
        
        # 生成访问 URL
        public_url = f"https://{DEFAULT_STORAGE_DOMAIN}/{object_key}"
        print(f"✅ 上传成功!")
        print(f"📹 对象键: {object_key}")
        print(f"🔗 公开访问 URL: {public_url}")
        
        return True
        
    except ClientError as e:
        print(f"❌ 上传失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='上传 MP4 文件到 Cloudflare R2')
    parser.add_argument('file_path', help='要上传的 MP4 文件路径')
    parser.add_argument('--bucket', '-b', default=None, help='R2 bucket 名称（默认使用硬编码配置）')
    parser.add_argument('--key', '-k', default=None, help='R2 中的对象键/路径（默认为文件名）')
    parser.add_argument('--endpoint', '-e', default=None, help='R2 endpoint URL（默认使用硬编码配置）')
    parser.add_argument('--access-key', '-a', default=None, help='R2 Access Key ID（默认使用硬编码配置）')
    parser.add_argument('--secret-key', '-s', default=None, help='R2 Secret Access Key（默认使用硬编码配置）')
    parser.add_argument('--region', '-r', default='auto', help='区域（默认: auto）')
    
    args = parser.parse_args()
    
    success = upload_mp4_to_r2(
        file_path=args.file_path,
        bucket_name=args.bucket,
        object_key=args.key,
        endpoint_url=args.endpoint,
        access_key_id=args.access_key,
        secret_access_key=args.secret_key,
        region=args.region
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

