import math
import os
from PIL import Image, ImageDraw

def create_gear_icon(output_ico="d:/aiagent/RJ/gear.ico", preview_png="d:/aiagent/RJ/gear_preview.png"):
    # 超采样尺寸
    size = 1024
    cx, cy = size / 2, size / 2

    # 创建高分辨率透明画布
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    teeth = 8
    r_outer = size * 0.44      # 齿顶半径
    r_inner = size * 0.35      # 齿根半径
    r_center_hole = size * 0.16 # 中心通孔半径
    r_flange = size * 0.26      # 内圈装饰环半径

    # 计算多边形顶点（齿轮外轮廓）
    points = []
    angle_step = 2 * math.pi / teeth
    # 梯形齿设计：齿顶占25%，齿侧过渡各12.5%，齿根占50%
    tooth_top_ratio = 0.26
    tooth_bottom_ratio = 0.50
    transition_ratio = (1.0 - tooth_top_ratio - tooth_bottom_ratio) / 2

    for i in range(teeth):
        base_angle = i * angle_step
        
        # 1. 齿顶开始
        a1 = base_angle - angle_step * (tooth_top_ratio / 2)
        # 2. 齿顶结束
        a2 = base_angle + angle_step * (tooth_top_ratio / 2)
        # 3. 齿根开始
        a3 = base_angle + angle_step * (tooth_top_ratio / 2 + transition_ratio)
        # 4. 齿根结束
        a4 = (i + 1) * angle_step - angle_step * (tooth_top_ratio / 2 + transition_ratio)

        # 齿顶外点
        p1 = (cx + r_outer * math.cos(a1), cy + r_outer * math.sin(a1))
        p2 = (cx + r_outer * math.cos(a2), cy + r_outer * math.sin(a2))
        # 齿根内点
        p3 = (cx + r_inner * math.cos(a3), cy + r_inner * math.sin(a3))
        p4 = (cx + r_inner * math.cos(a4), cy + r_inner * math.sin(a4))

        points.extend([p1, p2, p3, p4])

    # 1. 绘制齿轮外廓阴影 (微投影增加立体感)
    shadow_offset = size * 0.02
    shadow_points = [(x + shadow_offset * 0.5, y + shadow_offset) for x, y in points]
    shadow_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_img)
    s_draw.polygon(shadow_points, fill=(15, 23, 42, 60))
    s_draw.ellipse([cx - r_center_hole + shadow_offset * 0.5, 
                    cy - r_center_hole + shadow_offset,
                    cx + r_center_hole + shadow_offset * 0.5, 
                    cy + r_center_hole + shadow_offset], 
                   fill=(0, 0, 0, 0)) # 挖空
    
    # 2. 齿轮主体材质渐变模拟：从顶部的现代蓝到下部的深科技青蓝
    # 先绘制主体多边形
    gear_mask = Image.new("L", (size, size), 0)
    g_draw = ImageDraw.Draw(gear_mask)
    g_draw.polygon(points, fill=255)
    # 挖去中心孔
    g_draw.ellipse([cx - r_center_hole, cy - r_center_hole, cx + r_center_hole, cy + r_center_hole], fill=0)

    # 创建渐变填充
    gradient = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for y in range(size):
        factor = y / size
        # 现代科技蓝渐变: (37, 99, 235) -> (14, 116, 144) -> (30, 58, 138)
        r = int(30 * (1 - factor) + 15 * factor)
        g = int(120 * (1 - factor) + 80 * factor)
        b = int(245 * (1 - factor) + 210 * factor)
        grad_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # 应用齿轮蒙版
    img.paste(shadow_img, (0, 0), shadow_img)
    img.paste(gradient, (0, 0), gear_mask)

    # 3. 装饰元素：高光与同心内圈凹槽
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    # 内圈高光凹槽环
    ring_width = size * 0.018
    ov_draw.ellipse([cx - r_flange, cy - r_flange, cx + r_flange, cy + r_flange], 
                    outline=(255, 255, 255, 140), width=int(ring_width))
    ov_draw.ellipse([cx - r_flange + ring_width, cy - r_flange + ring_width, 
                     cx + r_flange - ring_width, cy + r_flange - ring_width], 
                    outline=(15, 23, 42, 100), width=int(ring_width * 0.6))

    # 中心孔外边框光泽
    ov_draw.ellipse([cx - r_center_hole, cy - r_center_hole, cx + r_center_hole, cy + r_center_hole], 
                    outline=(255, 255, 255, 180), width=int(size * 0.015))
    
    # 齿轮外边缘浅色勾边
    ov_draw.polygon(points, outline=(255, 255, 255, 120), width=int(size * 0.008))

    img.alpha_composite(overlay)

    # 保存预览 PNG
    img.save(preview_png, "PNG")

    # 生成包含各层级分辨率的专业 Windows ICO 图标
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    icon_layers = [img.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    
    icon_layers[0].save(
        output_ico,
        format="ICO",
        sizes=sizes,
        append_images=icon_layers[1:]
    )
    print(f"成功生成图标: {output_ico}, 尺寸列表: {sizes}")

if __name__ == "__main__":
    create_gear_icon()
