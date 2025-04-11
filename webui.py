import gradio as gr
import subprocess
import os
import torch
import warnings
import facefusion.globals as globals
from facefusion.core import run  # Hàm xử lý chính
from facefusion.typing import MediaInput
from facefusion.program import (
    create_crop_target_component,
    create_output_quality_component,
    create_face_enhancer_component,
    create_frame_enhancer_component,
    create_preview_component
)

# --- Cấu hình chạy bằng CPU ---
device = torch.device("cpu")
torch.set_num_threads(os.cpu_count())
warnings.filterwarnings("ignore", message=".*CUDA.*")
print(f"Đang sử dụng thiết bị: {device}, với {torch.get_num_threads()} luồng CPU")

# Tùy chọn chất lượng output
quality_options = ["480p", "720p", "1080p"]

# Thư mục output
output_dir = "outputs"
os.makedirs(output_dir, exist_ok=True)

def run_facefusion(source_image, target_video, quality, crop_target, face_enhancer, frame_enhancer):
    # Tạo đường dẫn file tạm
    src_path = os.path.join("temp", "source.jpg")
    tgt_path = os.path.join("temp", "target.mp4")
    os.makedirs("temp", exist_ok=True)
    source_image.save(src_path)
    tgt_path = target_video

    # Lệnh thực thi
    command = [
        "python", "facefusion.py", "run",
        "--source-path", src_path,
        "--target-path", tgt_path,
        "--output-path", output_dir,
        "--output-quality", quality,
        "--device", "cpu"  # Đảm bảo chỉ chạy bằng CPU
    ]

    if crop_target:
        command.append("--crop-target")
    if face_enhancer:
        command.append("--face-enhancer")
    if frame_enhancer:
        command.append("--frame-enhancer")

    try:
        subprocess.run(command, check=True)
        output_path = os.path.join(output_dir, "result.mp4")
        return output_path
    except subprocess.CalledProcessError:
        return "Lỗi khi chạy FaceFusion. Vui lòng kiểm tra lại đầu vào và thử lại."

with gr.Blocks(title="FaceFusion WebUI") as demo:
    gr.Markdown("""# 🧠 FaceFusion WebUI
Dễ dàng ghép mặt, chỉnh chất lượng và cải thiện video chỉ với vài cú click chuột.
""")

    with gr.Row():
        with gr.Column():
            source_input = gr.Image(label="Ảnh cần ghép mặt", type="pil")
            target_input = gr.Video(label="Video gốc", include_audio=True)

            quality = gr.Radio(quality_options, value="720p", label="Chất lượng output")
            crop_toggle = gr.Checkbox(label="Cắt mặt target (crop)", value=True)
            enhance_face = gr.Checkbox(label="Dùng Face Enhancer", value=True)
            enhance_frame = gr.Checkbox(label="Dùng Frame Enhancer", value=True)

            run_button = gr.Button("🚀 Chạy ghép mặt")

        with gr.Column():
            output_video = gr.Video(label="Kết quả")

    run_button.click(
        fn=run_facefusion,
        inputs=[source_input, target_input, quality, crop_toggle, enhance_face, enhance_frame],
        outputs=output_video
    )

demo.launch()
