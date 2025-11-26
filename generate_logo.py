#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成网页分析插件logo的脚本
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_logo():
    # 创建256x256像素的图像
    size = (256, 256)
    img = Image.new('RGBA', size, (255, 255, 255, 0))  # 透明背景
    draw = ImageDraw.Draw(img)
    
    # 设计logo元素
    # 1. 创建蓝色圆形背景
    center = (128, 128)
    radius = 100
    draw.ellipse([center[0]-radius, center[1]-radius, 
                  center[0]+radius, center[1]+radius], 
                 fill=(66, 133, 244, 255))  # Google蓝色
    
    # 2. 添加网页图标（简化版）
    # 浏览器窗口轮廓
    browser_width = 120
    browser_height = 80
    browser_x = center[0] - browser_width//2
    browser_y = center[1] - browser_height//2
    
    # 浏览器主体
    draw.rectangle([browser_x, browser_y, 
                    browser_x + browser_width, browser_y + browser_height], 
                   fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=2)
    
    # 浏览器地址栏
    address_bar_height = 15
    draw.rectangle([browser_x + 5, browser_y + 5, 
                    browser_x + browser_width - 5, browser_y + 5 + address_bar_height], 
                   fill=(240, 240, 240, 255), outline=(200, 200, 200, 255), width=1)
    
    # 3. 添加分析图标（放大镜）
    magnifier_center = (center[0] + 30, center[1] + 20)
    magnifier_radius = 15
    handle_length = 20
    
    # 放大镜圆环
    draw.ellipse([magnifier_center[0]-magnifier_radius, magnifier_center[1]-magnifier_radius,
                  magnifier_center[0]+magnifier_radius, magnifier_center[1]+magnifier_radius],
                 outline=(255, 255, 255, 255), width=3)
    
    # 放大镜手柄
    handle_end_x = magnifier_center[0] + magnifier_radius + handle_length
    handle_end_y = magnifier_center[1] + magnifier_radius + handle_length
    draw.line([magnifier_center[0] + magnifier_radius, magnifier_center[1] + magnifier_radius,
               handle_end_x, handle_end_y], 
              fill=(255, 255, 255, 255), width=3)
    
    # 4. 添加网络连接线
    for i in range(3):
        start_x = browser_x + 20 + i * 30
        start_y = browser_y + browser_height + 5
        end_x = start_x
        end_y = start_y + 15
        
        # 连接线
        draw.line([start_x, start_y, end_x, end_y], 
                  fill=(76, 175, 80, 255), width=2)
        
        # 连接点
        draw.ellipse([end_x-3, end_y-3, end_x+3, end_y+3], 
                     fill=(76, 175, 80, 255))
    
    # 5. 添加文字（可选，如果需要）
    try:
        # 尝试使用系统字体
        font = ImageFont.truetype("arial.ttf", 20)
        text = "Web"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        text_x = center[0] - text_width // 2
        text_y = browser_y + browser_height + 30
        
        draw.text((text_x, text_y), text, fill=(66, 133, 244, 255), font=font)
    except:
        # 如果字体不可用，跳过文字
        pass
    
    return img

def main():
    print("正在生成网页分析插件logo...")
    
    # 创建logo
    logo = create_logo()
    
    # 保存为PNG文件
    output_path = os.path.join(os.path.dirname(__file__), "logo.png")
    logo.save(output_path, "PNG")
    
    print(f"Logo已成功生成并保存到: {output_path}")
    print("Logo尺寸: 256x256 像素")
    print("Logo格式: PNG (透明背景)")
    
    # 显示logo信息
    print("\nLogo设计说明:")
    print("- 蓝色圆形背景代表网络和科技")
    print("- 浏览器窗口图标代表网页分析")
    print("- 放大镜图标代表内容分析功能")
    print("- 绿色连接线代表网络连接和数据流动")

if __name__ == "__main__":
    main()