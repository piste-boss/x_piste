import shutil
import os

src_dir = "/Users/ishikawasuguru/.gemini/antigravity/brain/79e6100c-6e9b-49a2-85fb-ebf58bd88bec"
dst_dir = "/Users/ishikawasuguru/x_piste/x_image"

files = [
    ("img_0303_2000_1_1772251394427.png", "2026-0303-2000-1.png"),
    ("img_0303_2000_2_1772251442510.png", "2026-0303-2000-2.png"),
    ("img_0303_2000_3_1772251491318.png", "2026-0303-2000-3.png"),
    ("img_0303_2000_4_1772251545448.png", "2026-0303-2000-4.png"),
    ("img_0304_0730_1_1772251611684.png", "2026-0304-0730-1.png"),
    ("img_0304_0730_2_1772251668466.png", "2026-0304-0730-2.png"),
    ("img_0304_0730_3_1772251723758.png", "2026-0304-0730-3.png"),
    ("img_0304_0730_4_1772251783746.png", "2026-0304-0730-4.png"),
    ("img_0304_1215_1772252072744.png", "2026-0304-1215.png"),
    ("img_0305_0730_1772252091189.png", "2026-0305-0730.png"),
    ("img_0305_1215_1772276230628.png", "2026-0305-1215.png"),
    ("img_0305_2000_1_1772276374114.png", "2026-0305-2000-1.png"),
    ("img_0305_2000_2_1772276392459.png", "2026-0305-2000-2.png"),
    ("img_0305_2000_3_1772276417606.png", "2026-0305-2000-3.png"),
    ("img_0305_2000_4_1772276436854.png", "2026-0305-2000-4.png"),
]

for src_name, dst_name in files:
    src_path = os.path.join(src_dir, src_name)
    dst_path = os.path.join(dst_dir, dst_name)
    if os.path.exists(src_path):
        print(f"Copying {src_name} -> {dst_name}")
        shutil.copy(src_path, dst_path)
    else:
        print(f"Skipping {src_name}, not found.")
