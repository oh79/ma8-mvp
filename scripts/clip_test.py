from PIL import Image
from sentence_transformers import SentenceTransformer, util
import os
import glob

# Ensure the sample directory exists
sample_dir = "samples/ocr/lens/"
if not os.path.exists(sample_dir):
    print(f"Error: Directory '{sample_dir}' not found. Please create it and add sample images.")
    exit()

# Find sample images (use the same logic as OCR test for consistency)
image_paths = glob.glob(os.path.join(sample_dir, "*.jpg"))
if not image_paths:
    print(f"Error: No JPG images found in '{sample_dir}'.")
    exit()

# Limit to first 3 images as per Day 2 plan example
image_paths_to_test = image_paths[:3]
if len(image_paths_to_test) < 3:
    print(f"Warning: Found only {len(image_paths_to_test)} images, testing with available ones.")

if not image_paths_to_test:
    print("Error: No images selected for CLIP testing.")
    exit()

print(f"Loading CLIP model (clip-ViT-B-32). This might take a moment...")
try:
    model = SentenceTransformer('clip-ViT-B-32')
except Exception as e:
    print(f"Error loading SentenceTransformer model: {e}")
    print("Please ensure sentence-transformers and its dependencies (torch, torchvision) are installed correctly.")
    exit()

prompts = [
    "고급스럽고 영상미 있는 렌즈 사진",
    "소프트 콘택트렌즈 후기",
    "컬러 렌즈 스타일링"
]

print("\n--- Testing CLIP Image-Text Similarity ---")
all_similarities_met_threshold = True
min_similarity_threshold = 0.2
results = []

for img_path in image_paths_to_test:
    print(f"Processing image: {os.path.basename(img_path)}")
    try:
        img = Image.open(img_path)
        # It's generally better to encode images and prompts separately for efficiency
        # if comparing one image to multiple prompts.
        img_emb = model.encode(img, convert_to_tensor=True)

        for prompt in prompts:
            try:
                txt_emb = model.encode(prompt, convert_to_tensor=True)
                sim = util.pytorch_cos_sim(txt_emb, img_emb).item()
                print(f"  ↔ '{prompt}' 유사도: {sim:.3f}")
                results.append({"image": os.path.basename(img_path), "prompt": prompt, "similarity": sim})
                if sim < min_similarity_threshold:
                    all_similarities_met_threshold = False
                    print(f"    -> Warning: Similarity ({sim:.3f}) is below threshold ({min_similarity_threshold})")
            except Exception as e:
                print(f"    Error encoding prompt '{prompt}' or calculating similarity: {e}")
                all_similarities_met_threshold = False # Consider failure as not meeting threshold

    except FileNotFoundError:
        print(f"  Error: Image file not found at {img_path}")
        all_similarities_met_threshold = False
    except Exception as e:
        print(f"  Error processing image {os.path.basename(img_path)}: {e}")
        all_similarities_met_threshold = False

# --- DoD Check --- 
print("\n--- CLIP Test Summary ---")
print(f"Total similarity checks performed: {len(results)}")
if all_similarities_met_threshold:
    print(f"DoD Met: All {len(results)} similarity scores ≥ {min_similarity_threshold}")
else:
    print(f"DoD Not Met: At least one similarity score was < {min_similarity_threshold} or an error occurred.") 